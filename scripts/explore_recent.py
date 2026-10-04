"""최근 3시즌(2023~2025) 탐색 — 2026 관찰 후보 찾기(2026-10-04 Paul 「1번으로 — 최근 3년만으로 쓸만한 것 찾기」).
  python explore_recent.py
⚠️ 탐색이다 — 2023~2025 는 이 탐색에 쓰였으므로 이후 「검증 구간」으로 쓸 수 없다. 결과는 증명이 아니라 2026 전향 관찰 후보.
판정 대상: 마감 라인 대비 ATS(그 팀이 커버했나) · O/U. 각 항목의 p(이항 양측) → BH 보정 q(전체 항목 수 기준) · 시즌별 방향 일관성.
후보 = q ≤ 0.10, 또는 (p ≤ 0.05 이고 3시즌 모두 같은 방향 · n ≥ 60). 둘 다 아니면 「잡음」.
항목 묶음: ① 라인·일정 상황 ② 「운」 지표(턴오버 마진·접전 성적·피타고리안·레드존) — 시장이 운을 실력으로 과대평가하는가 ③ 실력 지표(EPA·드라이브 득점) 대 라인 ④ 총점(날씨·지붕·라인 크기·양 팀 공수)."""
import math, os, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nfl_pull as N   # noqa: E402
import stat_research as SR   # noqa: E402

SEASONS = (2023, 2024, 2025)
f, tm = SR.f, SR.tm


def team_asof(season):
    """{(team, week): 피처} — 그 주 전까지 이번 시즌 경기만(3경기 미만이면 없음)."""
    T, _P, _n = SR.load(season)
    games = [g for g in N.rd(os.path.join(N.CACHE, "games.csv")) if g["season"] == str(season) and g["game_type"] == "REG" and f(g.get("result")) is not None]
    off, de = defaultdict(list), defaultdict(list)
    for (gid, wk, pt, dt), x in T.items():
        off[pt].append((wk, gid, x)); de[dt].append((wk, gid, x))
    res = defaultdict(list)            # team → [(week, pf, pa, cover_margin)]
    for g in games:
        h, a, wk = tm(g["home_team"]), tm(g["away_team"]), int(g["week"])
        hs, as_, sp = f(g["home_score"]), f(g["away_score"]), f(g["spread_line"])
        cm = (f(g["result"]) - sp) if sp is not None else None
        res[h].append((wk, hs, as_, cm)); res[a].append((wk, as_, hs, -cm if cm is not None else None))
    feats = {}
    for t in set(off) | set(res):
        for wk in range(1, 23):
            o = [x for w, _g, x in off[t] if w < wk]; d = [x for w, _g, x in de[t] if w < wk]
            r = sorted([v for v in res[t] if v[0] < wk])
            if len(r) < 3 or not o or not d:
                continue
            gp = len(r)
            pf, pa = sum(v[1] for v in r), sum(v[2] for v in r)
            wins = sum(1 for v in r if v[1] > v[2]); close = [v for v in r if abs(v[1] - v[2]) <= 8]
            pyth = pf ** 2.37 / (pf ** 2.37 + pa ** 2.37) if pf + pa else 0.5
            give = sum(x.get("to", 0) for x in o); take = sum(x.get("to", 0) for x in d)
            rz, rztd = sum(x.get("rz", 0) for x in o), sum(x.get("rz_td", 0) for x in o)
            covers = [v[3] for v in r if v[3] is not None and v[3] != 0]
            feats[(t, wk)] = dict(
                epa_o=sum(x["epa"] for x in o) / sum(x["n"] for x in o), epa_d=sum(x["epa"] for x in d) / sum(x["n"] for x in d),
                ppd_o=sum(x.get("dr_pts", 0) for x in o) / max(sum(x.get("dr", 0) for x in o), 1),
                ppd_d=sum(x.get("dr_pts", 0) for x in d) / max(sum(x.get("dr", 0) for x in d), 1),
                plays=sum(x["n"] for x in o) / gp, to_m=(take - give) / gp,
                close_net=sum(1 if v[1] > v[2] else -1 for v in close if v[1] != v[2]),
                luck=wins / gp - pyth, rz_rate=(rztd / rz) if rz else None,
                ats=(sum(1 for c in covers if c > 0) / len(covers)) if len(covers) >= 4 else None,
                last_margin=r[-1][1] - r[-1][2])
    return games, feats


