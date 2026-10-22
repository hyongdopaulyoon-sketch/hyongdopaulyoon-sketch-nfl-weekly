"""외부 재료 백테스트 E1~E6 — 심판 경향 · 키커 거리별 · OL 연속성이 마감 라인 대비 잔차를 설명하는가 (2026-10-21 사전 등록, pending_rules.md 같은 날 줄).
  python scripts/backtest_extdata.py
데이터: nflverse 미러만 — data/cache/games.csv · data/cache/hist/play_by_play_2016~2025.csv.gz · snap_counts_2018~2025 · injuries_2018~2025.
목표 변수: ML 잔차(그 쪽 실제 승 1/무 0.5/패 0 − 마감 무비그 확률) · ATS 커버 마진(결과 − spread_line) · 총점 잔차(E2·E3, 실제 − total_line).
판정: 시즌-주 묶음 부트스트랩 95% 구간 · 같은 시즌-주 안 순열 2,000회(backtest_features.test 재사용) · 1차 검정 10개 2018~25 합 p 를 BH 보정 q ≤ 0.05
      + 가설 방향 + 전(2018~23)·후(2024~25) 점추정 모두 가설 방향. 정의·문턱은 사전 등록 그대로 — 결과를 보고 고치지 않는다.
재료 정의는 기존 코드와 같은 꼴: 심판 = context_blocks._ref_season · 키커 = context_blocks.FG_BANDS(40~49 · 50+) · OL = adv_players.ol_continuity(IR 제외)."""
import csv, gzip, os, random, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import situations as S          # noqa: E402  (tm · norm · rd · f)
import backtest_features as BF  # noqa: E402  (test · slope)

HIST = S.HIST
SEED = 20261021
SEASONS = range(2018, 2026)
PRE, POST = set(range(2018, 2024)), {2024, 2025}
REF_MIN = 16
KICK_MIN = 15
LONG_BANDS = ((40, 49), (50, 99))
OL_POS = {"T", "G", "C", "OL", "OT", "OG", "LT", "RT", "LG", "RG"}
f = S.f


def pimp(am):
    am = f(am)
    if am is None or am == 0:
        return None
    return 100 / (am + 100) if am > 0 else -am / (-am + 100)


# ── 경기 ──
def load_games():
    out = []
    for g in S.rd(os.path.join(S.CACHE, "games.csv")):
        s = int(g["season"])
        if g["game_type"] != "REG" or not (2016 <= s <= 2025) or f(g["result"]) is None:
            continue
        x = dict(game_id=g["game_id"], s=s, wk=int(g["week"]), a=S.tm(g["away_team"]), h=S.tm(g["home_team"]), ref=g.get("referee") or "",
                 res=f(g["result"]), sp=f(g["spread_line"]), tot=f(g["total"]), tl=f(g["total_line"]), ph=None)
        ph, pa = pimp(g["home_moneyline"]), pimp(g["away_moneyline"])
        if ph and pa:
            x["ph"] = ph / (ph + pa)
        out.append(x)
    return out


def ml_res_home(g):
    if g["ph"] is None:
        return None
    won = 1.0 if g["res"] > 0 else 0.5 if g["res"] == 0 else 0.0
    return won - g["ph"]


