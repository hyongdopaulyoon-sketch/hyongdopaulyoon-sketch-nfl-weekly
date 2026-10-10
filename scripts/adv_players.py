"""리시버·러셔 고급 기록(2026-10-10 Paul 「넣어」 — nflverse 미러: PFR advstats rec/rush + NGS receiving/rushing) + OL 연속성.
전부 서술 전용(스탯 비교 「주요 선수」·「OL 연속성」 행) — 점수 0. 넣기 전 안정성 r(홀/짝 주 상관, 2024~2025 선수-시즌)을 직접 재서 실력/중간/운 꼬리표를 붙인다.
  python adv_players.py            → 안정성 r 측정·출력(data/cache/adv_stability.json 저장)
"""
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nfl_pull as N   # noqa: E402

STAB_PATH = os.path.join(N.CACHE, "adv_stability.json")
OL_POS = {"T", "G", "C", "OL", "OT", "OG", "LT", "RT", "LG", "RG"}
MIN_WEEKS = 4          # r 측정: 홀·짝 각각 최소 주 수
# (라벨, 파일 종류, 열, 가중 열) — 주별 값을 가중 평균해 홀/짝 상관
METRICS = {
    "rec_drop_pct": ("드롭률", "pfr_rec", "receiving_drop_pct", None),
    "rec_separation": ("분리도", "ngs_rec", "avg_separation", "targets"),
    "rec_cushion": ("쿠션", "ngs_rec", "avg_cushion", "targets"),
    "rec_yac_oe": ("기대 대비 YAC", "ngs_rec", "avg_yac_above_expectation", "receptions"),
    "rush_ybc": ("접촉 전 야드/캐리", "pfr_rush", "rushing_yards_before_contact_avg", "carries"),
    "rush_yac": ("접촉 후 야드/캐리", "pfr_rush", "rushing_yards_after_contact_avg", "carries"),
    "rush_bt": ("태클 깨기/캐리", "pfr_rush", "_bt_per_carry", "carries"),
    "rush_ryoe": ("기대 대비 러시 야드/캐리", "ngs_rush", "rush_yards_over_expected_per_att", "rush_attempts"),
    "rush_eff": ("효율(이동 야드/러시 야드)", "ngs_rush", "efficiency", "rush_attempts"),
}


def fetch_all(force=False):
    for sub, name, age in (("pfr_advstats", f"advstats_week_rec_{N.SEASON}.csv", 12), ("pfr_advstats", f"advstats_week_rush_{N.SEASON}.csv", 12),
                           ("pfr_advstats", f"advstats_week_rec_{N.SEASON - 1}.csv", 24 * 30), ("pfr_advstats", f"advstats_week_rush_{N.SEASON - 1}.csv", 24 * 30),
                           ("pfr_advstats", f"advstats_week_rec_{N.SEASON - 2}.csv", 24 * 30), ("pfr_advstats", f"advstats_week_rush_{N.SEASON - 2}.csv", 24 * 30),
                           ("nextgen_stats", "ngs_receiving.csv.gz", 12), ("nextgen_stats", "ngs_rushing.csv.gz", 12)):
        try:
            N.fetch(N.NFLVERSE + f"{sub}/{name}", os.path.join(N.CACHE, name), age, force)
        except Exception as e:
            N.log(f"  고급 기록 내려받기 실패 {name}: {type(e).__name__}")


def _weekly(kind, season):
    """kind → [(season, player_key, week, value, weight)] — 정규시즌 주별."""
    out = []
    if kind in ("pfr_rec", "pfr_rush"):
        p = os.path.join(N.CACHE, f"advstats_week_{'rec' if kind == 'pfr_rec' else 'rush'}_{season}.csv")
        for r in N.rd(p):
            if r.get("game_type") != "REG":
                continue
            row = dict(r)
            if kind == "pfr_rush":
                c = N.fnum(r.get("carries")) or 0
                row["_bt_per_carry"] = (N.fnum(r.get("rushing_broken_tackles")) or 0) / c if c else None
            out.append((season, r["pfr_player_name"], int(r["week"]), row))
    else:
        p = os.path.join(N.CACHE, "ngs_receiving.csv.gz" if kind == "ngs_rec" else "ngs_rushing.csv.gz")
        for r in N.rd(p):
            if r.get("season") != str(season) or r.get("season_type") != "REG" or r.get("week") == "0":
                continue
            out.append((season, r["player_display_name"], int(r["week"]), r))
    return out


def _corr(xs, ys):
    n = len(xs)
    if n < 8:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = (sum((x - mx) ** 2 for x in xs)) ** 0.5; sy = (sum((y - my) ** 2 for y in ys)) ** 0.5
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy) if sx and sy else None


