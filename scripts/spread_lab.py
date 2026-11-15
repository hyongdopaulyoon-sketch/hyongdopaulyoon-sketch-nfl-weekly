"""spread_lab.py — 「스프레드를 맞히는 정의」 검정(2026-11-15 Paul 「스프레드픽도 내자 · nfl도 스프레드 맞추는 방향으로」 → 계획 3번 「오늘 바로 시작」).
  python scripts/spread_lab.py            # 2018~2025 정규시즌 3주차~ · data/spread_lab_<오늘>.md
문턱(실행 전 고정 — Paul 승인 계획): 과거 2개 이상 시즌에서 같은 방향 & 전체 53% 이상인 정의만 스프레드 픽 정의 후보. 보고는 승-패 먼저,
시즌별 50% 넘긴 시즌 수·z(50% 대비)도 같이(여러 후보를 한꺼번에 보므로 |z| 2.6 미만은 우연 가능).
후보(실행 전 고정): D1 모델 마진 쪽(현행) · D2 모델 반대쪽(차 2+/3.5+/5+) · D3 홈 언더독 +7 이상 → 홈(A7) · D4 원정 휴식 우위 3일+ → 원정 ·
D5 원정 언더독 → 원정 · D6 언더독 전부 · D7 키 넘버 3·7 넘긴 이동 반대쪽(A6 · 개장 라인 있는 2024~25) · D8 페이버릿 전부(= 예측 승자 커버).
2차 — 선수 연결(2026-11-15 Paul 「스프레드와 선수들 정보를 연결시켜야」 · 후보는 실행 전 고정 · 같은 문턱 · 「그 팀 쪽」 승-패로 적고 47% 이하면 상대 쪽이 통과).
이미 본 것(재검 안 함): 결장 수 차·OL 2명+·패스러시·CPOE 차·백업 QB 첫 선발(backtest_features F1~F5 통과 0) · 백업 QB n번째 선발·주전 3명+ 결장(situations.py ≈50%).
새 후보: Q1 선발 QB 값(그 주 전까지 직전 시즌+올해 드롭백 EPA · 150 드롭백 수축)이 상대보다 0.10+ 높은 팀 · Q2 QB 값이 더 높은데 언더독인 팀 ·
Q3 타깃 1위 리시버(그 주 전 시즌 누적 · 팀 3경기+) 결장 첫 경기 팀 · Q4 결장 2~3경기째 · Q5 캐리 1위 러셔 결장 첫 경기 팀 · Q6 결장 2~3경기째 ·
Q7 첫 선발 QB(1999~ 선발 기록 없음 & 직전 경기 선발과 다름) 상대가 7+ 페이버릿 → 페이버릿(A12 의 스프레드 판). 결장 = 그 경기 타깃·캐리·드롭백 0.
한 경기에서 두 팀이 같은 조건이면 제외.
"""
import datetime as dt
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfl_pull as N  # noqa: E402
import backtest as B  # noqa: E402

SEASONS = list(range(2018, 2026))
MIN_WEEK = 3


def pbp_path(season):
    for p in (os.path.join(N.CACHE, "hist", f"play_by_play_{season}.csv.gz"), os.path.join(N.CACHE, f"play_by_play_{season}.csv.gz")):
        if os.path.exists(p):
            return p
    return ""


