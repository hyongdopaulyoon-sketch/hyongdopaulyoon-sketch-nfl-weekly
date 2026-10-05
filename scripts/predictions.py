"""경기 결과 예측 — 기록·채점(2026-10-04 Paul 「돈을 거느냐가 아니라 결과 예측을 하라」).
  python predictions.py record --week 4        다이제스트 때(킥오프 전 마지막 판이 정본 — 킥오프 지난 경기는 동결)
  python predictions.py grade --week 4         결과 받은 뒤 채점
  python predictions.py report                 시즌 누적(시장 · 우리 드라이브 모델 · 발행 세션)
예측원 셋을 나란히 잰다:
  시장  = DK ML 무비그 승리 확률 · 내재 점수((총점 ∓ 홈 스프레드)/2) — 2018~2025 가장 정확(점수 차 오차 9.92)
  모델  = 드라이브 득점 모델(stat_research 수축 — 오차 10.38)
  발행  = 발행문 「- 예측:」 줄(check_nfl --record 가 적는다) — 뉴스로 시장 값을 조정한 사람 판단
채점: 승자 적중(무승부 제외) · 점수 차 오차 · 총점 오차 · 스프레드 쪽 적중(예측 점수 차가 라인을 넘는 쪽) · 총점 쪽 적중."""
import argparse, os, sys
from collections import defaultdict
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nfl_pull as N   # noqa: E402

SEASON = N.SEASON
HDR = ["game_id", "week", "game", "kickoff_utc", "made_at", "src", "pick", "p_pick", "score_away", "score_home",
       "line_home", "total_line", "result", "margin_err", "total_err", "spread_hit", "total_hit", "final", "flag"]


# ★ 승자 자신감(2026-10-05 Paul 승인) — 이길 팀 확률 구간. 2018~2025 정규시즌 시장 무비그 확률로 잰 실제 승자 적중:
#   ★★★★ 75%+ 82.4%(n467) · ★★★ 65~75% 71.0%(n587) · ★★ 57~65% 60.8%(n656) · ★ <57% 50.1%(n409) — 8시즌 서열 유지.
#   「누가 이기나」 자신감일 뿐 돈의 가치가 아니다: 같은 기간 페이버릿 스프레드 커버는 모든 별에서 47~49%.
STAR_CUTS = ((0.75, 4), (0.65, 3), (0.57, 2), (0.0, 1))
STAR_HIT = {4: "82%", 3: "71%", 2: "61%", 1: "50%"}


def stars(p):
    """이길 팀 확률(0.5~1) → 별 수(1~4). None 이면 0."""
    if p is None:
        return 0
    return next(n for c, n in STAR_CUTS if p >= c)


def star_str(p):
    n = stars(p)
    return "★" * n if n else ""


def path(week):
    return os.path.join(N.week_dir(week), "predictions.csv")


def _drive_model(week):
    """{팀: (보정 공격 ppd, 보정 수비 ppd)}, 리그 ppd — 그 주 전 경기만."""
    import stat_research as SR
    try:
        T, _P, _n = SR.load(SEASON, cache=False)
    except Exception:
        return {}, 2.0
    off, de = defaultdict(list), defaultdict(list)
    for (g, wk, pt, dt), x in T.items():
        if wk < week:
            off[pt].append(x); de[dt].append(x)
    allx = [x for (g, wk, pt, dt), x in T.items() if wk < week]
    lg = sum(x.get("dr_pts", 0) for x in allx) / max(sum(x.get("dr", 0) for x in allx), 1)
    teams = set(off) | set(de)
    return {t: (SR.shrunk_ppd(off[t], lg, SR.K_OFF), SR.shrunk_ppd(de[t], lg, SR.K_DEF)) for t in teams}, lg


