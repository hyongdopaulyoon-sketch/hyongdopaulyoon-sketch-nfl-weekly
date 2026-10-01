"""특징 백테스트 F1~F6 — 「시장도 아는 정보」가 마감 라인 대비 잔차를 설명하는가 (2026-10-01 사전 등록, pending_rules.md 같은 날 줄).
  python scripts/backtest_features.py            발견 구간(2013~2022 · F3/F4 2018~2022)만
  python scripts/backtest_features.py --validate 발견 통과 특징만 검증 구간(2023~2025)을 한 번 연다
목표 변수: 팀 커버 마진 = (결과 − 마감 스프레드)(팀 기준) · 총점 잔차 = 실제 총점 − 마감 총점. ATS% 는 보조.
판정: 시즌-주 묶음 부트스트랩 95% 구간 · 같은 시즌-주 안 순열 검정 2,000회(양측, 중심화) · 유의 0.05/6 ≈ 0.0083 · 시즌별 부호 일관성.
특징 정의·문턱·채택 기준은 사전 등록 그대로 — 결과를 보고 고치지 않는다."""
import argparse, csv, gzip, math, os, random, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import situations as S   # noqa: E402  (G · tm · norm · rd · f · cover 정의 재사용)

HIST = S.HIST
ALPHA = 0.05 / 6
NPERM = 2000
STAR = 0.60
POS = {"OL": {"T", "G", "C", "OL", "OT", "OG"}, "WRTE": {"WR", "TE"}, "CBS": {"CB", "S", "FS", "SS", "DB"},
       "DLLB": {"DE", "DT", "NT", "DL", "LB", "ILB", "OLB", "MLB", "EDGE"}, "SKILL": {"WR", "TE", "RB", "FB"}}
f = S.f


def home_margin(g):
    return g["res"] - g["sp"]


# ── 부상 × 스냅(as-of) ──
def starters_out():
    """{(season, team, week): {all, OL, WRTE, CBS, DLLB, SKILL}} — 직전 팀 3경기 중 출전 경기 평균 스냅 60%+ 이고 그 주 Out/Doubtful."""
    out = {}
    for s in range(2013, 2026):
        snaps = S.rd(os.path.join(HIST, f"snap_counts_{s}.csv")); inj = S.rd(os.path.join(HIST, f"injuries_{s}.csv"))
        team_weeks = defaultdict(set); pct = defaultdict(dict)
        for r in snaps:
            if r.get("game_type", "REG") != "REG":
                continue
            t = S.tm(r["team"]); w = int(r["week"]); team_weeks[t].add(w)
            v = max(f(r.get("offense_pct")) or 0, f(r.get("defense_pct")) or 0)
            if v > 1.5:
                v /= 100
            if v > 0:
                pct[(t, S.norm(r["player"]))][w] = v
        od = defaultdict(list)
        for r in inj:
            if r.get("game_type", "REG") == "REG" and r.get("report_status") in ("Out", "Doubtful"):
                od[(S.tm(r["team"]), int(r["week"]))].append((S.norm(r["full_name"]), r.get("position", "")))
        for t, wks in team_weeks.items():
            for w in range(1, 23):
                prev = sorted(x for x in wks if x < w)[-3:]
                if len(prev) < 3:
                    continue
                c = dict.fromkeys(["all"] + list(POS), 0)
                for name, pos in od.get((t, w), []):
                    vals = [v for v in (pct.get((t, name), {}).get(x) for x in prev) if v]
                    if vals and sum(vals) / len(vals) >= STAR:
                        c["all"] += 1
                        for k, ps in POS.items():
                            c[k] += pos in ps
                out[(s, t, w)] = c
    return out