def model_rows():
    games_all = N.rd(os.path.join(N.CACHE, "games.csv"))
    rows = []
    for season in SEASONS:
        pbp, pp = pbp_path(season), pbp_path(season - 1)
        if not pbp:
            print(f"  {season} pbp 없음 — 건너뜀"); continue
        cur = N._team_week_epa(pbp, season); db = B.qb_dropbacks(pbp)
        prev = N._team_week_epa(pp, season - 1) if pp else {}
        teams = sorted({t for t, _ in cur} | {t for t, _ in prev})
        gs = [g for g in games_all if g["season"] == str(season) and g["game_type"] == "REG" and g.get("result") and g.get("spread_line")]
        for wk in sorted({int(g["week"]) for g in gs}):
            rt = B.ratings_asof(cur, prev, wk, teams) if wk >= MIN_WEEK else {}
            for g in gs:
                if int(g["week"]) != wk:
                    continue
                h, aw = g["home_team"], g["away_team"]
                margin = None
                if wk >= MIN_WEEK and h in rt and aw in rt:
                    oh, dh, oa, da = rt[h]["off"], rt[h]["def"], rt[aw]["off"], rt[aw]["def"]
                    hfa = 0.0 if str(g.get("location", "")).lower() == "neutral" else N.HFA
                    mh, ma = B.main_qb_before(db, h, wk), B.main_qb_before(db, aw, wk)
                    qh = -N.QB_ADJ if (g.get("home_qb_name") and mh and not N._same_person(mh, g["home_qb_name"])) else 0.0
                    qa = -N.QB_ADJ if (g.get("away_qb_name") and ma and not N._same_person(ma, g["away_qb_name"])) else 0.0
                    margin = N.PLAYS * ((oh + da) - (oa + dh)) + hfa + qh - qa
                rows.append(dict(home=h, away=aw, hq=g.get("home_qb_name") or "", aq=g.get("away_qb_name") or "",
                                 season=season, week=wk, margin=margin, res=N.fnum(g["result"]), mk=N.fnum(g["spread_line"]),
                                 ar=N.fnum(g.get("away_rest")) or 7, hr=N.fnum(g.get("home_rest")) or 7, gid=g["game_id"]))
        print(f"  {season}: 누적 {len(rows)}경기")
    return rows