def stability(seasons=(N.SEASON - 2, N.SEASON - 1)):
    """{metric: {"r": float, "n": 선수-시즌 수, "tier": 실력/중간/운}} — stat_research 와 같은 문턱(≥.45 실력 · .25~.45 중간 · <.25 운)."""
    res = {}
    cache = {}
    for key, (lab, kind, col, wcol) in METRICS.items():
        xs, ys = [], []
        for s in seasons:
            rows = cache.setdefault((kind, s), _weekly(kind, s))
            by = defaultdict(lambda: {0: [0.0, 0.0, 0], 1: [0.0, 0.0, 0]})
            for _s, pk, wk, r in rows:
                v = N.fnum(r.get(col)); w = (N.fnum(r.get(wcol)) if wcol else 1.0) or 0
                if v is None or w <= 0:
                    continue
                b = by[pk][wk % 2]; b[0] += v * w; b[1] += w; b[2] += 1
            for pk, b in by.items():
                if b[0][2] >= MIN_WEEKS and b[1][2] >= MIN_WEEKS and b[0][1] > 0 and b[1][1] > 0:
                    xs.append(b[0][0] / b[0][1]); ys.append(b[1][0] / b[1][1])
        r = _corr(xs, ys)
        res[key] = {"label": lab, "r": None if r is None else round(r, 2), "n": len(xs), "tier": ("—" if r is None else "실력" if r >= .45 else "중간" if r >= .25 else "운")}
    return res


def load_stability():
    try:
        return json.load(open(STAB_PATH, encoding="utf-8"))
    except Exception:
        return {}


def stab_tag(key):
    x = load_stability().get(key)
    return f"r {x['r']:.2f}·{x['tier']}" if x and x.get("r") is not None else "r 미측정"


# ───────────── 2026 시즌 값(스탯 비교용) ─────────────
_SEASON = None


def season_values():
    """→ {"rec": {name: dict}, "rush": {name: dict}} 2026 정규시즌 누적(PFR 주별 합 + NGS week 0)."""
    global _SEASON
    if _SEASON is not None:
        return _SEASON
    rec, rush = defaultdict(lambda: defaultdict(float)), defaultdict(lambda: defaultdict(float))
    for _s, pk, wk, r in _weekly("pfr_rec", N.SEASON):
        rec[pk]["drops"] += N.fnum(r.get("receiving_drop")) or 0; rec[pk]["bt"] += N.fnum(r.get("receiving_broken_tackles")) or 0; rec[pk]["g"] += 1
    for _s, pk, wk, r in _weekly("pfr_rush", N.SEASON):
        rush[pk]["car"] += N.fnum(r.get("carries")) or 0; rush[pk]["ybc"] += N.fnum(r.get("rushing_yards_before_contact")) or 0
        rush[pk]["yac"] += N.fnum(r.get("rushing_yards_after_contact")) or 0; rush[pk]["bt"] += N.fnum(r.get("rushing_broken_tackles")) or 0
    for r in N.rd(os.path.join(N.CACHE, "ngs_receiving.csv.gz")):
        if r.get("season") == str(N.SEASON) and r.get("season_type") == "REG" and r.get("week") == "0":
            x = rec[r["player_display_name"]]
            x["team"] = r.get("team_abbr", ""); x["tgt"] = N.fnum(r.get("targets")) or 0; x["sep"] = N.fnum(r.get("avg_separation")); x["cush"] = N.fnum(r.get("avg_cushion"))
            x["yac_oe"] = N.fnum(r.get("avg_yac_above_expectation")); x["adot"] = N.fnum(r.get("avg_intended_air_yards"))
    for r in N.rd(os.path.join(N.CACHE, "ngs_rushing.csv.gz")):
        if r.get("season") == str(N.SEASON) and r.get("season_type") == "REG" and r.get("week") == "0":
            x = rush[r["player_display_name"]]
            x["team"] = r.get("team_abbr", ""); x["att"] = N.fnum(r.get("rush_attempts")) or 0; x["ryoe"] = N.fnum(r.get("rush_yards_over_expected_per_att")); x["eff"] = N.fnum(r.get("efficiency"))
    _SEASON = {"rec": rec, "rush": rush}
    return _SEASON


def _find(d, short):
    """pbp 짧은 이름(J.Smith-Njigba) → 전체 이름 키."""
    for k in d:
        if N._same_person(short, k):
            return k
    return None


def _rk(vals, key, high=True):
    xs = sorted((v for v in vals.values() if v is not None), reverse=high)
    v = vals.get(key)
    if v is None:
        return None, len(xs)
    return xs.index(v) + 1, len(xs)


