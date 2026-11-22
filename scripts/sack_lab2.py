# -*- coding: utf-8 -*-
"""sack_lab2.py — 색(sack) 더 파기(2026-11-22 Paul 「색 관련은 더 파줘봐」 · 1차 = sack_lab.py).

    python scripts/sack_lab2.py   → data/sack_lab2_<오늘>.md

묻는 것: ⓐ 색이 경기 안에서 얼마나 중요한가(설명) ⓑ 색은 누구의 실력인가(수비·공격 라인·QB 중 무엇이 다음에도 이어지나) ⓒ 경기 전 값으로 시장을 이기는 색 조건이 있는가.
후보 14개(실행 전 고정 · 5주차~ · 그 경기 전 값 · 주차별 32팀 순위 · 두 팀 다 해당이면 제외):
  C1 공격 색 허용률 가장 낮은 8팀 쪽 · C2 공격 색 허용률 가장 높은 8팀의 상대 쪽
  C3 선발 QB 본인 색률 상위 8(색을 잘 당하는 QB)의 상대 쪽 · C4 그 QB 를 색률 상위 8 수비가 만날 때 수비 쪽
  C5 최근 3경기 수비 색률 상위 8 쪽 · C6 색 순차(수비 색률 − 공격 색 허용률) 상위 8 쪽
  C7 색 전환율(색 ÷ 압박) 상위 8 수비 = 운 좋은 수비의 상대 쪽 · C8 압박률 상위 8 인데 전환율은 하위 16 = 색이 덜 나온 수비 쪽
  C9 직전 경기 색 5개+ 낸 팀 쪽 · C10 직전 경기 색 5개+ 당한 팀 쪽
  C11 색률 상위 8 수비 팀 쪽(페이버릿일 때) · C12 같은 팀 쪽(언더독일 때)
  T1 두 수비 다 색률 상위 12 → 언더 · T2 두 선발 QB 다 색률 상위 12 → 언더
문턱(1차와 같음): 2018~2025 스프레드(총점) 53%+ & 2개+ 시즌 50% 초과 · 47% 이하면 반대쪽. 여기에 시장 대비 잔차 z 를 같이 적는다.
후보가 14개라 우연히 문턱을 넘는 것이 1~2개 나올 수 있다(53%·300경기 기준 우연 확률 15% 안팎) — 통과해도 올해(2026) 값이 같은 방향인지 본다.
"""
import csv, datetime as dt, math, os, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfl_pull as N  # noqa: E402
import team_hex as TH  # noqa: E402
from sack_lab import _open, _nv, corr  # noqa: E402

SEASONS = list(range(2018, 2027))


def load(season):
    off = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0])); dfn = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0])); qb = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    with _open(TH._p("play_by_play", season)) as f:
        for x in csv.DictReader(f):
            if x.get("season_type", "REG") != "REG" or x.get("qb_dropback") != "1" or not x.get("posteam") or not x.get("defteam"):
                continue
            wk = int(x["week"]); s = 1.0 if x.get("sack") == "1" else 0.0
            o = off[x["posteam"]][wk]; o[0] += 1; o[1] += s
            d = dfn[x["defteam"]][wk]; d[0] += 1; d[1] += s
            nm = x.get("passer") or x.get("passer_player_name") or ""
            if nm and nm != "NA":
                q = qb[nm][wk]; q[0] += 1; q[1] += s
    press = defaultdict(lambda: defaultdict(float))
    dp = TH._p("advstats_week_def", season)
    if dp:
        with _open(dp) as f:
            for r in csv.DictReader(f):
                if r.get("game_type") == "REG":
                    press[N.ESPN2NV.get(r["team"], r["team"])][int(r.get("week") or 0)] += N.fnum(r.get("def_pressures")) or 0.0
    return off, dfn, qb, press


