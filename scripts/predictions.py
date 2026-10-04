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
       "line_home", "total_line", "result", "margin_err", "total_err", "spread_hit", "total_hit", "final"]


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


def add_pub(week, game, pick, p, sa, sh, made_at=""):
    """발행 세션 예측 한 줄(check_nfl --record 가 부른다)."""
    rows = N.rd(path(week)); keep = {(r["game"], r["src"]): r for r in rows}
    games = {f'{g["away"]}@{g["home"]}': g for g in N.rd(os.path.join(N.week_dir(week), "games.csv"))}
    g = games.get(game, {})
    keep[(game, "발행")] = {k: "" for k in HDR} | dict(game_id=g.get("game_id", ""), week=week, game=game, kickoff_utc=g.get("kickoff_utc", ""),
                                                    made_at=made_at or datetime.now().strftime("%m-%d %H:%M"), src="발행", pick=pick,
                                                    p_pick=f"{p:.3f}" if p is not None else "", score_away=f"{sa:.1f}" if sa is not None else "",
                                                    score_home=f"{sh:.1f}" if sh is not None else "", line_home=g.get("spread_home", ""),
                                                    total_line=g.get("total", ""))
    N.wcsv(path(week), HDR, [[r.get(k, "") for k in HDR] for r in keep.values()])


def grade(week):
    rows = N.rd(path(week))
    res = {f'{r["away"]}@{r["home"]}': r for r in N.rd(os.path.join(N.week_dir(week), "results.csv")) if r["status"] == "STATUS_FINAL"}
    n = 0
    for r in rows:
        x = res.get(r["game"])
        if not x:
            continue
        a, h = r["game"].split("@")
        fa, fh = N.fnum(x["away_score"]), N.fnum(x["home_score"])
        r["final"] = f"{a} {fa:g}-{fh:g} {h}"
        win = h if fh > fa else a if fa > fh else ""
        r["result"] = "" if not win else ("W" if r["pick"] == win else "L")
        sa, sh = N.fnum(r["score_away"]), N.fnum(r["score_home"])
        lh, tl = N.fnum(r["line_home"]), N.fnum(r["total_line"])
        if sa is not None and sh is not None:
            r["margin_err"] = f"{abs((sh - sa) - (fh - fa)):.1f}"; r["total_err"] = f"{abs((sh + sa) - (fh + fa)):.1f}"
            if lh is not None:
                pred = (sh - sa) + lh; act = (fh - fa) + lh       # 홈 커버 여유(+ = 홈 커버)
                r["spread_hit"] = "" if act == 0 or pred == 0 else ("W" if (pred > 0) == (act > 0) else "L")
            if tl is not None:
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
        out[src] = dict(n=len(xs), w=w, l=l, me=sum(me) / len(me) if me else None, te=sum(te) / len(te) if te else None, sw=sw, sl=sl, tw=tw, tl=tl)
    return out


def all_rows():
    rows = []
    for wk in range(1, 23):
        p = path(wk)
        if os.path.exists(p):
            rows += N.rd(p)
    return rows


def report():
    s = summary(all_rows())
    print(f"📊 NFL {SEASON} 결과 예측 — 시즌 누적")
    for src, x in s.items():
        print(f"■ {src}: {x['n']}경기 · 승자 {x['w']}-{x['l']}" + (f" {100 * x['w'] / (x['w'] + x['l']):.0f}%" if x['w'] + x['l'] else "")
              + (f" · 점수 차 오차 {x['me']:.1f} · 총점 오차 {x['te']:.1f}" if x["me"] is not None else "")
              + (f" · 스프레드 쪽 {x['sw']}-{x['sl']}" if src != "시장" else "") + f" · 총점 쪽 {x['tw']}-{x['tl']}")
    print("  (시장은 스프레드 쪽을 고르지 않는다 — 라인 자체가 시장 예측 점수 차)")


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("record", "grade"):
        sub.add_parser(c).add_argument("--week", type=int, required=True)
    sub.add_parser("report")
    a = ap.parse_args()
    {"record": lambda: record(a.week), "grade": lambda: grade(a.week), "report": report}[a.cmd]()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