def compute(week):
    """{game_key: {src: dict}} — 시장·모델 예측(가격·점수가 있는 경기만)."""
    import stat_research as SR
    games = N.rd(os.path.join(N.week_dir(week), "games.csv"))
    dm, lg = _drive_model(week)
    out = {}
    for g in games:
        a, h = g["away"], g["home"]
        hl, tot = N.fnum(g.get("spread_home")), N.fnum(g.get("total"))
        wa, wh = N._novig(g.get("ml_away"), g.get("ml_home"))
        neutral = g.get("neutral") == "1"
        res = {}
        if hl is not None and tot is not None and wa is not None:
            sa, sh = (tot + hl) / 2, (tot - hl) / 2
            res["시장"] = dict(pick=h if wh >= wa else a, p=max(wa, wh), sa=sa, sh=sh)
        if a in dm and h in dm:
            hfa = 0 if neutral else N.HFA / 2
            ea = SR.DRIVES_PG * (dm[a][0] + dm[h][1] - lg) - hfa
            eh = SR.DRIVES_PG * (dm[h][0] + dm[a][1] - lg) + hfa
            pm = N.norm_cdf((eh - ea) / N.SD_MARGIN) if hasattr(N, "norm_cdf") else None
            res["모델"] = dict(pick=h if eh >= ea else a, p=max(pm, 1 - pm) if pm is not None else None, sa=ea, sh=eh)
        out[f"{a}@{h}"] = (g, res)
    return out


