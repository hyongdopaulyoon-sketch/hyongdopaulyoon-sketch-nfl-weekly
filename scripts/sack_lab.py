# -*- coding: utf-8 -*-
"""sack_lab.py — 색(sack) 재점검(2026-11-22 Paul 「nfl에서 색이 중요한 것 같은데 저번에 빼버렸는데 다시 점검해서 넣어야 할 듯」 → 계획 「다 추천대로」).

    python scripts/sack_lab.py   → data/sack_lab_<오늘>.md      (hex_baseline.json 은 건드리지 않는다)

배경: 「저번에 뺀 것」 = A10(색률 상위 8 수비의 **상대** ML · 11/15 폐기 20픽 7-13). 색 값 자체는 수비 표·육각형 「패스 보호」(색 허용률)에 남아 있다.
검정 세 가지(정의·문턱 실행 전 고정 · 전부 그 경기 전까지의 값):
  ① 육각형 「패스러시」 재료 후보 — 승패·점수차·커버 상관 비교(4주차~ · 두 팀 값이 다 있는 경기):
     A 지금: 뛰는 패스러셔 압박 상위 3명의 경기당 압박 합
     B A + 그 3명의 경기당 색 합(z 평균)
     C 팀 수비 색률(색 ÷ 상대 드롭백)
     D A + C(z 평균)
     문턱: 승패 상관이 A 보다 높고 커버 상관이 A 보다 나쁘지 않으면(−0.01 안) 교체 후보.
  ② 색 미스매치: 수비 색률 상위 8 & 상대 공격 색 허용률 상위 8(많이 내주는 쪽) → 그 수비 팀 쪽 (5주차~ · 두 팀 다 해당이면 제외)
  ③ 색률 상위 8 수비 팀 쪽(A10 의 반대 방향 · 5주차~ · 두 팀 다 해당이면 제외)
     ②③ 문턱(육각형 검정과 같음): 스프레드 2개+ 시즌 50% 초과 & 전체 53%+ · 47% 이하면 상대 쪽. 승-패·시장 대비 잔차(무비그 ML)는 값으로 같이.
     2018~2025 와 2026(올해)을 따로 적는다.
색률 = pbp 드롭백 중 색(sack=1) · 선수 압박·색 = PFR advstats def(주간) · 출전 판정 = 그 경기 수비 스냅 기록.
"""
import csv, datetime as dt, gzip, io, math, os, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfl_pull as N  # noqa: E402
import team_hex as TH  # noqa: E402

SEASONS = list(range(2018, 2027))
TOP = 8


def _open(p):
    return io.TextIOWrapper(gzip.open(p, "rb"), encoding="utf-8-sig", newline="") if p.endswith(".gz") else open(p, encoding="utf-8-sig", newline="")


def season_data(season):
    """→ off[t][wk] = [드롭백, 색 허용] · dfn[t][wk] = [상대 드롭백, 색] · pl[t][wk][이름] = [압박, 색, 1] · snap[(gid, t)] = 수비 스냅 있는 이름(정규화)"""
    off = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0])); dfn = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    pp = TH._p("play_by_play", season)
    with _open(pp) as f:
        for x in csv.DictReader(f):
            if x.get("season_type", "REG") != "REG" or x.get("qb_dropback") != "1" or not x.get("posteam") or not x.get("defteam"):
                continue
            wk = int(x["week"]); s = 1.0 if x.get("sack") == "1" else 0.0
            o = off[x["posteam"]][wk]; o[0] += 1; o[1] += s
            d = dfn[x["defteam"]][wk]; d[0] += 1; d[1] += s
    pl = defaultdict(lambda: defaultdict(dict)); dplay = defaultdict(set)
    dp = TH._p("advstats_week_def", season)
    if dp:
        with _open(dp) as f:
            for r in csv.DictReader(f):
                if r.get("game_type") != "REG":
                    continue
                t = N.ESPN2NV.get(r["team"], r["team"]); wk = int(r.get("week") or 0)
                pl[t][wk][r["pfr_player_name"]] = [N.fnum(r.get("def_pressures")) or 0.0, N.fnum(r.get("def_sacks")) or 0.0]
                dplay[(r["game_id"], t)].add(r["pfr_player_name"])
    snap = defaultdict(set)
    sp = TH._p("snap_counts", season)
    if sp:
        with _open(sp) as f:
            for r in csv.DictReader(f):
                if r.get("game_type") == "REG" and (N.fnum(r.get("defense_snaps")) or 0) > 0:
                    snap[(r["game_id"], N.ESPN2NV.get(r["team"], r["team"]))].add(N._norm_name(r["player"]))
    return off, dfn, pl, dplay, snap


def _nv(ml_a, ml_h):
    def imp(m):
        m = N.fnum(m)
        if m is None or m == 0:
            return None
        return (-m) / (-m + 100) if m < 0 else 100 / (m + 100)
    a, h = imp(ml_a), imp(ml_h)
    return h / (a + h) if a and h else None


