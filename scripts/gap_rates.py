"""📊 스탯 비교 「격차」 등급별 실측 — 2026-10-17 Paul 「서술 옆에 퍼센트」.
항목마다 그 주 전까지(as-of) 시즌 값으로 32팀 순위를 매기고, 두 팀 순위 차 등급(차이 없음/근접/경미/중대 — stat_compare.GAP_CUTS)별로
「순위 높은 팀이 실제 이긴 비율」과 「시장(마감 무비그)이 그 팀에 준 확률」을 센다. 서술 전용 — 확률·별점에 넣지 않는다.
  python scripts/gap_rates.py --seasons 2024 2025 --min-week 4   → data/gap_rates.json
"""
import argparse, json, os, sys
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nfl_pull as N          # noqa: E402
import stat_research as SR    # noqa: E402
import stat_compare as SC     # noqa: E402

# 항목 키 → (T 행에서 분자, 분모, 높을수록 좋음, 공격(posteam) 기준인지)
ITEMS = {
    "공격 효율(드라이브당 득점)": ("dr_pts", "dr", True, True), "득점 드라이브 비율": (("dr_td", "dr_fg"), "dr", True, True),
    "수비 효율(내준 드라이브당 득점)": ("dr_pts", "dr", False, False), "상대 득점 드라이브 허용": (("dr_td", "dr_fg"), "dr", False, False),
    "패스 공격(드롭백당 EPA)": ("pepa", "db", True, True), "러시 공격(러시당 EPA)": ("repa", "rn", True, True),
    "패스 수비(허용 EPA)": ("pepa", "db", False, False), "러시 수비(허용 EPA)": ("repa", "rn", False, False),
    "3rd down 전환(공격)": ("d3c", "d3", True, True), "3rd down 허용(수비)": ("d3c", "d3", False, False),
    "턴오버(경기당 잃음)": ("to", "g", False, True), "색 허용률(공격)": ("sack", "db", False, True),
}


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


def val(rows, num, den):
    d = sum(r.get(den, 0) if den != "g" else 1 for r in rows)
    if not d:
        return None
    if isinstance(num, tuple):
        return sum(sum(r.get(k, 0) for k in num) for r in rows) / d
    return sum(r.get(num, 0) for r in rows) / d


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--seasons", nargs="+", type=int, default=[2024, 2025]); ap.add_argument("--min-week", type=int, default=4)
    a = ap.parse_args()
    games = [g for g in N.rd(os.path.join(N.CACHE, "games.csv")) if g["game_type"] == "REG" and g.get("result")]
    agg = defaultdict(lambda: defaultdict(lambda: [0, 0, 0.0]))     # item → grade → [n, win, mkt_sum]
    for season in a.seasons:
        T, _P, _N = SR.load(season)
        offr, defr = defaultdict(list), defaultdict(list)            # team → [(week, row)]
        for (gid, wk, pt, dt), x in T.items():
            offr[pt].append((wk, x)); defr[dt].append((wk, x))
        pf, pa = defaultdict(list), defaultdict(list)                 # 득점·실점(경기당) — games.csv
        gs = [g for g in games if int(g["season"]) == season]
        for g in gs:
            w = int(g["week"]); hs, as_ = f(g["home_score"]), f(g["away_score"])
            pf[g["home_team"]].append((w, hs)); pa[g["home_team"]].append((w, as_)); pf[g["away_team"]].append((w, as_)); pa[g["away_team"]].append((w, hs))
        teams = sorted(set(pf))
        for g in gs:
            w = int(g["week"])
            if w < a.min_week:
                continue
            h, aw = g["home_team"], g["away_team"]
            ph, pa_ = pimp(g["home_moneyline"]), pimp(g["away_moneyline"])
            if ph is None or pa_ is None or f(g["result"]) == 0:
                continue
            s = ph + pa_; ph, pa_ = ph / s, pa_ / s
            won = {h: f(g["result"]) > 0, aw: f(g["result"]) < 0}; mk = {h: ph, aw: pa_}
            for item, (num, den, high, off) in ITEMS.items():
                src = offr if off else defr
                vals = {t: val([x for wk, x in src[t] if wk < w], num, den) for t in teams}
                if sum(1 for v in vals.values() if v is not None) < 28:
                    continue
                ra, rh = SC._rank(vals, aw, high), SC._rank(vals, h, high)
                lab = SC.gap_label(ra, rh, aw, h).split(" · ")[0]
                if lab == "—":
                    continue
                better = aw if ra < rh else h
                if lab == "차이 없음":
                    better = h if mk[h] >= mk[aw] else aw          # 차이 없음은 참고로 「시장 페이버릿」 기준
                c = agg[item][lab]; c[0] += 1; c[1] += won[better]; c[2] += mk[better]
            for item, src, high in (("득점(경기당)", pf, True), ("실점(경기당)", pa, False)):
                vals = {t: (sum(v for wk, v in src[t] if wk < w) / len([1 for wk, v in src[t] if wk < w])) if [1 for wk, v in src[t] if wk < w] else None for t in teams}
                ra, rh = SC._rank(vals, aw, high), SC._rank(vals, h, high)
                lab = SC.gap_label(ra, rh, aw, h).split(" · ")[0]
                if lab == "—":
                    continue
                better = aw if ra < rh else h
                if lab == "차이 없음":
                    better = h if mk[h] >= mk[aw] else aw
                c = agg[item][lab]; c[0] += 1; c[1] += won[better]; c[2] += mk[better]
    out = {item: {lab: {"n": c[0], "win": round(100 * c[1] / c[0]), "mkt": round(100 * c[2] / c[0])} for lab, c in grades.items() if c[0] >= 10}
           for item, grades in agg.items()}
    out["_meta"] = {"seasons": a.seasons, "min_week": a.min_week, "note": "순위 높은 팀 ML 실제 승률 vs 시장 무비그 기대 — 서술 전용"}
    p = os.path.join(N.DATA, "gap_rates.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"| 항목 | 근접 | 경미 | 중대 |\n|---|---|---|---|")
    for item in ITEMS.keys() | {"득점(경기당)", "실점(경기당)"}:
        g_ = out.get(item, {})
        print(f"| {item} | " + " | ".join(f"{g_[l]['win']}% vs 시장 {g_[l]['mkt']}% (n{g_[l]['n']})" if l in g_ else "—" for l in ("근접", "경미", "중대")) + " |")
    print("wrote", p)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