def player_feats(rows):
    """rows 에 선수 상황 칸을 붙인다(그 주 전까지만 본 값) — qv_h/qv_a(선발 QB 값) · wr_h/wr_a·rb_h/rb_a(1위 선수 연속 결장 수, 출전이면 0, 판정 불가면 None) · fs_h/fs_a(첫 선발 QB)."""
    K = 150.0
    # 첫 선발 QB: games.csv 전체(1999~)에서 그 경기 전 선발 기록
    seen = set(); lastq = {}; first = {}
    for g in sorted((g for g in N.rd(os.path.join(N.CACHE, "games.csv")) if g["game_type"] == "REG"), key=lambda g: (int(g["season"]), int(g["week"]), g["game_id"])):
        for t, q in ((g["home_team"], g.get("home_qb_name") or ""), (g["away_team"], g.get("away_qb_name") or "")):
            k = N._norm_name(q)
            if k:
                first[(g["game_id"], t)] = (k not in seen) and (lastq.get((g["season"], t)) not in (None, k))
                lastq[(g["season"], t)] = k
        for q in (g.get("home_qb_name"), g.get("away_qb_name")):
            if N._norm_name(q):
                seen.add(N._norm_name(q))
    by_season = defaultdict(list)
    for r in rows:
        by_season[r["season"]].append(r)
    prevq = defaultdict(lambda: [0.0, 0.0])
    p0 = pbp_path(min(by_season) - 1)
    if p0:                                                              # 첫 시즌의 「직전 시즌」 QB 값
        for x in N.rd(p0):
            if x.get("season_type", "REG") == "REG" and x.get("qb_dropback") == "1" and x.get("passer_player_name"):
                prevq[x["passer_player_name"]][0] += 1; prevq[x["passer_player_name"]][1] += N.fnum(x.get("epa")) or 0.0
    for season in sorted(by_season):
        pbp = pbp_path(season)
        qb = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))     # week -> passer -> [dropbacks, epa]
        use = defaultdict(lambda: defaultdict(set))                    # (gid, team) -> {"p": 이름들(타깃·캐리·드롭백)}
        tg = defaultdict(lambda: defaultdict(lambda: defaultdict(int))); ca = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))   # team -> week -> name -> n
        for x in N.rd(pbp):
            if x.get("season_type", "REG") != "REG" or not x.get("posteam"):
                continue
            wk = int(x["week"]); t = x["posteam"]; key = (x["game_id"], t)
            e = N.fnum(x.get("epa"))
            if x.get("qb_dropback") == "1" and x.get("passer_player_name"):
                d = qb[wk][x["passer_player_name"]]; d[0] += 1; d[1] += e or 0.0; use[key]["p"].add(x["passer_player_name"])
            if x.get("play_type") == "pass" and x.get("receiver_player_name"):
                tg[t][wk][x["receiver_player_name"]] += 1; use[key]["p"].add(x["receiver_player_name"])
            if x.get("play_type") == "run" and x.get("rusher_player_name"):
                ca[t][wk][x["rusher_player_name"]] += 1; use[key]["p"].add(x["rusher_player_name"])
        cumq = defaultdict(lambda: [0.0, 0.0])

        def qval(full, wk):
            n = e = 0.0
            for nm, (a, b) in prevq.items():
                if N._same_person(nm, full):
                    n += a; e += b
            for w2 in qb:
                if w2 < wk:
                    for nm, (a, b) in qb[w2].items():
                        if N._same_person(nm, full):
                            n += a; e += b
            return e / (n + K)                                           # 0(리그 평균 근처) 쪽으로 수축

        def streak(tbl, t, wk, key_games):
            """그 주 전 누적 1위 선수의 연속 결장 수(이번 경기 포함) — 팀 3경기 미만이면 None."""
            wks = sorted(w for w in tbl[t] if w < wk)
            if len(wks) < 3:
                return None
            tot = defaultdict(int)
            for w in wks:
                for nm, c in tbl[t][w].items():
                    tot[nm] += c
            lead = max(tot, key=tot.get)
            if lead in use[key_games]["p"]:
                return 0
            s = 1
            for w in reversed(wks):
                if lead in tg[t][w] or lead in ca[t][w]:
                    break
                s += 1
            return s
        for r in sorted(by_season[season], key=lambda r: r["week"]):
            for sd, t, q in (("h", r["home"], r["hq"]), ("a", r["away"], r["aq"])):
                r["qv_" + sd] = qval(q, r["week"]) if q else None
                r["wr_" + sd] = streak(tg, t, r["week"], (r["gid"], t)); r["rb_" + sd] = streak(ca, t, r["week"], (r["gid"], t))
                r["fs_" + sd] = bool(first.get((r["gid"], t)))
        prevq = defaultdict(lambda: [0.0, 0.0])
        for w2 in qb:
            for nm, (a, b) in qb[w2].items():
                prevq[nm][0] += a; prevq[nm][1] += b
        print(f"  선수 {season}")


def tally(rows, side):
    """side(r) → +1 홈 쪽 / −1 원정 쪽 / 0 해당 없음. 돌려주는 값 (w, l, p, {season: [w, l]})."""
    w = l = p = 0; by = defaultdict(lambda: [0, 0])
    for r in rows:
        s = side(r)
        if not s:
            continue
        cov = r["res"] - r["mk"]          # + = 홈 커버(nflverse spread_line = 홈 기대 마진)
        if cov == 0:
            p += 1; continue
        ok = (cov > 0) == (s > 0)
        w += ok; l += (not ok); by[r["season"]][0 if ok else 1] += 1
    return w, l, p, by


def line(lab, rows, side):
    w, l, p, by = tally(rows, side)
    n = w + l
    if not n:
        return f"| {lab} | 0 | — | — | — | — | — |", None
    pct = 100 * w / n; z = (w - n / 2) / math.sqrt(n / 4)
    over = sum(1 for s, (a, b) in by.items() if a + b and a / (a + b) > 0.5); tot = sum(1 for s, (a, b) in by.items() if a + b)
    seas = " · ".join(f"{str(s)[2:]}:{a}-{b}" for s, (a, b) in sorted(by.items()))
    ok = pct >= 53 and over >= 2
    return f"| {lab} | {n} | {w}-{l}" + (f"-{p}" if p else "") + f" | {pct:.1f}% | {z:+.2f} | {over}/{tot} | {seas} |", dict(lab=lab, n=n, w=w, l=l, pct=pct, z=z, over=over, tot=tot, ok=ok)


