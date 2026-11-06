"""B1·B3·B4 백테스트(2026-11-05 발행 세션 요청 · Paul 「모두 승인 · 로컬에서」 · 사전 등록 = pending_rules 2026-11-05 「[사전 등록 — 실행 전] B1·B3·B4」).
  python scripts/backtest_weather_qb.py
B1 비·뇌우(바람 15mph 미만) · B3 첫 선발 백업 QB 상대 큰 페이버릿 · B4 스프레드÷총점 상위 10%. B2(각도 겹침)는 집계 정리라 picks.angle_game_record.
데이터: data/cache/games.csv(nflverse — 마감 ML·spread_line·total_line·roof·wind·qb_id) · data/cache/hist/play_by_play_YYYY.csv.gz 의 weather 문자열(경기당 1행).
목표 변수: ML 잔차(그 쪽 실제 승 1/무 0.5/패 0 − 마감 무비그 확률) · 커버 마진(그 쪽 기준 결과 − 라인) · 총점 잔차(실제 − total_line).
검정: backtest_features.test('flag') — 같은 시즌-주 안 순열(조건 플래그를 섞음) · 시즌-주 묶음 부트스트랩 95%. 1차 가설 BH 보정.
판정: q ≤ 0.05 & 가설 방향 & 전(2018~23)·후(2024~25) 같은 부호 → 각도 후보 「제안」(등록은 Paul). 플래그 경기 < 100 이면 「방향만」(판정 없음)."""
import csv, gzip, os, random, re, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import backtest_features as BF  # noqa: E402

ROOT = os.path.dirname(HERE)
CACHE = os.path.join(ROOT, "data", "cache"); HIST = os.path.join(CACHE, "hist")
OUT = os.path.join(ROOT, "data", "backtest_weather_qb_2026-11-05.md")
RAIN = re.compile(r"rain|shower|thunder|storm|drizzle", re.I)
NOT_RAIN = re.compile(r"chance of|0%|no rain", re.I)
SNOW = re.compile(r"snow|sleet|flurr", re.I)   # 2026-11-05 복기/개선/수정 ② — 눈은 비 코호트에서 빼고 「눈」 꼬리표로 따로(방향만)


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def imp(o):
    o = f(o)
    if o is None or o == 0:
        return None
    return -o / (-o + 100) if o < 0 else 100 / (o + 100)


def weather_by_game():
    p = os.path.join(HIST, "weather_by_game.csv")
    if os.path.exists(p):
        return {r["game_id"]: r["weather"] for r in csv.DictReader(open(p, encoding="utf-8"))}
    out = {}
    for s in range(2017, 2026):
        src = os.path.join(HIST, f"play_by_play_{s}.csv.gz")
        if not os.path.exists(src):
            continue
        with gzip.open(src, "rt", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["game_id"] not in out and r.get("weather"):
                    out[r["game_id"]] = r["weather"]
        print(f"  pbp {s} weather", file=sys.stderr)
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["game_id", "weather"]); w.writerows(out.items())
    return out


def games():
    gs = []
    for g in csv.DictReader(open(os.path.join(CACHE, "games.csv"), encoding="utf-8")):
        if g["game_type"] != "REG" or not g["result"]:
            continue
        s = int(g["season"])
        if s < 2010 or s > 2025:
            continue
        a, h = imp(g["away_moneyline"]), imp(g["home_moneyline"])
        sl, tl = f(g["spread_line"]), f(g["total_line"])
        if a is None or h is None or sl is None or tl is None:
            continue
        g["ph"] = h / (a + h); g["sl"] = sl; g["tl"] = tl
        g["res"] = int(g["result"]); g["tot"] = int(g["total"]); g["s"] = s; g["wk"] = int(g["week"])
        gs.append(g)
    return gs


def fav_rows(gs, flag):
    """페이버릿 기준 행 — (cluster, season, flag, ML 잔차, 커버 마진)."""
    out = []
    for g in gs:
        home_fav = g["sl"] > 0 if g["sl"] != 0 else g["ph"] >= 0.5
        pf = g["ph"] if home_fav else 1 - g["ph"]
        r = g["res"] if home_fav else -g["res"]
        win = 1.0 if r > 0 else 0.5 if r == 0 else 0.0
        line = abs(g["sl"])
        out.append((f'{g["s"]}-{g["wk"]}', g["s"], int(flag(g)), win - pf, r - line, abs(g["sl"])))
    return out


def run(rows, ycol, rng):
    rs = [(r[0], r[1], r[2], r[ycol]) for r in rows]
    return BF.test(rs, "flag", rng)


def periods(rows):
    return {"합": rows, "장기 2010~17": [r for r in rows if r[1] <= 2017],
            "전 2018~23": [r for r in rows if 2018 <= r[1] <= 2023], "후 2024~25": [r for r in rows if r[1] >= 2024]}