def build():
    games = [g for g in N.rd(os.path.join(N.CACHE, "games.csv")) if g["game_type"] == "REG" and g.get("result") not in (None, "") and g.get("spread_line")]
    rows = []; halves = {"dsr": [], "osr": [], "qsr": [], "conv": []}; same = []
    qprev = {}
    for season in SEASONS:
        off, dfn, qb, press = load(season)
        # ⓑ 전반(1~9주)·후반(10주~) 이어짐
        if season <= 2025:
            for tbl, key in ((dfn, "dsr"), (off, "osr")):
                for t in tbl:
                    a = [tbl[t][w] for w in tbl[t] if w <= 9]; b = [tbl[t][w] for w in tbl[t] if w >= 10]
                    if sum(x[0] for x in a) >= 150 and sum(x[0] for x in b) >= 150:
                        halves[key].append((sum(x[1] for x in a) / sum(x[0] for x in a), sum(x[1] for x in b) / sum(x[0] for x in b)))
            for nm in qb:
                a = [qb[nm][w] for w in qb[nm] if w <= 9]; b = [qb[nm][w] for w in qb[nm] if w >= 10]
                if sum(x[0] for x in a) >= 150 and sum(x[0] for x in b) >= 150:
                    halves["qsr"].append((sum(x[1] for x in a) / sum(x[0] for x in a), sum(x[1] for x in b) / sum(x[0] for x in b)))
            for t in dfn:
                pa = sum(press[t][w] for w in press[t] if w <= 9); pb = sum(press[t][w] for w in press[t] if w >= 10)
                if pa >= 40 and pb >= 40:
                    halves["conv"].append((sum(dfn[t][w][1] for w in dfn[t] if w <= 9) / pa, sum(dfn[t][w][1] for w in dfn[t] if w >= 10) / pb))
        for g in games:
            if int(g["season"]) != season:
                continue
            wk = int(g["week"]); h, a = g["home_team"], g["away_team"]; res = N.fnum(g["result"])
            if season <= 2025 and wk in dfn[h] and wk in dfn[a]:
                same.append((dfn[h][wk][1] - dfn[a][wk][1], res))      # ⓐ 같은 경기: 홈이 낸 색 − 원정이 낸 색
            m = {}
            for t, qn in ((h, g.get("home_qb_name")), (a, g.get("away_qb_name"))):
                v = {}
                ow = sorted(w for w in off[t] if w < wk); dw = sorted(w for w in dfn[t] if w < wk)
                if len(ow) >= 4:
                    v["osr"] = sum(off[t][w][1] for w in ow) / sum(off[t][w][0] for w in ow)
                    v["last_taken"] = off[t][ow[-1]][1]
                if len(dw) >= 4:
                    db = sum(dfn[t][w][0] for w in dw); sk = sum(dfn[t][w][1] for w in dw)
                    v["dsr"] = sk / db
                    l3 = dw[-3:]; v["dsr3"] = sum(dfn[t][w][1] for w in l3) / sum(dfn[t][w][0] for w in l3)
                    v["last_made"] = dfn[t][dw[-1]][1]
                    pr = sum(press[t][w] for w in dw)
                    if pr >= 20:
                        v["conv"] = sk / pr; v["prate"] = pr / db
                if "osr" in v and "dsr" in v:
                    v["net"] = v["dsr"] - v["osr"]
                if qn:
                    n = s = 0.0
                    for nm, d in qb.items():
                        if N._same_person(nm, qn):
                            for w in d:
                                if w < wk:
                                    n += d[w][0]; s += d[w][1]
                    for nm, (pn, ps) in qprev.items():
                        if N._same_person(nm, qn):
                            n += pn; s += ps
                    if n >= 150:
                        v["qsr"] = s / n
                m[t] = v
            rows.append({"season": season, "week": wk, "h": h, "a": a, "res": res, "mk": N.fnum(g["spread_line"]),
                         "ph": _nv(g.get("away_moneyline"), g.get("home_moneyline")), "tl": N.fnum(g.get("total_line")), "tot": N.fnum(g.get("total")), "m": m})
        qprev = {nm: (sum(x[0] for x in d.values()), sum(x[1] for x in d.values())) for nm, d in qb.items()}
        print(f"  {season}: 누적 {len(rows)}경기", file=sys.stderr)
    return rows, halves, same