def a6_rows():
    """개장·마감 라인(ESPN · 2024~25) — 키 넘버 3·7 넘긴 이동 반대쪽. 홈 라인 기준(− = 홈 페이버릿)."""
    out = []
    for r in N.rd(os.path.join(N.CACHE, "odds_openclose.csv")):
        o, c = N.fnum(r.get("open_spread_home")), N.fnum(r.get("close_spread_home"))
        hs, as_ = N.fnum(r.get("home_score")), N.fnum(r.get("away_score"))
        if o is None or c is None or hs is None or as_ is None or o == c:
            continue
        if not any((abs(o) < k <= abs(c)) or (abs(c) < k <= abs(o)) for k in (3.0, 7.0)):
            continue
        # 이동 방향: c < o 면 홈 쪽으로 이동(홈이 더 페이버릿) → 반대쪽 = 원정
        out.append(dict(season=int(r["season"]), res=hs - as_, mk=-c, fade=(-1 if c < o else 1)))
    return out


def main():
    rows = model_rows()
    md = [r for r in rows if r["margin"] is not None]
    L = [f"# NFL 스프레드 정의 검정 — {dt.date.today()} · 2018~2025 정규시즌 · 마감 스프레드(nflverse) · 모델 후보는 {MIN_WEEK}주차~", "",
         "문턱(실행 전 고정): 2개 이상 시즌에서 같은 방향(50% 초과) & 전체 53% 이상. z = 50% 대비(|z| 2.6 미만은 여러 후보를 한꺼번에 본 우연 가능). 손익분기 52.4%.", "",
         "| 후보 | 경기 | 승-패(-무) | 적중 | z | 50% 넘긴 시즌 | 시즌별 |", "|---|---|---|---|---|---|---|"]
    res = []

    def add(lab, rs, side):
        ln, d = line(lab, rs, side); L.append(ln)
        if d:
            res.append(d)
    gap = lambda r: r["margin"] - r["mk"]
    add("D1 모델 마진 쪽(현행 · 전 경기)", md, lambda r: (1 if gap(r) > 0 else -1) if gap(r) else 0)
    for th in (1, 2, 3.5, 5):
        add(f"D1 모델 쪽 · 차 {th}+", md, lambda r, th=th: (1 if gap(r) > 0 else -1) if abs(gap(r)) >= th else 0)
    for th in (2, 3.5, 5):
        add(f"D2 모델 반대쪽 · 차 {th}+", md, lambda r, th=th: (-1 if gap(r) > 0 else 1) if abs(gap(r)) >= th else 0)
    add("D3 홈 언더독 +7 이상 → 홈(A7)", rows, lambda r: 1 if r["mk"] <= -7 else 0)
    add("D4 원정 휴식 우위 3일+ → 원정", rows, lambda r: -1 if r["ar"] - r["hr"] >= 3 else 0)
    add("D5 원정 언더독 → 원정", rows, lambda r: -1 if r["mk"] > 0 else 0)
    add("D6 언더독 전부", rows, lambda r: (-1 if r["mk"] > 0 else 1) if r["mk"] else 0)
    add("D8 페이버릿 전부(= 예측 승자 커버)", rows, lambda r: (1 if r["mk"] > 0 else -1) if r["mk"] else 0)
    add("D7 키 넘버 3·7 넘긴 이동 반대쪽(A6 · 2024~25)", a6_rows(), lambda r: r["fade"])
    # 2차 — 선수 연결
    player_feats(rows)
    L += ["", "## 2차 — 선수 연결(「그 팀 쪽」 승-패 · 47% 이하면 상대 쪽이 53%+)", "", "| 후보 | 경기 | 승-패(-무) | 적중 | z | 50% 넘긴 시즌 | 시즌별 |", "|---|---|---|---|---|---|---|"]
    n1 = len(res)

    def one(cond):
        def side(r):
            a, h = bool(cond(r, "a")), bool(cond(r, "h"))
            return 0 if a == h else (1 if h else -1)
        return side
    qd = lambda r: (r["qv_h"] - r["qv_a"]) if r.get("qv_h") is not None and r.get("qv_a") is not None else None
    add("Q1 선발 QB 값이 0.10+ 높은 팀", rows, lambda r: (1 if qd(r) >= 0.10 else -1 if qd(r) <= -0.10 else 0) if qd(r) is not None else 0)
    add("Q1 선발 QB 값이 0.05+ 높은 팀", rows, lambda r: (1 if qd(r) >= 0.05 else -1 if qd(r) <= -0.05 else 0) if qd(r) is not None else 0)
    add("Q2 QB 값이 0.05+ 높은데 언더독인 팀", rows, lambda r: (1 if (qd(r) >= 0.05 and r["mk"] < 0) else -1 if (qd(r) <= -0.05 and r["mk"] > 0) else 0) if qd(r) is not None else 0)
    add("Q3 타깃 1위 리시버 결장 첫 경기 팀", rows, one(lambda r, s: r.get("wr_" + s) == 1))
    add("Q4 타깃 1위 리시버 결장 2~3경기째 팀", rows, one(lambda r, s: r.get("wr_" + s) in (2, 3)))
    add("Q5 캐리 1위 러셔 결장 첫 경기 팀", rows, one(lambda r, s: r.get("rb_" + s) == 1))
    add("Q6 캐리 1위 러셔 결장 2~3경기째 팀", rows, one(lambda r, s: r.get("rb_" + s) in (2, 3)))
    add("Q7 첫 선발 QB 상대 7+ 페이버릿 → 페이버릿", rows, lambda r: (1 if (r.get("fs_a") and not r.get("fs_h") and r["mk"] >= 7) else -1 if (r.get("fs_h") and not r.get("fs_a") and r["mk"] <= -7) else 0))
    add("Q7b 첫 선발 QB 팀(라인 무관) → 상대", rows, lambda r: (1 if (r.get("fs_a") and not r.get("fs_h")) else -1 if (r.get("fs_h") and not r.get("fs_a")) else 0))
    for d in res[n1:]:
        if d["pct"] <= 47 and (d["tot"] - d["over"]) >= 2:
            d["ok"] = True; d["lab"] += " → 상대 쪽"; d["w"], d["l"] = d["l"], d["w"]; d["pct"] = 100 - d["pct"]; d["z"] = -d["z"]; d["over"] = d["tot"] - d["over"]
    # 겹침: 모델 반대쪽 3.5+ 가 언더독·홈 언더독과 얼마나 같은 경기인가
    f35 = [r for r in md if abs(gap(r)) >= 3.5]
    dog = sum(1 for r in f35 if r["mk"] and ((-1 if gap(r) > 0 else 1) == (-1 if r["mk"] > 0 else 1)))
    L += ["", f"겹침: 「모델 반대쪽 · 차 3.5+」 {len(f35)}경기 중 언더독 쪽 {dog}경기({100 * dog / max(1, len(f35)):.0f}%)", "",
          "## 문턱 통과(2개+ 시즌 50% 초과 & 전체 53%+)", ""]
    ok = [d for d in res if d["ok"]]
    L += [f"- {d['lab']}: {d['w']}-{d['l']} {d['pct']:.1f}% · z {d['z']:+.2f} · 시즌 {d['over']}/{d['tot']}" for d in ok] or ["- 없음"]
    out = os.path.join(N.DATA, f"spread_lab_{dt.date.today()}.md")
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L)); print(f"\nwrote {out}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