def main():
    rng = random.Random(20261105)
    gs = games()
    wx = weather_by_game()
    res, lines = [], []

    def add(name, hyp_sign, rows, ycol, label, period_filter=None, primary=False, cluster_bin=False):
        for lab, rs in periods(rows).items():
            if period_filter and not period_filter(lab):
                continue
            n = sum(r[2] for r in rs)
            if n == 0:
                continue
            obs, lo, hi, p = (lambda t: (t[0], t[1][0], t[1][1], t[2]))(run(rs, ycol, rng))
            res.append(dict(name=name, label=label, period=lab, n=n, obs=obs, lo=lo, hi=hi, p=p, hyp=hyp_sign, primary=primary))

    # B1 — 비·뇌우 · 실외/open · wind<15 · weather 문자열 2017~25 만 있음 → 판정 표본 2018~25(장기 구간 없음)
    def b1(g):
        w = wx.get(g["game_id"], "")
        return (g["roof"] in ("outdoors", "open") and f(g["wind"]) is not None and f(g["wind"]) < 15
                and bool(RAIN.search(w)) and not NOT_RAIN.search(w) and not SNOW.search(w))

    def snow(g):
        w = wx.get(g["game_id"], "")
        return g["roof"] in ("outdoors", "open") and bool(SNOW.search(w)) and not NOT_RAIN.search(w)
    gs_w = [g for g in gs if g["game_id"] in wx and g["s"] >= 2018]
    tot_rows = [(f'{g["s"]}-{g["wk"]}', g["s"], int(b1(g)), g["tot"] - g["tl"]) for g in gs_w]
    fr = fav_rows(gs_w, b1)
    add("B1 비·뇌우", -1, [(r[0], r[1], r[2], r[3]) for r in tot_rows], 3, "총점 잔차(점)", primary=True)
    add("B1 비·뇌우 · 7+ 페이버릿", -1, [(r[0], r[1], int(r[2] and r[5] >= 7), r[3], r[4]) for r in fr], 4, "페이버릿 커버 마진(점)", primary=True)
    add("B1 비·뇌우(2차)", 0, fr, 3, "페이버릿 ML 잔차")
    add("B1 꼬리표 눈(방향만)", -1, [(f'{g["s"]}-{g["wk"]}', g["s"], int(snow(g)), g["tot"] - g["tl"]) for g in gs_w], 3, "총점 잔차(점)", lambda lab: lab == "합")

    # B3 — 선발 QB 첫 정규시즌 선발(2010~ 기준) & 그 팀 직전 경기 선발과 다름 · 상대가 7+ 페이버릿
    started, last_qb, used = set(), {}, defaultdict(set)
    first = {}
    for g in sorted(gs, key=lambda g: (g["s"], g["wk"])):
        for side in ("away", "home"):
            t, q = g[f"{side}_team"], g.get(f"{side}_qb_id") or ""
            first[(g["game_id"], side)] = (q and q not in started and last_qb.get(t) not in (None, q), len(used[(t, g["s"])]) >= 2)
        for side in ("away", "home"):
            t, q = g[f"{side}_team"], g.get(f"{side}_qb_id") or ""
            if q:
                started.add(q); last_qb[t] = q; used[(t, g["s"])].add(q)

    def b3(g, third=False):
        home_fav = g["sl"] > 0
        dog = "away" if home_fav else "home"
        fs, is3 = first.get((g["game_id"], dog), (False, False))
        return abs(g["sl"]) >= 7 and fs and (is3 if third else True)
    gs11 = [g for g in gs if g["s"] >= 2011]   # ③ 2010 은 경력 조회용(2009 이전 선발이 안 보여 베테랑이 「첫 선발」로 잡힘)
    fr3 = fav_rows(gs11, b3)
    add("B3 첫 선발 백업 QB 상대 7+ 페이버릿", 1, fr3, 3, "페이버릿 ML 잔차", primary=True)
    add("B3 첫 선발 백업 QB 상대 7+ 페이버릿(2차)", 1, fr3, 4, "페이버릿 커버 마진(점)")
    add("B3 꼬리표 3번 QB(방향만)", 1, fav_rows(gs11, lambda g: b3(g, True)), 3, "페이버릿 ML 잔차", lambda lab: lab == "합")

    # B4 — |spread| / total 시즌 내 상위 10%
    cut = {}
    for s in {g["s"] for g in gs}:
        v = sorted(abs(g["sl"]) / g["tl"] for g in gs if g["s"] == s and g["tl"])
        cut[s] = v[int(len(v) * 0.9)]
    b4 = lambda g: g["tl"] and abs(g["sl"]) / g["tl"] >= cut[g["s"]]
    fr4 = fav_rows(gs, b4)
    add("B4 스프레드÷총점 상위 10%", -1, fr4, 4, "페이버릿 커버 마진(점)", primary=True)
    add("B4 스프레드÷총점 상위 10%(2차)", 0, fr4, 3, "페이버릿 ML 잔차")
    # ④ 층화 대조 — 같은 |spread| 구간(3·3.5~6.5·7~9.5·10+ · 3 미만은 「<3」) 안에서 상위 10% vs 비상위(순열은 구간 안에서 섞음)
    sbin = lambda v: "<3" if v < 3 else "3" if v == 3 else "3.5~6.5" if v < 7 else "7~9.5" if v < 10 else "10+"
    strat = [(sbin(r[5]), r[1], r[2], r[3], r[4], r[5]) for r in fr4]
    add("B4 층화 대조(같은 스프레드 구간 안)", -1, strat, 4, "페이버릿 커버 마진(점)", lambda lab: lab == "합")
    add("B4 보조 · 상위 10% & (비 또는 바람 15+)(방향만)", -1,
        fav_rows([g for g in gs_w], lambda g: b4(g) and (b1(g) or (g["roof"] in ("outdoors", "open") and (f(g["wind"]) or 0) >= 15))),
        4, "페이버릿 커버 마진(점)", lambda lab: lab == "합")

    # BH — 1차(합 구간 · 보조/방향만 제외)
    prim = [r for r in res if r["period"] == "합" and r.get("primary")]   # ① 1차 4개(B1 총점 · B1 7+ 커버 · B3 ML · B4 커버)만 BH
    ps = sorted(prim, key=lambda r: r["p"]); m = len(ps); q = 1.0
    for i in range(m - 1, -1, -1):
        q = min(q, ps[i]["p"] * m / (i + 1)); ps[i]["q"] = q
    L = ["# 백테스트 — 비·뇌우 · 첫 선발 백업 QB · 스프레드÷총점 (2026-11-05)", "",
         "- 사전 등록: scripts/pending_rules.md 2026-11-05 「[사전 등록 — 실행 전] B1·B3·B4」(실행 전 커밋)",
         "- 데이터: nflverse games.csv(마감) · pbp weather(2017~25 로컬 캐시 — B1 은 2018~25 만) · 정규시즌 2010~2025",
         "- 판정: 1차 4개(B1 총점 잔차 · B1 7+ 커버 마진 · B3 페이버릿 ML 잔차 · B4 페이버릿 커버 마진)만 BH — q≤0.05 & 가설 방향 & 전·후 같은 부호(B4 는 같은 스프레드 구간 층화 대조도 통과) → 각도 후보 제안 · 플래그 경기 <100 = 방향만 · 나머지는 2차·보조(판정 없음)", "",
         "| 가설 | 목표 | 구간 | 플래그 경기 | 효과 | 95% 구간 | 순열 p | BH q | 판정 |", "|---|---|---|---|---|---|---|---|---|"]
    by = defaultdict(dict)
    for r in res:
        by[(r["name"], r["label"])][r["period"]] = r
    for (nm, lab), d in by.items():
        a = d.get("합")
        sign_ok = None
        if a and "전 2018~23" in d and "후 2024~25" in d:
            sg = lambda v: (v > 0) - (v < 0)
            sign_ok = sg(d["전 2018~23"]["obs"]) == sg(d["후 2024~25"]["obs"])
        for per, r in d.items():
            verdict = ""
            if per == "합":
                if not r.get("primary"):
                    verdict = "2차·보조(판정 없음)" if r["n"] >= 100 and "방향만" not in nm else "방향만(n<100 또는 꼬리표)"
                elif r["n"] < 100:
                    verdict = "방향만(n<100)"
                else:
                    hyp_ok = r["hyp"] == 0 or (r["obs"] > 0) == (r["hyp"] > 0)
                    strat_ok = True
                    if nm.startswith("B4"):
                        st = by.get(("B4 층화 대조(같은 스프레드 구간 안)", lab), {}).get("합")
                        strat_ok = bool(st) and st["p"] <= 0.05 and (st["obs"] < 0)
                    verdict = ("통과 → 각도 후보 제안" if r.get("q", 1) <= 0.05 and hyp_ok and sign_ok and strat_ok
                               else "미달 — 서술 전용" + ("(층화 대조 미통과)" if nm.startswith("B4") and not strat_ok else ""))
            L.append(f'| {nm} | {lab} | {per} | {r["n"]} | {r["obs"]:+.3f} | [{r["lo"]:+.3f}, {r["hi"]:+.3f}] | {r["p"]:.3f} | '
                     + (f'{r["q"]:.3f}' if "q" in r else "") + f' | {verdict} |')
    L += ["", "- 역사 자료가 없어 하지 않은 것: 개장→마감 총점 이동(B1) · 경기 당일 라인 되돌림(B3) — nflverse 에 개장 라인 없음 → 2026 line_history 전향 관찰로만.",
          "- 번개 지연: 원천 없음.", "- B2(A3·A6·A7 겹침): A3·A6 은 개장 라인 필요 → 역사 불가. 2026 페이퍼 경기 단위 집계(picks.angle_game_record)로 대신."]
    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
