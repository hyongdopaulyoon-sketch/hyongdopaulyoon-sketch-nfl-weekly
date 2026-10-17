"""키커 엣지 백테스트(2026-10-17 Paul 「선수·팀 위주로 다시 찾아」 — P6 후보 확장): pbp 에서 FG 시도를 뽑아 팀-시즌 as-of FG% 를 만들고
접전 라인(|스프레드|≤3)에서 「키커 나쁜 팀의 상대」 ML/ATS 를 2018~25(+2026 표본 외)로 잰다. 사전 고정 변형 4개(실행 전 확정):
  P6a 시즌 FG% <80%(10킥+) & |라인|≤3 → 상대   P6b 같은 조건 라인 무관 → 상대   P6c FG% ≥90%(10킥+) & |라인|≤3 → 그 팀   P6d 40야드+ FG% <65%(8킥+) & |라인|≤3 → 상대
  python scripts/kicker_edge.py    → data/cache/hist/fg_attempts.csv(캐시) + 표"""
import csv, gzip, collections, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); CACHE = os.path.join(ROOT, "data", "cache"); HIST = os.path.join(CACHE, "hist")


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def pimp(am):
    am = f(am)
    if am is None:
        return None
    return 100 / (am + 100) if am > 0 else -am / (-am + 100)


def dec(am):
    am = f(am); return 1 + am / 100 if am > 0 else 1 + 100 / -am


def extract(seasons):
    out = os.path.join(HIST, "fg_attempts.csv")
    have = {}
    if os.path.exists(out):
        for r in csv.DictReader(open(out, encoding="utf-8-sig")):
            have.setdefault(int(r["season"]), []).append(r)
    rows = [r for s in have for r in have[s]]
    for s in seasons:
        if s in have:
            continue
        src = os.path.join(HIST, f"play_by_play_{s}.csv.gz")
        if not os.path.exists(src):
            src = os.path.join(CACHE, f"play_by_play_{s}.csv.gz")
        if not os.path.exists(src):
            print("  pbp 없음", s); continue
        n = 0
        with gzip.open(src, "rt", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r.get("season_type", "REG") != "REG" or f(r.get("field_goal_attempt")) != 1:
                    continue
                rows.append(dict(season=s, week=int(r["week"]), team=r["posteam"], kicker=r.get("kicker_player_id", ""), dist=f(r.get("kick_distance")) or 0,
                                 made=1 if r.get("field_goal_result") == "made" else 0)); n += 1
        print(f"  {s}: FG 시도 {n}")
    with open(out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["season", "week", "team", "kicker", "dist", "made"]); w.writeheader(); w.writerows(rows)
    return rows


def main():
    seasons = list(range(2018, 2027))
    fg = extract(seasons)
    by = collections.defaultdict(list)
    for r in fg:
        by[(int(r["season"]), r["team"])].append((int(r["week"]), float(r["dist"]), int(r["made"])))
    G = [g for g in csv.DictReader(open(os.path.join(CACHE, "games.csv"), encoding="utf-8-sig")) if g["game_type"] == "REG" and g.get("result")]
    ML = collections.defaultdict(list); ATS = collections.defaultdict(list)
    for g in G:
        s, w = int(g["season"]), int(g["week"])
        if s < 2018 or w < 5:
            continue
        h, a = g["home_team"], g["away_team"]; sp = f(g["spread_line"]); res = f(g["result"])
        ph, pa = pimp(g["home_moneyline"]), pimp(g["away_moneyline"])
        if ph is None or pa is None or res == 0 or sp is None:
            continue
        t_ = ph + pa; ph, pa = ph / t_, pa / t_
        side = {h: (res > 0, ph, dec(g["home_moneyline"])), a: (res < 0, pa, dec(g["away_moneyline"]))}
        tag = "2026" if s == 2026 else "2018-25"

        def add(name, team):
            ML[(name, tag)].append((s,) + side[team])
            if res - sp != 0:
                ATS[(name, tag)].append((s, ((res - sp) > 0) == (team == h)))
        for t, opp in ((h, a), (a, h)):
            ks = [x for x in by.get((s, t), []) if x[0] < w]
            att = len(ks); md = sum(x[2] for x in ks)
            lng = [x for x in ks if x[1] >= 40]; la, lm = len(lng), sum(x[2] for x in lng)
            close = abs(sp) <= 3
            if att >= 10 and md / att < .80:
                if close:
                    add("P6a FG% <80%(10킥+) & |라인|≤3 → 상대", opp)
                add("P6b FG% <80%(10킥+) 전 경기 → 상대", opp)
            if att >= 10 and md / att >= .90 and close:
                add("P6c FG% ≥90%(10킥+) & |라인|≤3 → 그 팀", t)
            if la >= 8 and lm / la < .65 and close:
                add("P6d 40야드+ FG% <65%(8킥+) & |라인|≤3 → 상대", opp)
    print("| 가설 | 구간 | n | W-L | 실제 | 시장 | 잔차 | z | ML 수익 | ATS | 시즌 +/n |\n|---|---|---|---|---|---|---|---|---|---|---|")
    for (name, tag) in sorted(ML):
        xs = ML[(name, tag)]; n = len(xs); w = sum(1 for x in xs if x[1]); e = sum(x[2] for x in xs); var = sum(x[2] * (1 - x[2]) for x in xs)
        pnl = sum((x[3] - 1) if x[1] else -1 for x in xs) / n; bys = collections.defaultdict(lambda: [0, 0.0])
        for s_, won, p, _ in xs:
            bys[s_][0] += won; bys[s_][1] += p
        pos = sum(1 for s_, (ww, ee) in bys.items() if ww > ee)
        at = ATS.get((name, tag), []); aw = sum(1 for _, ok in at if ok)
        print(f"| {name} | {tag} | {n} | {w}-{n - w} | {w / n:.1%} | {e / n:.1%} | {100 * (w / n - e / n):+.1f}%p | {(w - e) / math.sqrt(var) if var else 0:+.2f} | {100 * pnl:+.1f}% | {aw}-{len(at) - aw} {100 * aw / len(at) if at else 0:.0f}% | {pos}/{len(bys)} |")
    if ("P6a FG% <80%(10킥+) & |라인|≤3 → 상대", "2018-25") in ML:
        bys = collections.defaultdict(lambda: [0, 0, 0.0])
        for s_, won, p, _ in ML[("P6a FG% <80%(10킥+) & |라인|≤3 → 상대", "2018-25")]:
            bys[s_][0] += won; bys[s_][1] += 1; bys[s_][2] += p
        print("P6a 시즌별:", {s_: f"{v[0]}-{v[1] - v[0]} (시장 {100 * v[2] / v[1]:.0f}%)" for s_, v in sorted(bys.items())})


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