def tier(rank, n):
    if rank is None:
        return "—"
    return "상위" if rank <= max(1, n * 10 // 32) else "중간" if rank <= n * 22 // 32 else "하위"


def receiver_extra(short):
    """리시버 추가 수치 한 토막(값·순위·구간·안정성) 또는 ""."""
    R = season_values()["rec"]; k = _find(R, short)
    if not k:
        return ""
    x = R[k]
    pool = {n: v for n, v in R.items() if (v.get("tgt") or 0) >= 15}
    parts = []
    for col, lab, high, fmt, sk in (("sep", "분리도", True, "{:.1f}야드", "rec_separation"), ("yac_oe", "기대 대비 YAC", True, "{:+.1f}", "rec_yac_oe")):
        if x.get(col) is None:
            continue
        r, n = _rk({nn: vv.get(col) for nn, vv in pool.items()}, k, high)
        parts.append(f"{lab} {fmt.format(x[col])}" + (f"({r}/{n}위·{tier(r, n)})" if r else "") + f"[{stab_tag(sk)}]")
    if x.get("tgt"):
        parts.append(f"드롭 {int(x.get('drops', 0))}/{int(x['tgt'])}타깃({100 * x.get('drops', 0) / x['tgt']:.0f}%)[{stab_tag('rec_drop_pct')}]")
    return " · ".join(parts)


def rusher_extra(short):
    R = season_values()["rush"]; k = _find(R, short)
    if not k:
        return ""
    x = R[k]
    pool = {n: v for n, v in R.items() if (v.get("car") or v.get("att") or 0) >= 25}
    parts = []
    if x.get("car"):
        yac = {nn: (vv["yac"] / vv["car"]) for nn, vv in pool.items() if vv.get("car")}
        r, n = _rk(yac, k, True)
        ybc = {nn: (vv["ybc"] / vv["car"]) for nn, vv in pool.items() if vv.get("car")}
        r2, n2 = _rk(ybc, k, True)
        parts.append(f"접촉 전 야드/캐리 {x['ybc'] / x['car']:.1f}" + (f"({r2}/{n2}위·{tier(r2, n2)})" if r2 else "") + f"[{stab_tag('rush_ybc')}]"
                     + f" · 접촉 후 {x['yac'] / x['car']:.1f}" + (f"({r}/{n}위·{tier(r, n)})" if r else "") + f"[{stab_tag('rush_yac')}]"
                     + f" · 태클 깨기 {int(x['bt'])}[{stab_tag('rush_bt')}]")
    if x.get("ryoe") is not None:
        r, n = _rk({nn: vv.get("ryoe") for nn, vv in pool.items()}, k, True)
        parts.append(f"기대 대비 러시 야드/캐리 {x['ryoe']:+.2f}" + (f"({r}/{n}위·{tier(r, n)})" if r else "") + f"[{stab_tag('rush_ryoe')}]")
    return " · ".join(parts)


# ───────────── OL 연속성 ─────────────
def ol_continuity(team, inj_row, week):
    """최근 3경기(이번 주 전) 공격 스냅 상위 OL 5명 중 오늘 Out/Doubtful 수 → 문자열."""
    rows = [r for r in N.rd(os.path.join(N.CACHE, f"snap_counts_{N.SEASON}.csv"))
            if r.get("team") == team and r.get("game_type") == "REG" and r.get("position") in OL_POS and int(r.get("week") or 0) < week]
    if not rows:
        return "스냅 자료 없음"
    weeks = sorted({int(r["week"]) for r in rows})[-3:]
    tot = defaultdict(float)
    for r in rows:
        if int(r["week"]) in weeks:
            tot[r["player"]] += N.fnum(r.get("offense_snaps")) or 0
    starters = [n for n, _ in sorted(tot.items(), key=lambda kv: -kv[1])[:5]]
    absent = [n.split("(")[0].strip() for key in ("out", "doubtful") for n in str((inj_row or {}).get(key) or "").split(" · ") if n.strip()]
    miss = [s for s in starters if any(N._same_person(s, a) or N._same_person(a, s) or s.lower() == a.lower() for a in absent)]
    pend = bool((inj_row or {}).get("final_pending"))
    return (f"주전 5명 중 결장 {len(miss)}명" + (f"({', '.join(miss)})" if miss else "") + f" · 최근 {len(weeks)}경기 기준"
            + (" · ⚠️ 최종 지정 미발표(연습 보고만)" if pend else ""))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    fetch_all()
    res = stability()
    json.dump(res, open(STAB_PATH + ".tmp", "w", encoding="utf-8"), ensure_ascii=False, indent=1); os.replace(STAB_PATH + ".tmp", STAB_PATH)
    print(f"안정성 r(홀/짝 주 상관 · {N.SEASON - 2}~{N.SEASON - 1} 선수-시즌 · 홀·짝 각 {MIN_WEEKS}주+):")
    for k, x in res.items():
        print(f"  {x['label']:<22} r {x['r'] if x['r'] is not None else '—':>5} · n {x['n']:>4} · {x['tier']}")