def build():
    games = [g for g in N.rd(os.path.join(N.CACHE, "games.csv")) if g["game_type"] == "REG" and g.get("result") not in (None, "") and g.get("spread_line")]
    rows = []
    for season in SEASONS:
        off, dfn, pl, dplay, snap = season_data(season)
        for g in games:
            if int(g["season"]) != season:
                continue
            wk = int(g["week"]); gid = g["game_id"]; m = {}
            for t in (g["home_team"], g["away_team"]):
                v = {}
                ow = [w for w in off[t] if w < wk]; dw = [w for w in dfn[t] if w < wk]
                if len(ow) >= 3:
                    v["osr"] = sum(off[t][w][1] for w in ow) / max(1.0, sum(off[t][w][0] for w in ow))
                if len(dw) >= 3:
                    v["dsr"] = sum(dfn[t][w][1] for w in dw) / max(1.0, sum(dfn[t][w][0] for w in dw))
                tot = defaultdict(lambda: [0.0, 0.0, 0.0])
                for w in pl[t]:
                    if w < wk:
                        for nm, (pr, sk) in pl[t][w].items():
                            d = tot[nm]; d[0] += pr; d[1] += sk; d[2] += 1
                key = (gid, t)

                def plays(nm, key=key):
                    return (N._norm_name(nm) in snap[key]) if snap[key] else (nm in dplay[key])
                top = sorted((nm for nm in tot if tot[nm][2] >= 2 and plays(nm)), key=lambda nm: -tot[nm][0])[:3]
                if len(top) == 3:
                    v["rushA"] = sum(tot[nm][0] / tot[nm][2] for nm in top)
                    v["rushS"] = sum(tot[nm][1] / tot[nm][2] for nm in top)
                m[t] = v
            rows.append({"season": season, "week": wk, "h": g["home_team"], "a": g["away_team"], "res": N.fnum(g["result"]), "mk": N.fnum(g["spread_line"]),
                         "ph": _nv(g.get("away_moneyline"), g.get("home_moneyline")), "mh": m[g["home_team"]], "ma": m[g["away_team"]]})
        print(f"  {season}: 누적 {len(rows)}경기", file=sys.stderr)
    return rows


def corr(xs, ys):
    n = len(xs)
    if n < 30:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs)); sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy) if sx and sy else None