# ── PFR 압박(as-of) ──
def pressure_asof():
    """{(season, team, week): (수비 압박/경기, 공격 피압박/경기)} — 시즌 내 직전 ≤6경기, 3경기 미만이면 전 시즌 경기당."""
    per = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))     # (s, team) -> week -> [def_press, off_pressured]
    for s in range(2018, 2026):
        for r in S.rd(os.path.join(HIST, f"advstats_week_def_{s}.csv")):
            if r.get("game_type", "REG") == "REG":
                per[(s, S.tm(r["team"]))][int(r["week"])][0] += f(r.get("def_pressures")) or 0
        for r in S.rd(os.path.join(HIST, f"advstats_week_pass_{s}.csv")):
            if r.get("game_type", "REG") == "REG":
                per[(s, S.tm(r["team"]))][int(r["week"])][1] += f(r.get("times_pressured")) or 0
    full = {k: (sum(v[0] for v in d.values()) / len(d), sum(v[1] for v in d.values()) / len(d)) for k, d in per.items() if d}
    out = {}
    for (s, t), d in per.items():
        for w in range(1, 23):
            prev = sorted(x for x in d if x < w)[-6:]
            if len(prev) >= 3:
                out[(s, t, w)] = (sum(d[x][0] for x in prev) / len(prev), sum(d[x][1] for x in prev) / len(prev))
            elif (s - 1, t) in full:
                out[(s, t, w)] = full[(s - 1, t)]
    return out


# ── NGS CPOE(as-of) ──
def cpoe_asof():
    with gzip.open(os.path.join(HIST, "ngs_passing.csv.gz"), "rt", encoding="utf-8-sig") as fh:
        ngs = list(csv.DictReader(fh))
    rows = [r for r in ngs if r.get("season_type") == "REG" and r.get("week") not in ("0", "")]
    by = defaultdict(list)    # gsis -> [(season, week, cpoe, att)]
    for r in rows:
        c, a = f(r.get("completion_percentage_above_expectation")), f(r.get("attempts"))
        if c is not None and a:
            by[r["player_gsis_id"]].append((int(r["season"]), int(r["week"]), c, a))

    def get(gid, s, w):
        xs = [(c, a) for (ss, ww, c, a) in by.get(gid, ()) if ss == s - 1 or (ss == s and ww < w)]
        return sum(c * a for c, a in xs) / (sum(a for _, a in xs) + 200.0)
    return get


# ── 백업 QB 첫 선발 ──
def backup_first():
    flags = set(); seq = defaultdict(list)
    for g in S.G:
        for side in ("a", "h"):
            qb = g["away_qb_name" if side == "a" else "home_qb_name"]
            if qb:
                seq[(g["s"], g[side])].append((g, qb))
    for (s, t), lst in seq.items():
        starts = defaultdict(int); last = {}
        for i, (g, qb) in enumerate(lst):
            if i >= 2:
                reg = max(starts, key=lambda q: (starts[q], last[q]))
                if qb != reg and starts[qb] == 0:
                    flags.add((g["game_id"], t))
            starts[qb] += 1; last[qb] = i
    return flags


# ── 통계 ──
def slope(xs, ys):
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    vx = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / vx if vx else 0.0


def test(rows, kind, rng):
    """rows = [(cluster, season, x, y)] · kind 'slope'(x 연속) 또는 'flag'(x 0/1, 통계 = 플래그 행 y 평균)."""
    def stat(rs):
        if kind == "slope":
            return slope([r[2] for r in rs], [r[3] for r in rs])
        ys = [r[3] for r in rs if r[2]]
        return sum(ys) / len(ys) if ys else 0.0
    obs = stat(rows)
    cl = defaultdict(list)
    for r in rows:
        cl[r[0]].append(r)
    keys = list(cl)
    perm = []
    for _ in range(NPERM):
        rs = []
        for k in keys:
            xs = [r[2] for r in cl[k]]; rng.shuffle(xs)
            rs += [(r[0], r[1], x, r[3]) for r, x in zip(cl[k], xs)]
        perm.append(stat(rs))
    pm = sum(perm) / len(perm)
    p = (1 + sum(1 for v in perm if abs(v - pm) >= abs(obs - pm))) / (NPERM + 1)
    boot = []
    for _ in range(1000):
        rs = []
        for k in rng.choices(keys, k=len(keys)):
            rs += cl[k]
        boot.append(stat(rs))
    boot.sort()
    by = defaultdict(list)
    for r in rows:
        by[r[1]].append(r)
    seas = {s: stat(rs) for s, rs in by.items() if (kind == "slope" and len(rs) > 10) or (kind == "flag" and any(r[2] for r in rs))}
    n = sum(1 for r in rows if r[2]) if kind == "flag" else len(rows)
    return obs, (boot[25], boot[974]), p, seas, n