def record(week):
    """시장·모델 예측을 predictions.csv 에 쓴다 — 킥오프 지난 경기 행은 동결, 그 밖은 최신 판으로 덮는다. 발행 행(src=발행)은 건드리지 않는다."""
    now = datetime.now(timezone.utc)
    rows = N.rd(path(week))
    keep = {(r["game"], r["src"]): r for r in rows}
    for gk, (g, res) in compute(week).items():
        kick = datetime.strptime(g["kickoff_utc"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
        for src, x in res.items():
            if (gk, src) in keep and kick <= now:
                continue
            if kick <= now:
                continue                              # 이미 시작한 경기는 새로 적지 않는다
            keep[(gk, src)] = {k: "" for k in HDR} | dict(
                game_id=g["game_id"], week=week, game=gk, kickoff_utc=g["kickoff_utc"], made_at=datetime.now().strftime("%m-%d %H:%M"), src=src,
                pick=x["pick"], p_pick=f'{x["p"]:.3f}' if x.get("p") is not None else "", score_away=f'{x["sa"]:.1f}', score_home=f'{x["sh"]:.1f}',
                line_home=g.get("spread_home", ""), total_line=g.get("total", ""))
    N.wcsv(path(week), HDR, [[r.get(k, "") for k in HDR] for r in keep.values()])
    print(f"predictions record week {week}: {len(keep)}행")


def add_pub(week, game, pick, p, sa, sh, made_at="", flag=""):
    """발행 세션 예측 한 줄(check_nfl --record 가 부른다)."""
    rows = N.rd(path(week)); keep = {(r["game"], r["src"]): r for r in rows}
    games = {f'{g["away"]}@{g["home"]}': g for g in N.rd(os.path.join(N.week_dir(week), "games.csv"))}
    g = games.get(game, {})
    keep[(game, "발행")] = {k: "" for k in HDR} | dict(game_id=g.get("game_id", ""), week=week, game=game, kickoff_utc=g.get("kickoff_utc", ""),
                                                    made_at=made_at or datetime.now().strftime("%m-%d %H:%M"), src="발행", pick=pick,
                                                    p_pick=f"{p:.3f}" if p is not None else "", score_away=f"{sa:.1f}" if sa is not None else "",
                                                    score_home=f"{sh:.1f}" if sh is not None else "", line_home=g.get("spread_home", ""),
                                                    total_line=g.get("total", ""), flag=flag)
    N.wcsv(path(week), HDR, [[r.get(k, "") for k in HDR] for r in keep.values()])


def _cache_games(week):
    """nflverse games.csv(캐시) 그 주 정규시즌 경기 — 마감 ML·스프레드·총점·점수."""
    return [g for g in N.rd(os.path.join(N.DATA, "cache", "games.csv")) if g.get("season") == str(SEASON) and g.get("week") == str(week)]


def _finals(week):
    """{A@H: (원정 점수, 홈 점수)} — 우리 results.csv(끝난 경기) 우선, 없으면 nflverse 캐시."""
    out = {}
    for g in _cache_games(week):
        fa, fh = N.fnum(g.get("away_score")), N.fnum(g.get("home_score"))
        if fa is not None and fh is not None:
            out[f'{g["away_team"]}@{g["home_team"]}'] = (fa, fh)
    for r in N.rd(os.path.join(N.week_dir(week), "results.csv")):
        if r["status"] == "STATUS_FINAL":
            out[f'{r["away"]}@{r["home"]}'] = (N.fnum(r["away_score"]), N.fnum(r["home_score"]))
    return out


def backfill(week):
    """시장 예측 소급(2026-10-05 Paul 승인) — 킥오프 전 기록이 없는 경기만, nflverse 마감 ML·스프레드·총점으로.
    made_at 「소급(마감)」 — 마감 값은 킥오프 직전 시장이라 그 시점 예측과 같은 성격이지만, 실시간 기록과 구분해 둔다. 발행·모델 행은 만들지 않는다."""
    rows = [r for r in N.rd(path(week)) if not (r["src"] == "시장" and r["made_at"].startswith("소급"))]   # 소급 시장 행은 다시 만든다
    keep = {(r["game"], r["src"]): r for r in rows}; n = 0
    dk = {r["game"]: r for r in N.rd(os.path.join(N.week_dir(week), "closing.csv"))}   # DK 마감(ESPN pickcenter) 우선 — 4주차 실시간 기록과 같은 북
    for g in _cache_games(week):
        gk = f'{g["away_team"]}@{g["home_team"]}'
        if (gk, "시장") in keep or g.get("game_type", "REG") != "REG":
            continue
        c = dk.get(gk)
        if c and N.fnum(c.get("spread_home")) is not None and N.fnum(c.get("total")) is not None and c.get("ml_home"):
            hl, tot = N.fnum(c["spread_home"]), N.fnum(c["total"]); wa, wh = N._novig(c.get("ml_away"), c.get("ml_home")); tag = "소급(DK 마감)"
        else:
            sl, tot = N.fnum(g.get("spread_line")), N.fnum(g.get("total_line"))
            wa, wh = N._novig(g.get("away_moneyline"), g.get("home_moneyline"))
            hl = -sl if sl is not None else None          # nflverse spread_line = 홈 기대 마진 → 베팅 표기
            tag = "소급(nflverse 마감)"
        if hl is None or tot is None or wa is None:
            continue
        keep[(gk, "시장")] = {k: "" for k in HDR} | dict(
            game_id=g["game_id"], week=week, game=gk, kickoff_utc="", made_at=tag, src="시장",
            pick=g["home_team"] if wh >= wa else g["away_team"], p_pick=f"{max(wa, wh):.3f}",
            score_away=f"{(tot + hl) / 2:.1f}", score_home=f"{(tot - hl) / 2:.1f}", line_home=f"{hl:g}", total_line=f"{tot:g}")
        n += 1
    os.makedirs(N.week_dir(week), exist_ok=True)
    N.wcsv(path(week), HDR, [[r.get(k, "") for k in HDR] for r in keep.values()])
    print(f"predictions backfill week {week}: 소급 {n}경기")


def grade(week):
    rows = N.rd(path(week))
    fin = _finals(week)
    n = 0
    for r in rows:
        if r["game"] not in fin:
            continue
        a, h = r["game"].split("@")
        fa, fh = fin[r["game"]]
        r["final"] = f"{a} {fa:g}-{fh:g} {h}"
        win = h if fh > fa else a if fa > fh else ""
        r["result"] = "" if not win else ("W" if r["pick"] == win else "L")
        sa, sh = N.fnum(r["score_away"]), N.fnum(r["score_home"])
        lh, tl = N.fnum(r["line_home"]), N.fnum(r["total_line"])
        if sa is not None and sh is not None:
            r["margin_err"] = f"{abs((sh - sa) - (fh - fa)):.1f}"; r["total_err"] = f"{abs((sh + sa) - (fh + fa)):.1f}"
            if r["src"] == "시장":
                r["spread_hit"] = r["total_hit"] = ""        # 시장 예측 = 라인 자체(내재 점수 반올림 잔차로 쪽이 생기는 착시 방지)
            elif lh is not None:
                pred = (sh - sa) + lh; act = (fh - fa) + lh       # 홈 커버 여유(+ = 홈 커버)
                r["spread_hit"] = "" if act == 0 or pred == 0 else ("W" if (pred > 0) == (act > 0) else "L")
            if tl is not None and r["src"] != "시장":
                pt_, at_ = (sh + sa) - tl, (fh + fa) - tl
                r["total_hit"] = "" if at_ == 0 or pt_ == 0 else ("W" if (pt_ > 0) == (at_ > 0) else "L")
        n += 1
    N.wcsv(path(week), HDR, [[r.get(k, "") for k in HDR] for r in rows])
    print(f"predictions grade week {week}: {n}행")


def summary(rows):
    """{src: dict(승자 W-L, 점수 차 오차, 총점 오차, 스프레드 W-L, 총점 W-L)}"""
    out = {}
    for src in ("시장", "모델", "발행"):
        xs = [r for r in rows if r["src"] == src and r.get("final")]
        if not xs:
            continue
        w = sum(1 for r in xs if r["result"] == "W"); l = sum(1 for r in xs if r["result"] == "L")
        me = [N.fnum(r["margin_err"]) for r in xs if N.fnum(r["margin_err"]) is not None]
        te = [N.fnum(r["total_err"]) for r in xs if N.fnum(r["total_err"]) is not None]
        sw = sum(1 for r in xs if r["spread_hit"] == "W"); sl = sum(1 for r in xs if r["spread_hit"] == "L")
        tw = sum(1 for r in xs if r["total_hit"] == "W"); tl = sum(1 for r in xs if r["total_hit"] == "L")
        st = {}
        for k in (4, 3, 2, 1):
            ys = [r for r in xs if stars(N.fnum(r["p_pick"])) == k and r["result"] in ("W", "L")]
            st[k] = (sum(1 for r in ys if r["result"] == "W"), sum(1 for r in ys if r["result"] == "L"))
        out[src] = dict(n=len(xs), w=w, l=l, me=sum(me) / len(me) if me else None, te=sum(te) / len(te) if te else None, sw=sw, sl=sl, tw=tw, tl=tl,
                        stars=st, back=sum(1 for r in xs if r["made_at"].startswith("소급")))
    return out


def all_rows():
    rows = []
    for wk in range(1, 23):
        p = path(wk)
        if os.path.exists(p):
            rows += N.rd(p)
    return rows


def report(week=None):
    rows = all_rows()
    print(f"📊 NFL {SEASON} 결과 예측 — 시즌 누적")
    for lab, rs in ((f"{week}주차", [r for r in rows if r["week"] == str(week)]), ("시즌", rows)) if week else (("시즌", rows),):
        s = summary(rs)
        for src, x in s.items():
            print(f"■ {lab} {src}: {x['n']}경기" + (f"(소급 {x['back']})" if x["back"] else "") + f" · 승자 {x['w']}-{x['l']}"
                  + (f" {100 * x['w'] / (x['w'] + x['l']):.0f}%" if x['w'] + x['l'] else "")
                  + (f" · 점수 차 오차 {x['me']:.1f} · 총점 오차 {x['te']:.1f}" if x["me"] is not None else "")
                  + (f" · 스프레드 쪽 {x['sw']}-{x['sl']} · 총점 쪽 {x['tw']}-{x['tl']}" if src != "시장" else ""))
            print("    별점별 승자: " + " · ".join(f"{'★' * k} {w}-{l}" + (f" {100 * w / (w + l):.0f}%" if w + l else "") + f"(기대 {STAR_HIT[k]})"
                                          for k, (w, l) in x["stars"].items()))
    ex = [r for r in rows if r["src"] == "발행" and r.get("flag") == "상한 예외" and r.get("result") in ("W", "L")]
    if ex:
        print(f"■ 발행 상한 예외(시장 ±5%p 초과 — QB·새 정보·확정): 승자 {sum(1 for r in ex if r['result'] == 'W')}-{sum(1 for r in ex if r['result'] == 'L')}")
    print("  (시장은 스프레드 쪽을 고르지 않는다 — 라인 자체가 시장 예측 점수 차 · 별점은 승자 자신감이지 돈의 가치가 아니다)")


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("record", "grade"):
        sub.add_parser(c).add_argument("--week", type=int, required=True)
    sub.add_parser("report").add_argument("--week", type=int, help="그 주차 줄을 시즌 위에 먼저")
    sub.add_parser("backfill").add_argument("--weeks", required=True, help="예: 1-4")
    a = ap.parse_args()
    if a.cmd == "backfill":
        lo, _, hi = a.weeks.partition("-")
        for wk in range(int(lo), int(hi or lo) + 1):
            backfill(wk); grade(wk)
        return
    {"record": lambda: record(a.week), "grade": lambda: grade(a.week), "report": lambda: report(a.week)}[a.cmd]()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