def flags(rows):
    by = defaultdict(list)
    for r in rows:
        if r["week"] >= 5:
            by[(r["season"], r["week"])].append(r)
    out = []
    for gs in by.values():
        vals = defaultdict(dict)
        for r in gs:
            for t in (r["h"], r["a"]):
                for k, v in r["m"][t].items():
                    vals[k][t] = v

        def top(k, n, high=True):
            d = vals.get(k, {})
            return set(sorted(d, key=lambda t: -d[t] if high else d[t])[:n]) if len(d) >= 20 else set()
        S = {"osr_lo": top("osr", 8, False), "osr_hi": top("osr", 8), "qsr_hi": top("qsr", 8), "qsr12": top("qsr", 12), "dsr_hi": top("dsr", 8), "dsr12": top("dsr", 12),
             "dsr3_hi": top("dsr3", 8), "net_hi": top("net", 8), "conv_hi": top("conv", 8), "conv_lo16": top("conv", 16, False), "prate_hi": top("prate", 8)}
        for r in gs:
            f = {}
            for t, o in ((r["h"], r["a"]), (r["a"], r["h"])):
                fav = (r["mk"] > 0) == (t == r["h"]) if r["mk"] != 0 else None
                f[t] = {"C1": t in S["osr_lo"], "C2": o in S["osr_hi"], "C3": o in S["qsr_hi"], "C4": t in S["dsr_hi"] and o in S["qsr_hi"], "C5": t in S["dsr3_hi"],
                        "C6": t in S["net_hi"], "C7": o in S["conv_hi"], "C8": t in S["prate_hi"] and t in S["conv_lo16"],
                        "C9": r["m"][t].get("last_made", 0) >= 5, "C10": r["m"][t].get("last_taken", 0) >= 5,
                        "C11": t in S["dsr_hi"] and fav is True, "C12": t in S["dsr_hi"] and fav is False}
            T = {"T1": r["h"] in S["dsr12"] and r["a"] in S["dsr12"], "T2": r["h"] in S["qsr12"] and r["a"] in S["qsr12"]}
            out.append((r, f, T))
    return out


LAB = {"C1": "C1 공격 색 허용률 가장 낮은 8팀 쪽", "C2": "C2 색 허용률 가장 높은 8팀의 상대 쪽", "C3": "C3 색 잘 당하는 QB(본인 색률 상위 8)의 상대 쪽",
       "C4": "C4 그 QB 를 색률 상위 8 수비가 만날 때 수비 쪽", "C5": "C5 최근 3경기 수비 색률 상위 8 쪽", "C6": "C6 색 순차(수비 − 공격 허용) 상위 8 쪽",
       "C7": "C7 색 전환율(색÷압박) 상위 8 수비의 상대 쪽", "C8": "C8 압박률 상위 8 & 전환율 하위 16 수비 쪽", "C9": "C9 직전 경기 색 5개+ 낸 팀 쪽",
       "C10": "C10 직전 경기 색 5개+ 당한 팀 쪽", "C11": "C11 색률 상위 8 수비 팀 쪽 · 페이버릿", "C12": "C12 색률 상위 8 수비 팀 쪽 · 언더독",
       "T1": "T1 두 수비 다 색률 상위 12 → 언더", "T2": "T2 두 선발 QB 다 색률 상위 12 → 언더"}


def side_cohort(F, key, sel):
    w = l = p = sw = sl = nr = 0; rs = var = 0.0; by = defaultdict(lambda: [0, 0])
    for r, f, _ in F:
        if not sel(r):
            continue
        h_, a_ = f[r["h"]][key], f[r["a"]][key]
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
        ok = (cv > 0) == home; w += ok; l += (not ok); by[r["season"]][0 if ok else 1] += 1
    return {"sw": sw, "sl": sl, "res": 100 * rs / nr if nr else 0.0, "z": rs / math.sqrt(var) if var else 0.0, "w": w, "l": l, "p": p, "by": by}


def under_cohort(F, key, sel):
    w = l = p = 0; by = defaultdict(lambda: [0, 0])
    for r, _, T in F:
        if not sel(r) or not T[key] or r["tl"] is None or r["tot"] is None:
            continue
        if r["tot"] == r["tl"]:
            p += 1; continue
        ok = r["tot"] < r["tl"]; w += ok; l += (not ok); by[r["season"]][0 if ok else 1] += 1
    return {"w": w, "l": l, "p": p, "by": by}