# ── pbp 추출(캐시) ──
def pbp_extract():
    """→ (kicks [(season, wk, stype, seq, game_id, team, kicker, kind, dist, made)], pen {game_id: 정규시즌 페널티 수})."""
    kp, pp = os.path.join(HIST, "extdata_kicks.csv"), os.path.join(HIST, "extdata_pen.csv")
    if os.path.exists(kp) and os.path.exists(pp):
        kicks = [(int(r["season"]), int(r["week"]), r["stype"], int(r["seq"]), r["game_id"], r["team"], r["kicker"], r["kind"], float(r["dist"]), int(r["made"]))
                 for r in S.rd(kp)]
        return kicks, {r["game_id"]: int(r["pen"]) for r in S.rd(pp)}
    kicks, pen = [], defaultdict(int); seq = 0
    for s in range(2016, 2026):
        src = os.path.join(HIST, f"play_by_play_{s}.csv.gz")
        with gzip.open(src, "rt", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                st = r.get("season_type", "REG")
                if st == "REG" and r.get("penalty") in ("1", "1.0"):
                    pen[r["game_id"]] += 1
                fg, xp = f(r.get("field_goal_attempt")) == 1, f(r.get("extra_point_attempt")) == 1
                if not (fg or xp) or not r.get("kicker_player_id"):
                    continue
                seq += 1
                made = (r.get("field_goal_result") == "made") if fg else (r.get("extra_point_result") == "good")
                kicks.append((s, int(r["week"]), st, seq, r["game_id"], S.tm(r["posteam"]), r["kicker_player_id"], "fg" if fg else "xp",
                              f(r.get("kick_distance")) or 0.0, int(made)))
        print(f"  pbp {s} 추출", file=sys.stderr)
    with open(kp, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["season", "week", "stype", "seq", "game_id", "team", "kicker", "kind", "dist", "made"]); w.writerows(kicks)
    with open(pp, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["game_id", "pen"]); w.writerows(pen.items())
    return kicks, dict(pen)


def in_window(s, w, ks, kw, kst):
    """as-of 창: 직전 두 시즌 전체 + 이번 시즌 이번 주 전 정규시즌."""
    return (s - 2 <= ks <= s - 1) or (ks == s and kst == "REG" and kw < w)


# ── E1~E3 심판 ──
def referee_feats(G, pen):
    by_ref = defaultdict(list)
    for g in G:
        if g["ref"]:
            by_ref[g["ref"]].append(g)
    league = {}
    out = {}
    for g in G:
        if g["s"] not in SEASONS or not g["ref"]:
            continue
        key = (g["s"], g["wk"])
        if key not in league:
            win = [x for x in G if x["ref"] and in_window(g["s"], g["wk"], x["s"], x["wk"], "REG") and x["game_id"] in pen]
            league[key] = sum(pen[x["game_id"]] for x in win) / max(len(win), 1)
        win = [x for x in by_ref[g["ref"]] if in_window(g["s"], g["wk"], x["s"], x["wk"], "REG")]
        if len(win) < REF_MIN:
            continue
        cov = [(x["res"] - x["sp"]) > 0 for x in win if x["sp"] is not None and x["res"] != x["sp"]]
        ovr = [x["tot"] > x["tl"] for x in win if x["tl"] is not None and x["tot"] is not None and x["tot"] != x["tl"]]
        pw = [pen[x["game_id"]] for x in win if x["game_id"] in pen]
        out[g["game_id"]] = dict(hcov=sum(cov) / len(cov) - 0.5 if cov else None, over=sum(ovr) / len(ovr) - 0.5 if ovr else None,
                                 pen=(sum(pw) / len(pw) - league[key]) if pw else None, n=len(win))
    return out


# ── E4 키커 ──
def kicker_feats(G, kicks):
    fgs = [k for k in kicks if k[7] == "fg" and k[8] >= 40]
    by_k = defaultdict(list)
    for k in fgs:
        by_k[k[6]].append(k)
    by_team = defaultdict(list)
    for k in kicks:
        by_team[k[5]].append(k)
    for t in by_team:
        by_team[t].sort(key=lambda k: k[3])
    band = lambda d: 0 if d < 50 else 1
    league = {}
    out = {}
    for g in G:
        if g["s"] not in SEASONS:
            continue
        key = (g["s"], g["wk"])
        if key not in league:
            c = [[0, 0], [0, 0]]
            for k in fgs:
                if in_window(g["s"], g["wk"], k[0], k[1], k[2]):
                    c[band(k[8])][0] += 1; c[band(k[8])][1] += k[9]
            league[key] = [m / a if a else 0 for a, m in c]
        q = {}
        for t in (g["h"], g["a"]):
            prior = [k for k in by_team[t] if k[0] < g["s"] or (k[0] == g["s"] and k[2] == "REG" and k[1] < g["wk"])]
            if not prior:
                break
            kid = prior[-1][6]
            att = [k for k in by_k[kid] if in_window(g["s"], g["wk"], k[0], k[1], k[2])]
            if len(att) < KICK_MIN:
                break
            q[t] = sum(k[9] - league[key][band(k[8])] for k in att) / len(att)
        if len(q) == 2:
            out[g["game_id"]] = q[g["h"]] - q[g["a"]]
    return out


# ── E5·E6 OL 연속성 ──
def ol_feats():
    """{(season, team, week): 상위 5 OL 중 Out/Doubtful 수} — 직전 3경기 미만이면 없음."""
    out = {}
    for s in SEASONS:
        snaps = [r for r in S.rd(os.path.join(HIST, f"snap_counts_{s}.csv")) if r.get("game_type", "REG") == "REG"]
        team_weeks = defaultdict(set); ol = defaultdict(lambda: defaultdict(float))
        for r in snaps:
            t = S.tm(r["team"]); w = int(r["week"]); team_weeks[t].add(w)
            if r.get("position") in OL_POS:
                ol[(t, w)][S.norm(r["player"])] += f(r.get("offense_snaps")) or 0
        od = defaultdict(set)
        for r in S.rd(os.path.join(HIST, f"injuries_{s}.csv")):
            if r.get("game_type", "REG") == "REG" and r.get("report_status") in ("Out", "Doubtful"):
                od[(S.tm(r["team"]), int(r["week"]))].add(S.norm(r["full_name"]))
        for t, wks in team_weeks.items():
            for w in range(1, 23):
                prev = sorted(x for x in wks if x < w)[-3:]
                if len(prev) < 3:
                    continue
                tot = defaultdict(float)
                for x in prev:
                    for p, v in ol[(t, x)].items():
                        tot[p] += v
                top = [p for p, _ in sorted(tot.items(), key=lambda kv: -kv[1])[:5]]
                out[(s, t, w)] = sum(1 for p in top if p in od.get((t, w), ()))
    return out


# ── 검정 ──
HYP = [  # (id, 목표, kind, 가설 부호, 설명)
    ("E1", "ml", "slope", +1, "심판 홈 커버율−.5 → 홈 ML 잔차 기울기"),
    ("E1", "ats", "slope", +1, "심판 홈 커버율−.5 → 홈 커버 마진 기울기(점)"),
    ("E2", "tot", "slope", +1, "심판 Over율−.5 → 총점 잔차 기울기(점)"),
    ("E3", "tot", "slope", 0, "심판 경기당 페널티−리그 → 총점 잔차 기울기(점/개, 양측)"),
    ("E4", "ml", "slope", +1, "키커 40+ 기대 대비 차(홈−원정) → 홈 ML 잔차 기울기"),
    ("E4", "ats", "slope", +1, "키커 40+ 기대 대비 차(홈−원정) → 홈 커버 마진 기울기(점)"),
    ("E5", "ml", "slope", -1, "OL 결장 수 차(홈−원정) → 홈 ML 잔차 기울기(/명)"),
    ("E5", "ats", "slope", -1, "OL 결장 수 차(홈−원정) → 홈 커버 마진 기울기(점/명)"),
    ("E6", "ml", "flag", -1, "OL 2명+ 결장 팀 ML 잔차 평균"),
    ("E6", "ats", "flag", -1, "OL 2명+ 결장 팀 커버 마진 평균(점)"),
]


def build_rows(G, RF, KF, OF):
    R = defaultdict(list)   # (id, 목표) -> [(cl, season, x, y)]
    aux = defaultdict(list)  # (id, 목표) -> [(season, 그 쪽 커버 True/False)] — 보조 ATS%
    for g in G:
        if g["s"] not in SEASONS:
            continue
        cl = (g["s"], g["wk"]); mr = ml_res_home(g)
        m = g["res"] - g["sp"] if g["sp"] is not None else None
        tr = g["tot"] - g["tl"] if g["tl"] is not None and g["tot"] is not None else None

        def add_slope(hid, x, sgn):
            if x is None:
                return
            if mr is not None:
                R[(hid, "ml")].append((cl, g["s"], x, mr))
            if m is not None:
                R[(hid, "ats")].append((cl, g["s"], x, m))
                if x != 0 and m != 0:
                    aux[(hid, "ats")].append((g["s"], (m > 0) == (x * sgn > 0)))   # 가설이 고르는 쪽 커버
        rf = RF.get(g["game_id"])
        if rf:
            add_slope("E1", rf["hcov"], +1)
            for hid, k, sgn in (("E2", "over", +1), ("E3", "pen", +1)):
                if rf[k] is not None and tr is not None:
                    R[(hid, "tot")].append((cl, g["s"], rf[k], tr))
                    if rf[k] != 0 and tr != 0:
                        aux[(hid, "tot")].append((g["s"], (tr > 0) == (rf[k] > 0)))   # E3 은 「페널티 많으면 Over」 쪽 표기
        add_slope("E4", KF.get(g["game_id"]), +1)
        oh, oa = OF.get((g["s"], g["h"], g["wk"])), OF.get((g["s"], g["a"], g["wk"]))
        if oh is not None and oa is not None:
            add_slope("E5", oh - oa, -1)
            for c, sign in ((oh, 1), (oa, -1)):
                fl = int(c >= 2)
                if mr is not None:
                    R[("E6", "ml")].append((cl, g["s"], fl, sign * mr))
                if m is not None:
                    R[("E6", "ats")].append((cl, g["s"], fl, sign * m))
                    if fl and m != 0:
                        aux[("E6", "ats")].append((g["s"], (sign * m) > 0))       # 결장 팀 커버
    return R, aux


def bh(ps):
    n = len(ps); order = sorted(range(n), key=lambda i: ps[i]); q = [0.0] * n; prev = 1.0
    for rank, i in reversed(list(enumerate(order, 1))):
        prev = min(prev, ps[i] * n / rank); q[i] = prev
    return q


def ats_txt(xs):
    w = sum(1 for _, ok in xs if ok); n = len(xs)
    return f"{w}-{n - w} {100 * w / n:.1f}%" if n else "—"


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    rng = random.Random(SEED)
    G = load_games()
    kicks, pen = pbp_extract()
    RF, KF, OF = referee_feats(G, pen), kicker_feats(G, kicks), ol_feats()
    R, aux = build_rows(G, RF, KF, OF)
    print(f"사전 등록 2026-10-21 · 순열 {BF.NPERM}(시즌-주 안) · 부트스트랩 1000(시즌-주 묶음) · seed {SEED} · BH q ≤ 0.05(1차 10개, 2018~25 합 p)")
    res = []
    for hid, tgt, kind, sgn, txt in HYP:
        rows = R[(hid, tgt)]
        out = {}
        for lab, ss in (("합 2018~25", set(SEASONS)), ("전 2018~23", PRE), ("후 2024~25", POST)):
            rs = [r for r in rows if r[1] in ss]
            out[lab] = BF.test(rs, kind, rng)
        res.append((hid, tgt, kind, sgn, txt, out))
    q = bh([r[5]["합 2018~25"][2] for r in res])
    print("\n| 가설 | 목표 | 구간 | n | 효과 | 95% 구간 | 순열 p | BH q | 시즌 +/n | 보조 ATS/OU |\n|---|---|---|---|---|---|---|---|---|---|")
    verdicts = []
    for (hid, tgt, kind, sgn, txt, out), qq in zip(res, q):
        for lab in ("합 2018~25", "전 2018~23", "후 2024~25"):
            obs, ci, p, seas, n = out[lab]
            ss = set(SEASONS) if lab.startswith("합") else PRE if lab.startswith("전") else POST
            ref = sgn if sgn else (1 if out["합 2018~25"][0] > 0 else -1)
            cons = sum(1 for v in seas.values() if v * ref > 0)
            ax = [x for x in aux.get((hid, tgt), []) if x[0] in ss]
            print(f"| {hid} {txt} | {tgt} | {lab} | {n} | {obs:+.4f} | [{ci[0]:+.4f}, {ci[1]:+.4f}] | {p:.4f} | {f'{qq:.3f}' if lab.startswith('합') else ''} | {cons}/{len(seas)} | {ats_txt(ax)} |")
        o_all, o_pre, o_post = (out[k][0] for k in ("합 2018~25", "전 2018~23", "후 2024~25"))
        if sgn:
            ok = qq <= 0.05 and o_all * sgn > 0 and o_pre * sgn > 0 and o_post * sgn > 0
        else:
            ok = qq <= 0.05 and o_pre * o_post > 0
        why = []
        if qq > 0.05:
            why.append(f"q {qq:.3f}>0.05")
        if sgn and o_all * sgn <= 0:
            why.append("합 효과가 가설 반대")
        if (sgn and (o_pre * sgn <= 0 or o_post * sgn <= 0)) or (not sgn and o_pre * o_post <= 0):
            why.append("전·후 방향 불일치")
        verdicts.append((hid, tgt, ok, why))
    print("\n판정:")
    for hid, tgt, ok, why in verdicts:
        print(f"  {hid}·{tgt}: {'통과 → 각도 후보 제안' if ok else '서술 전용 유지'}" + (f" ({' · '.join(why)})" if why else ""))
    print(f"\n표본: 심판 재료 {len(RF)}경기 · 키커 재료 {len(KF)}경기 · OL 재료 팀-주 {len(OF)}")


if __name__ == "__main__":
    main()