def binom_p(w, n):
    """양측 이항 p(정규 근사 + 연속 보정)."""
    if n == 0:
        return 1.0
    z = (abs(w - n / 2) - 0.5) / math.sqrt(n / 4)
    return math.erfc(max(z, 0) / math.sqrt(2))


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    rows = []        # (season, game dict, home feats, away feats)
    qcut = {}
    for s in SEASONS:
        games, F = team_asof(s)
        for g in games:
            h, a, wk = tm(g["home_team"]), tm(g["away_team"]), int(g["week"])
            fh, fa = F.get((h, wk)), F.get((a, wk))
            rows.append((s, g, fh, fa))
    # 분위 문턱(3시즌 전체 팀-주 분포)
    allf = [x for _s, _g, fh, fa in rows for x in (fh, fa) if x]
    def q(key, p):
        v = sorted(x[key] for x in allf if x.get(key) is not None)
        return v[int(p * (len(v) - 1))] if v else None
    for k in ("to_m", "luck", "rz_rate", "epa_o", "epa_d", "ppd_o", "ppd_d", "plays"):
        qcut[k] = (q(k, 0.25), q(k, 0.75))

    tests = []   # (묶음, 이름, [(season, win_bool)])

    def add(group, name, outcomes):
        tests.append((group, name, [o for o in outcomes if o[1] is not None]))

    def ats(s, g, team):
        sp, res = f(g["spread_line"]), f(g["result"])
        if sp is None or res is None or res == sp:
            return None
        return (res > sp) if team == tm(g["home_team"]) else (res < sp)

    def ou(g):
        tl, tot = f(g["total_line"]), f(g["total"])
        if tl is None or tot is None or tot == tl:
            return None
        return tot > tl

    def side_rows(cond):
        """cond(s, g, team, ft, fo, is_home) → True 면 그 팀 ATS."""
        out = []
        for s, g, fh, fa in rows:
            h, a = tm(g["home_team"]), tm(g["away_team"])
            for team, ft, fo, ih in ((h, fh, fa, True), (a, fa, fh, False)):
                try:
                    if cond(s, g, team, ft, fo, ih):
                        out.append((s, ats(s, g, team)))
                except (TypeError, KeyError):
                    pass
        return out

    line = lambda g, ih: (-f(g["spread_line"]) if ih else f(g["spread_line"]))     # 그 팀 베팅 라인(+ = 받음)
    # ① 라인·일정 상황
    add("①상황", "홈 언더독", side_rows(lambda s, g, t, ft, fo, ih: ih and line(g, ih) > 0))
    add("①상황", "홈 언더독 +3~+7", side_rows(lambda s, g, t, ft, fo, ih: ih and 3 <= line(g, ih) <= 7))
    add("①상황", "원정 페이버릿 −7 이상", side_rows(lambda s, g, t, ft, fo, ih: (not ih) and line(g, ih) <= -7))
    add("①상황", "언더독 +10 이상", side_rows(lambda s, g, t, ft, fo, ih: line(g, ih) >= 10))
    add("①상황", "디비전 경기 언더독", side_rows(lambda s, g, t, ft, fo, ih: g["div_game"] == "1" and line(g, ih) > 0))
    add("①상황", "휴식 3일+ 우위 팀", side_rows(lambda s, g, t, ft, fo, ih: (f(g["home_rest" if ih else "away_rest"]) or 7) - (f(g["away_rest" if ih else "home_rest"]) or 7) >= 3))
    add("①상황", "바이 뒤 팀(휴식 13+)", side_rows(lambda s, g, t, ft, fo, ih: (f(g["home_rest" if ih else "away_rest"]) or 7) >= 13))
    add("①상황", "목요일 원정 팀", side_rows(lambda s, g, t, ft, fo, ih: g["weekday"] == "Thursday" and not ih))
    add("①상황", "월요일 홈 팀", side_rows(lambda s, g, t, ft, fo, ih: g["weekday"] == "Monday" and ih))
    add("①상황", "프라임타임(20시+ ET) 페이버릿", side_rows(lambda s, g, t, ft, fo, ih: (g.get("gametime") or "00:00") >= "20:00" and line(g, ih) < 0))
    add("①상황", "12월~ 홈 언더독", side_rows(lambda s, g, t, ft, fo, ih: ih and line(g, ih) > 0 and int(g["week"]) >= 14))
    add("①상황", "직전 경기 17점+ 대패 팀", side_rows(lambda s, g, t, ft, fo, ih: ft["last_margin"] <= -17))
    add("①상황", "직전 경기 17점+ 대승 팀", side_rows(lambda s, g, t, ft, fo, ih: ft["last_margin"] >= 17))
    add("①상황", "시즌 ATS 70%+ 팀(4경기+)", side_rows(lambda s, g, t, ft, fo, ih: ft["ats"] is not None and ft["ats"] >= 0.7))
    add("①상황", "시즌 ATS 30%- 팀(4경기+)", side_rows(lambda s, g, t, ft, fo, ih: ft["ats"] is not None and ft["ats"] <= 0.3))
    # ② 운 지표 — 「운 좋은 팀」은 시장이 과대평가하나(→ 그 팀 ATS 낮음) · 운 나쁜 팀은 과소평가하나
    add("②운", "턴오버 마진 상위 25% 팀", side_rows(lambda s, g, t, ft, fo, ih: ft["to_m"] >= qcut["to_m"][1]))
    add("②운", "턴오버 마진 하위 25% 팀", side_rows(lambda s, g, t, ft, fo, ih: ft["to_m"] <= qcut["to_m"][0]))
    add("②운", "접전(8점 이내) 순승 +2 이상 팀", side_rows(lambda s, g, t, ft, fo, ih: ft["close_net"] >= 2))
    add("②운", "접전 순패 −2 이하 팀", side_rows(lambda s, g, t, ft, fo, ih: ft["close_net"] <= -2))
    add("②운", "피타고리안 대비 승률 운 상위 25% 팀", side_rows(lambda s, g, t, ft, fo, ih: ft["luck"] >= qcut["luck"][1]))
    add("②운", "피타고리안 대비 승률 운 하위 25% 팀", side_rows(lambda s, g, t, ft, fo, ih: ft["luck"] <= qcut["luck"][0]))
    add("②운", "레드존 TD% 상위 25% 팀", side_rows(lambda s, g, t, ft, fo, ih: ft["rz_rate"] is not None and ft["rz_rate"] >= qcut["rz_rate"][1]))
    add("②운", "레드존 TD% 하위 25% 팀", side_rows(lambda s, g, t, ft, fo, ih: ft["rz_rate"] is not None and ft["rz_rate"] <= qcut["rz_rate"][0]))
    # ③ 실력 지표 대 라인
    net = lambda x: x["epa_o"] - x["epa_d"]
    add("③실력", "EPA 순우위(공−수) 큰 쪽이 언더독", side_rows(lambda s, g, t, ft, fo, ih: net(ft) - net(fo) >= 0.05 and line(g, ih) > 0))
    add("③실력", "EPA 순우위 큰 쪽(라인 무관)", side_rows(lambda s, g, t, ft, fo, ih: net(ft) - net(fo) >= 0.10))
    add("③실력", "드라이브 득점 차 우위 쪽이 언더독", side_rows(lambda s, g, t, ft, fo, ih: (ft["ppd_o"] - ft["ppd_d"]) - (fo["ppd_o"] - fo["ppd_d"]) >= 0.5 and line(g, ih) > 0))
    add("③실력", "실력 상위 25% 공격인데 운 하위(턴오버 하위 25%)", side_rows(lambda s, g, t, ft, fo, ih: ft["epa_o"] >= qcut["epa_o"][1] and ft["to_m"] <= qcut["to_m"][0]))
    # ④ 총점
    def ou_rows(cond):
        out = []
        for s, g, fh, fa in rows:
            try:
                if cond(s, g, fh, fa):
                    out.append((s, ou(g)))
            except (TypeError, KeyError):
                pass
        return out
    outdoor = lambda g: g["roof"] in ("outdoors", "open")
    add("④총점(오버)", "총점 라인 ≤40", ou_rows(lambda s, g, fh, fa: f(g["total_line"]) <= 40))
    add("④총점(오버)", "총점 라인 ≥50", ou_rows(lambda s, g, fh, fa: f(g["total_line"]) >= 50))
    add("④총점(오버)", "실외 바람 15mph+", ou_rows(lambda s, g, fh, fa: outdoor(g) and (f(g["wind"]) or 0) >= 15))
    add("④총점(오버)", "실외 기온 32°F 이하", ou_rows(lambda s, g, fh, fa: outdoor(g) and f(g["temp"]) is not None and f(g["temp"]) <= 32))
    add("④총점(오버)", "돔·닫힌 지붕", ou_rows(lambda s, g, fh, fa: g["roof"] in ("dome", "closed")))
    add("④총점(오버)", "디비전 경기", ou_rows(lambda s, g, fh, fa: g["div_game"] == "1"))
    add("④총점(오버)", "프라임타임(20시+ ET)", ou_rows(lambda s, g, fh, fa: (g.get("gametime") or "00:00") >= "20:00"))
    add("④총점(오버)", "양 팀 공격 EPA 상위 25%", ou_rows(lambda s, g, fh, fa: fh["epa_o"] >= qcut["epa_o"][1] and fa["epa_o"] >= qcut["epa_o"][1]))
    add("④총점(오버)", "양 팀 수비 EPA 상위 25%(잘 막음)", ou_rows(lambda s, g, fh, fa: fh["epa_d"] <= qcut["epa_d"][0] and fa["epa_d"] <= qcut["epa_d"][0]))
    add("④총점(오버)", "양 팀 플레이 수 상위 25%(빠른 템포)", ou_rows(lambda s, g, fh, fa: fh["plays"] >= qcut["plays"][1] and fa["plays"] >= qcut["plays"][1]))
    add("④총점(오버)", "양 팀 레드존 TD% 하위 25%(운 나쁨)", ou_rows(lambda s, g, fh, fa: fh["rz_rate"] <= qcut["rz_rate"][0] and fa["rz_rate"] <= qcut["rz_rate"][0]))
    # 통계
    res = []
    for grp, name, outs in tests:
        n = len(outs); w = sum(1 for _, x in outs if x)
        p = binom_p(w, n)
        by = defaultdict(lambda: [0, 0])
        for s, x in outs:
            by[s][0 if x else 1] += 1
        sign = 1 if w >= n / 2 else -1
        cons = sum(1 for a_, b_ in by.values() if (a_ - b_) * sign > 0)
        res.append(dict(grp=grp, name=name, n=n, w=w, p=p, cons=cons, seasons=len(by), by=dict(by)))
    m = len(res)
    order = sorted(range(m), key=lambda i: res[i]["p"])
    qv = [0.0] * m; prev = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        prev = min(prev, res[i]["p"] * m / rank); qv[i] = prev
    for i, r in enumerate(res):
        r["q"] = qv[i]
        pct = 100 * r["w"] / r["n"] if r["n"] else 0
        r["cand"] = r["n"] >= 60 and (r["q"] <= 0.10 or (r["p"] <= 0.05 and r["cons"] == 3))
        r["pct"] = pct
    print(f"■ 최근 3시즌(2023~2025) 탐색 — 항목 {m}개 · ATS/O-U 손익분기 52.4% · 후보 = q≤0.10 또는 (p≤0.05 & 3시즌 같은 방향 & n≥60)")
    print("묶음 | 항목 | n | 적중(ATS는 그 팀 커버 / 총점은 오버) | p | q(BH) | 시즌 일관 | 시즌별 W-L | 판정")
    for r in sorted(res, key=lambda r: r["p"]):
        bys = " ".join(f"{s % 100}:{a_}-{b_}" for s, (a_, b_) in sorted(r["by"].items()))
        side = "" if r["pct"] >= 50 else " (반대로 걸면 " + f"{100 - r['pct']:.1f}%)"
        print(f"{r['grp']} | {r['name']} | {r['n']} | {r['w']}-{r['n'] - r['w']} {r['pct']:.1f}%{side} | {r['p']:.3f} | {r['q']:.2f} | {r['cons']}/{r['seasons']} | {bys} | "
              + ("★ 2026 관찰 후보" if r["cand"] else "잡음"))


if __name__ == "__main__":
    main()