def main():
    rows, halves, same = build()
    F = flags(rows)
    L = [f"# NFL 색(sack) 더 파기 — {dt.date.today()}", "", "Paul 「색 관련은 더 파줘봐」 · 정의·문턱은 scripts/sack_lab2.py 머리(실행 전 고정) · 예측·★·판단 무변경.", "",
         "## ⓐ 색은 경기 안에서 얼마나 중요한가(2018~2025 · 같은 경기 기록 — 미리 알 수 없는 값)", ""]
    for lab, cond in (("색을 더 많이 낸 팀", lambda d: d != 0), ("색을 2개 이상 더 낸 팀", lambda d: abs(d) >= 2), ("색을 3개 이상 더 낸 팀", lambda d: abs(d) >= 3)):
        xs = [(d, r) for d, r in same if cond(d) and r != 0]
        w = sum(1 for d, r in xs if (d > 0) == (r > 0))
        L.append(f"- {lab}: {w}-{len(xs) - w} · 승률 {100 * w / len(xs):.1f}%")
    L.append(f"- 색 차와 점수차의 상관 {corr([d for d, _ in same], [r for _, r in same]):+.3f}({len(same)}경기)")
    L += ["", "## ⓑ 색은 누구의 실력인가 — 시즌 전반(1~9주) 값이 후반(10주~)에도 이어지는 정도(상관 · 1에 가까울수록 실력)", "",
          "| 값 | 표본 | 전반·후반 상관 |", "|---|---|---|"]
    for key, lab in (("qsr", "QB 본인 색률(색 ÷ 드롭백)"), ("osr", "팀 공격 색 허용률"), ("dsr", "팀 수비 색률"), ("conv", "수비 색 전환율(색 ÷ 압박)")):
        xs = halves[key]
        L.append(f"| {lab} | {len(xs)} | {corr([a for a, _ in xs], [b for _, b in xs]):+.3f} |" if len(xs) >= 30 else f"| {lab} | {len(xs)} | 표본 부족 |")
    L += ["", "## ⓒ 경기 전 값으로 본 색 조건 14개(5주차~ · 「그 쪽」)", "",
          "| 조건 | 구간 | 승-패 | 시장 대비 잔차 | 스프레드(총점) 승-패 | 50% 넘긴 시즌 |", "|---|---|---|---|---|---|"]
    passed = []
    for key in ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10", "C11", "C12"):
        for era, sel in (("2018~2025", lambda r: r["season"] <= 2025), ("2026", lambda r: r["season"] == 2026)):
            c = side_cohort(F, key, sel); n = c["w"] + c["l"]
            if not n:
                L.append(f"| {LAB[key]} | {era} | — | — | 0 | — |"); continue
            pct = 100 * c["w"] / n; over = sum(1 for a, b in c["by"].values() if a / (a + b) > 0.5); tot = len(c["by"])
            L.append(f"| {LAB[key]} | {era} | {c['sw']}-{c['sl']} {100 * c['sw'] / max(1, c['sw'] + c['sl']):.1f}% | {c['res']:+.1f}%p (z {c['z']:+.2f}) | {c['w']}-{c['l']}" + (f"-{c['p']}" if c["p"] else "") + f" {pct:.1f}% | {over}/{tot} |")
            if era == "2018~2025":
                if pct >= 53 and over >= 2:
                    passed.append(f"{LAB[key]}: 스프레드 {c['w']}-{c['l']} {pct:.1f}% · 시장 대비 {c['res']:+.1f}%p")
                elif pct <= 47 and tot - over >= 2:
                    passed.append(f"{LAB[key]} → 반대쪽: 스프레드 {c['l']}-{c['w']} {100 - pct:.1f}% · 시장 대비 {-c['res']:+.1f}%p")
    for key in ("T1", "T2"):
        for era, sel in (("2018~2025", lambda r: r["season"] <= 2025), ("2026", lambda r: r["season"] == 2026)):
            c = under_cohort(F, key, sel); n = c["w"] + c["l"]
            if not n:
                L.append(f"| {LAB[key]} | {era} | — | — | 0 | — |"); continue
            pct = 100 * c["w"] / n; over = sum(1 for a, b in c["by"].values() if a / (a + b) > 0.5); tot = len(c["by"])
            L.append(f"| {LAB[key]} | {era} | — | — | 언더 {c['w']}-{c['l']}" + (f"-{c['p']}" if c["p"] else "") + f" {pct:.1f}% | {over}/{tot} |")
            if era == "2018~2025":
                if pct >= 53 and over >= 2:
                    passed.append(f"{LAB[key]}: {c['w']}-{c['l']} {pct:.1f}%")
                elif pct <= 47 and tot - over >= 2:
                    passed.append(f"{LAB[key]} → 오버: {c['l']}-{c['w']} {100 - pct:.1f}%")
    L += ["", "문턱 통과(2018~2025 · 53%+ & 2개+ 시즌 50% 초과 · 47% 이하면 반대쪽 · 후보 14개 중 우연 통과 1~2개 가능): " + (" / ".join(passed) if passed else "없음"), ""]
    out = os.path.join(N.DATA, f"sack_lab2_{dt.date.today()}.md")
    with open(out + ".tmp", "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(L) + "\n")
    os.replace(out + ".tmp", out)
    print("\n".join(L)); print("→", out)


if __name__ == "__main__":
    main()