def ats_side(rows_flag):
    """플래그 행의 커버 W-L(푸시 제외) — y>0 이 커버."""
    w = sum(1 for y in rows_flag if y > 0); l = sum(1 for y in rows_flag if y < 0)
    return f"{w}-{l} {100 * w / (w + l):.1f}%" if w + l else "—"


def build(seasons, SO, PR, CP, BQ):
    """특징별 rows 생성. 반환 {F: (kind, 가설 부호, rows, ATS용 y 목록, 설명)}"""
    G = [g for g in S.G if g["s"] in seasons]
    F = {k: [] for k in ("F1", "F2", "F3", "F4", "F5", "F6")}
    ats = {k: [] for k in F}
    desc = defaultdict(list)
    # F3 시즌별 z 를 위해 먼저 값 모으기
    pr_rows = []
    for g in G:
        cl = (g["s"], g["wk"]); m = home_margin(g)
        sa, sh = SO.get((g["s"], g["a"], g["wk"])), SO.get((g["s"], g["h"], g["wk"]))
        if sa and sh:
            F["F1"].append((cl, g["s"], sh["all"] - sa["all"], m))
            if sh["all"] != sa["all"]:
                ats["F1"].append(m if sh["all"] < sa["all"] else -m)        # 결장 적은 쪽
            for grp in ("OL", "WRTE", "CBS", "DLLB"):
                desc[grp].append((cl, g["s"], sh[grp] - sa[grp], m))
            for t, c, sign in ((g["h"], sh, 1), (g["a"], sa, -1)):
                fl = int(c["OL"] >= 2)
                F["F2"].append((cl, g["s"], fl, sign * m))
                if fl:
                    ats["F2"].append(sign * m)
            if g["tl"] is not None and g["tot"] is not None:
                wind = (f(g["wind"]) or 0) >= 15 and g["roof"] in ("outdoors", "open")
                fl = int(sa["SKILL"] + sh["SKILL"] >= 2 or wind)
                F["F6"].append((cl, g["s"], fl, g["tot"] - g["tl"]))
                if fl:
                    ats["F6"].append(-(g["tot"] - g["tl"]))                 # 언더 쪽 승 = 잔차 음수
                desc["F6_skill"].append((cl, g["s"], int(sa["SKILL"] + sh["SKILL"] >= 2), g["tot"] - g["tl"]))
                desc["F6_wind"].append((cl, g["s"], int(wind), g["tot"] - g["tl"]))
        pa, ph = PR.get((g["s"], g["a"], g["wk"])), PR.get((g["s"], g["h"], g["wk"]))
        if pa and ph and g["s"] >= 2018:
            pr_rows.append((g, pa, ph))
        if g["s"] >= 2018 and g.get("home_qb_id") and g.get("away_qb_id"):
            d = CP(g["home_qb_id"], g["s"], g["wk"]) - CP(g["away_qb_id"], g["s"], g["wk"])
            F["F4"].append((cl, g["s"], d, m))
            if abs(d) >= 2:
                ats["F4"].append(m if d > 0 else -m)
        for t, sign in ((g["h"], 1), (g["a"], -1)):
            fl = int((g["game_id"], t) in BQ)
            F["F5"].append((cl, g["s"], fl, sign * m))
            if fl:
                ats["F5"].append(sign * m)
    # F3: 수비 팀 기준 점수 = z(수비 압박) + z(상대 공격 피압박), 시즌 내 표준화 → 시즌 상위 25%
    by_s = defaultdict(list)
    for g, pa, ph in pr_rows:
        by_s[g["s"]] += [(g, g["h"], ph[0], pa[1], 1), (g, g["a"], pa[0], ph[1], -1)]
    for s, xs in by_s.items():
        def z(vals):
            mu = sum(vals) / len(vals); sd = (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5 or 1
            return [(v - mu) / sd for v in vals]
        sc = [a + b for a, b in zip(z([x[2] for x in xs]), z([x[3] for x in xs]))]
        cut = sorted(sc)[int(len(sc) * 0.75)]
        for (g, t, _, _, sign), v in zip(xs, sc):
            m = sign * home_margin(g); fl = int(v >= cut)
            F["F3"].append(((g["s"], g["wk"]), g["s"], fl, m))
            if fl:
                ats["F3"].append(m)
    return F, ats, desc


HYP = {"F1": ("slope", -1, "주전 결장 차(홈−원정) → 홈 커버 마진 기울기(점/명)"),
       "F2": ("flag", -1, "주전 OL 2명+ 결장 팀 커버 마진"),
       "F3": ("flag", +1, "패스러시 미스매치 상위 25% 수비 팀 커버 마진"),
       "F4": ("slope", +1, "QB CPOE 차(홈−원정) → 홈 커버 마진 기울기(점/CPOE 1)"),
       "F5": ("flag", 0, "백업 QB 첫 선발 팀 커버 마진(양측)"),
       "F6": ("flag", -1, "총점: 주전 스킬 결장 합 2+ 또는 실외 바람 15mph+ → 총점 잔차")}


def run(seasons_main, rng, SO, PR, CP, BQ, label):
    F, A, D = build(seasons_main, SO, PR, CP, BQ)
    res = {}
    print(f"\n■ {label}")
    print("특징 | 가설 | n | 효과(관측) | 95% 구간 | 순열 p | 시즌 부호 일관 | 보조 ATS | 판정")
    for k in ("F1", "F2", "F3", "F4", "F5", "F6"):
        kind, sgn, txt = HYP[k]
        rows = F[k]
        if not rows:
            print(f"{k} | {txt} | 0"); continue
        obs, ci, p, seas, n = test(rows, kind, rng)
        cons = sum(1 for v in seas.values() if (v * sgn > 0 if sgn else v * obs > 0))
        ok = p <= ALPHA and (sgn == 0 or obs * sgn > 0)
        res[k] = (ok, obs, p)
        ats = ats_side(A[k])
        verdict = "통과(검증으로)" if ok else ("반대 방향 유의" if p <= ALPHA else "0과 미구분")
        print(f"{k} | {txt} | {n} | {obs:+.3f} | [{ci[0]:+.3f}, {ci[1]:+.3f}] | {p:.4f} | {cons}/{len(seas)} | {ats} | {verdict}")
    print("  (서술) 포지션군별 결장 차 기울기 — 검정 안 함:", " · ".join(f"{g} {slope([r[2] for r in D[g]], [r[3] for r in D[g]]):+.2f}" for g in ("OL", "WRTE", "CBS", "DLLB") if D[g]))
    for k in ("F6_skill", "F6_wind"):
        ys = [r[3] for r in D[k] if r[2]]
        if ys:
            print(f"  (서술) {k}: n {len(ys)} · 총점 잔차 평균 {sum(ys) / len(ys):+.2f} · 언더 {ats_side([-y for y in ys])}")
    return res


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(); ap.add_argument("--validate", action="store_true"); a = ap.parse_args()
    rng = random.Random(20261001)
    SO, PR, CP, BQ = starters_out(), pressure_asof(), cpoe_asof(), backup_first()
    disc = set(range(2013, 2023)); val = {2023, 2024, 2025}
    print(f"사전 등록 2026-10-01 · 유의 기준 p ≤ {ALPHA:.4f}(0.05/6, 양측) · 순열 {NPERM} · 부트스트랩 1000(시즌-주 묶음)")
    print("검정력: 커버 마진 SD≈13 → n=300 에서 평균 ±1.5점이 2σ — 그보다 작은 효과는 「있어도 못 본다」.")
    print("※ F3·F4 는 PFR·NGS 가 2018~ 이라 발견 구간이 2018~2022.")
    res = run(disc, rng, SO, PR, CP, BQ, "발견 구간 2013~2022")
    passed = [k for k, v in res.items() if v[0]]
    print(f"\n발견 통과: {', '.join(passed) or '없음'}")
    if a.validate and passed:
        rng2 = random.Random(20261002)
        F, A, _ = build(val, SO, PR, CP, BQ)
        print("\n■ 검증 구간 2023~2025 (발견 통과 특징만, 한 번)")
        for k in passed:
            kind, sgn, txt = HYP[k]
            obs, ci, p, seas, n = test(F[k], kind, rng2)
            cons = sum(1 for v in seas.values() if (v * sgn > 0 if sgn else v * res[k][1] > 0))
            print(f"{k} | {txt} | n {n} | {obs:+.3f} [{ci[0]:+.3f}, {ci[1]:+.3f}] | p {p:.4f} | 시즌 {cons}/{len(seas)} | ATS {ats_side(A[k])}")
    elif a.validate:
        print("검증 구간은 열지 않음(발견 통과 0).")


if __name__ == "__main__":
    main()