def part1(rows, L):
    ev = [r for r in rows if r["week"] >= 4 and all(k in r["mh"] and k in r["ma"] for k in ("rushA", "rushS", "dsr")) and r["season"] <= 2025]
    z = {}
    for k in ("rushA", "rushS", "dsr"):
        xs = [r[s][k] for r in ev for s in ("mh", "ma")]
        mu = sum(xs) / len(xs); sd = (sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5
        z[k] = (mu, sd)

    def zz(r, s, k):
        return (r[s][k] - z[k][0]) / z[k][1]
    cand = {"A 지금(압박 상위 3명 경기당 압박)": lambda r, s: zz(r, s, "rushA"),
            "B A + 그 3명의 경기당 색": lambda r, s: (zz(r, s, "rushA") + zz(r, s, "rushS")) / 2,
            "C 팀 수비 색률": lambda r, s: zz(r, s, "dsr"),
            "D A + 팀 수비 색률": lambda r, s: (zz(r, s, "rushA") + zz(r, s, "dsr")) / 2}
    win = [1.0 if r["res"] > 0 else 0.0 for r in ev]; mar = [r["res"] for r in ev]; cov = [r["res"] - r["mk"] for r in ev]
    L += [f"## ① 육각형 「패스러시」 재료 후보 — 2018~2025 · 4주차~ · {len(ev)}경기(홈 − 원정 값과 결과의 상관)", "",
          "| 후보 | 승패 상관 | 점수차 상관 | 커버 상관 |", "|---|---|---|---|"]
    res = {}
    for nm, f in cand.items():
        xs = [f(r, "mh") - f(r, "ma") for r in ev]
        res[nm] = (corr(xs, win), corr(xs, mar), corr(xs, cov))
        L.append(f"| {nm} | {res[nm][0]:+.3f} | {res[nm][1]:+.3f} | {res[nm][2]:+.3f} |")
    a = res["A 지금(압박 상위 3명 경기당 압박)"]
    ok = [nm for nm, v in res.items() if not nm.startswith("A") and v[0] > a[0] and v[2] >= a[2] - 0.01]
    best = max(ok, key=lambda nm: res[nm][0]) if ok else None
    L += ["", "교체 후보(승패 상관이 A 보다 높고 커버 상관이 −0.01 안): " + (" / ".join(ok) + f" → 가장 높은 것 **{best}**" if ok else "없음"), ""]
    return best


def part2(rows, L):
    # 주차별 순위
    by = defaultdict(list)
    for r in rows:
        if r["week"] >= 5:
            by[(r["season"], r["week"])].append(r)
    flags = []
    for (season, wk), gs in by.items():
        dv = {}; ov = {}
        for r in gs:
            for t, s in ((r["h"], "mh"), (r["a"], "ma")):
                if "dsr" in r[s]:
                    dv[t] = r[s]["dsr"]
                if "osr" in r[s]:
                    ov[t] = r[s]["osr"]
        dtop = set(sorted(dv, key=lambda t: -dv[t])[:TOP]) if len(dv) >= 20 else set()
        otop = set(sorted(ov, key=lambda t: -ov[t])[:TOP]) if len(ov) >= 20 else set()
        for r in gs:
            flags.append((r, r["h"] in dtop, r["a"] in dtop, r["h"] in otop, r["a"] in otop))

    def cohort(lab, cond, sel):
        w = l = p = sw = sl = 0; rs = 0.0; var = 0.0; nr = 0; by_ = defaultdict(lambda: [0, 0])
        for r, hd, ad, ho, ao in flags:
            if not sel(r):
                continue
            h_, a_ = cond(hd, ao), cond(ad, ho)
            if h_ == a_:
                continue
            home = h_
            if r["res"] != 0:
                ok = (r["res"] > 0) == home; sw += ok; sl += (not ok)
                if r["ph"] is not None:
                    pp = r["ph"] if home else 1 - r["ph"]; rs += (1 if ok else 0) - pp; var += pp * (1 - pp); nr += 1
            cv = r["res"] - r["mk"]
            if cv == 0:
                p += 1; continue
            ok = (cv > 0) == home; w += ok; l += (not ok); by_[r["season"]][0 if ok else 1] += 1
        n = w + l
        if not n:
            L.append(f"| {lab} | 0 | — | — | — | — | — |"); return None
        pct = 100 * w / n; over = sum(1 for a, b in by_.values() if a / (a + b) > 0.5); tot = len(by_)
        zr = rs / math.sqrt(var) if var else 0.0
        L.append(f"| {lab} | {sw}-{sl} {100 * sw / max(1, sw + sl):.1f}% | {100 * rs / max(1, nr):+.1f}%p (z {zr:+.2f}) | {w}-{l}" + (f"-{p}" if p else "") + f" {pct:.1f}% | {over}/{tot} | "
                 + " · ".join(f"{str(s)[2:]}:{a}-{b}" for s, (a, b) in sorted(by_.items())) + " |")
        return pct, over, tot, w, l
    L += ["## ②③ 코호트 — 「그 수비 팀 쪽」(5주차~ · 두 팀 다 해당이면 제외)", "",
          "| 조건 · 구간 | 승-패 | 시장 대비 잔차 | 스프레드 승-패 | 50% 넘긴 시즌 | 시즌별(스프레드) |", "|---|---|---|---|---|---|"]
    out = {}
    for lab, cond in (("② 색 미스매치(수비 색률 상위 8 & 상대 공격 색 허용 상위 8)", lambda d, oo: d and oo), ("③ 색률 상위 8 수비 팀", lambda d, oo: d)):
        out[lab] = cohort(lab + " · 2018~2025", cond, lambda r: r["season"] <= 2025)
        cohort(lab + " · 2026(올해)", cond, lambda r: r["season"] == 2026)
    L.append("")
    passed = []
    for lab, v in out.items():
        if not v:
            continue
        pct, over, tot, w, l = v
        if pct >= 53 and over >= 2:
            passed.append(f"{lab}: 스프레드 {w}-{l} {pct:.1f}% · 시즌 {over}/{tot}")
        elif pct <= 47 and tot - over >= 2:
            passed.append(f"{lab} → 상대 쪽: 스프레드 {l}-{w} {100 - pct:.1f}% · 시즌 {tot - over}/{tot}")
    L += ["문턱 통과(2018~2025 · 스프레드 2개+ 시즌 50% 초과 & 전체 53%+ · 47% 이하면 상대 쪽): " + (" / ".join(passed) if passed else "없음"), ""]


def main():
    rows = build()
    L = [f"# NFL 색(sack) 재점검 — {dt.date.today()}", "",
         "Paul 「nfl에서 색이 중요한 것 같은데 저번에 빼버렸는데 다시 점검해서 넣어야 할 듯」 · 정의·문턱은 scripts/sack_lab.py 머리(실행 전 고정) · 확률·★·판단 무변경.", ""]
    part1(rows, L)
    part2(rows, L)
    out = os.path.join(N.DATA, f"sack_lab_{dt.date.today()}.md")
    with open(out + ".tmp", "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(L) + "\n")
    os.replace(out + ".tmp", out)
    print("\n".join(L)); print("→", out)


if __name__ == "__main__":
    main()
