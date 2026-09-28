"""모델 캘리브레이션 백테스트 — 지난 시즌 주차별로 「그 주 전까지의 데이터」로 레이팅을 만들고 마감 라인·결과와 대조.
  python backtest.py --seasons 2025 [--min-week 3] [--no-qb]
출력: 마진 MAE(모델/시장/혼합 k) · 스프레드 ATS 엣지 구간별(모델 방향 · 반대 방향) · 총점 O/U 구간별 · 잔차 SD.
QB 조정: nflverse 일정의 예상 선발 QB 가 그 주 전까지 드롭백 최다 QB 와 다르면 −QB_ADJ(실전 규칙 N4 와 같은 근사)."""
import argparse
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfl_pull as N  # noqa: E402


def ratings_asof(cur, prev, upto_week, teams):
    out = {}
    for t in teams:
        r = {}
        for side in ("off", "def"):
            s = n = 0.0
            for (tt, wk), v in cur.items():
                if tt == t and wk < upto_week and v.get(f"{side}_n"):
                    w = N.DECAY ** max(0, (upto_week - 1) - wk)
                    s += w * v[f"{side}_epa"]; n += w * v[f"{side}_n"]
            ps = pn = 0.0
            for (tt, wk), v in prev.items():
                if tt == t and v.get(f"{side}_n"):
                    ps += v[f"{side}_epa"]; pn += v[f"{side}_n"]
            prior = N.PRIOR_SHRINK * (ps / pn) if pn else 0.0
            r[side] = (s + prior * N.PRIOR_PLAYS) / (n + N.PRIOR_PLAYS)
        out[t] = r
    return out


def qb_dropbacks(pbp_path):
    """{(team, week): {passer: n}}"""
    db = defaultdict(lambda: defaultdict(int))
    for r in N.rd(pbp_path):
        if r.get("play_type") == "pass" and r.get("passer_player_name") and r.get("posteam") and r.get("season_type", "REG") == "REG":
            db[(r["posteam"], int(r["week"]))][r["passer_player_name"]] += 1
    return db


def main_qb_before(db, team, week):
    tot = defaultdict(int)
    for (t, wk), v in db.items():
        if t == team and wk < week:
            for p, n in v.items():
                tot[p] += n
    return max(tot, key=tot.get) if tot else None


def rec(xs, sign):
    w = sum(1 for r in xs if sign(r) > 0); l = sum(1 for r in xs if sign(r) < 0)
    return f"{w}-{l}" + (f" {100 * w / (w + l):.1f}%" if w + l else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", type=int, default=[2025])
    ap.add_argument("--min-week", type=int, default=3)
    ap.add_argument("--no-qb", action="store_true")
    a = ap.parse_args()
    games_all = N.rd(os.path.join(N.CACHE, "games.csv"))
    rows = []
    for season in a.seasons:
        pbp = os.path.join(N.CACHE, f"play_by_play_{season}.csv.gz")
        cur = N._team_week_epa(pbp, season)
        db = qb_dropbacks(pbp)
        pp = os.path.join(N.CACHE, f"play_by_play_{season - 1}.csv.gz")
        prev = N._team_week_epa(pp, season - 1) if os.path.exists(pp) else {}
        teams = sorted({t for t, _ in cur} | {t for t, _ in prev})
        gs = [g for g in games_all if g["season"] == str(season) and g["game_type"] == "REG" and g.get("result") and g.get("spread_line")]
        for wk in sorted({int(g["week"]) for g in gs}):
            if wk < a.min_week:
                continue
            rt = ratings_asof(cur, prev, wk, teams)
            done = [g for g in gs if int(g["week"]) < wk]
            pts = [N.fnum(g["home_score"]) for g in done] + [N.fnum(g["away_score"]) for g in done]
            lg = sum(pts) / len(pts) if pts else 22.0
            for g in gs:
                if int(g["week"]) != wk or g["home_team"] not in rt or g["away_team"] not in rt:
                    continue
                h, aw = g["home_team"], g["away_team"]
                oh, dh, oa, da = rt[h]["off"], rt[h]["def"], rt[aw]["off"], rt[aw]["def"]
                hfa = 0.0 if str(g.get("location", "")).lower() == "neutral" else N.HFA
                qh = qa = 0.0
                if not a.no_qb:
                    mh, ma = main_qb_before(db, h, wk), main_qb_before(db, aw, wk)
                    if g.get("home_qb_name") and mh and not N._same_person(mh, g["home_qb_name"]):
                        qh = -N.QB_ADJ
                    if g.get("away_qb_name") and ma and not N._same_person(ma, g["away_qb_name"]):
                        qa = -N.QB_ADJ
                margin = N.PLAYS * ((oh + da) - (oa + dh)) + hfa + qh - qa
                total = 2 * lg + N.PLAYS * ((oh + da) + (oa + dh)) + qh + qa
                rows.append(dict(season=season, week=wk, margin=margin, total=total, res=N.fnum(g["result"]), mk=N.fnum(g["spread_line"]),
                                 tl=N.fnum(g["total_line"]), tot=N.fnum(g["total"]), qb=bool(qh or qa)))
    if not rows:
        sys.exit("표본 없음")
    n = len(rows)
    mae = lambda f: sum(abs(f(r)) for r in rows) / n
    print(f"■ 표본 {n}경기(시즌 {a.seasons} · {a.min_week}주차~ · QB 조정 {'끔' if a.no_qb else '켬'} · QB 조정 경기 {sum(1 for r in rows if r['qb'])})")
    print(f"  마진 MAE — 모델 {mae(lambda r: r['margin'] - r['res']):.2f} · 시장(마감) {mae(lambda r: r['mk'] - r['res']):.2f}")
    for k in (0.0, 0.1, 0.2, 0.3, 0.5, 1.0):
        print(f"    혼합 최종 = 시장 + {k:.1f}×(모델−시장): MAE {mae(lambda r, k=k: (r['mk'] + k * (r['margin'] - r['mk'])) - r['res']):.2f}")
    tr = [r for r in rows if r["tl"] is not None and r["tot"] is not None]
    if tr:
        nt = len(tr)
        print(f"  총점 MAE — 모델 {sum(abs(r['total'] - r['tot']) for r in tr) / nt:.2f} · 시장 {sum(abs(r['tl'] - r['tot']) for r in tr) / nt:.2f}"
              + " · 혼합 " + " ".join(f"{k:.1f}:{sum(abs((r['tl'] + k * (r['total'] - r['tl'])) - r['tot']) for r in tr) / nt:.2f}" for k in (0.2, 0.4, 0.6)))
    print("\n■ 스프레드 ATS — |모델−시장| 구간별 · 모델 방향으로 걸었을 때(반대로 걸었을 때) · 푸시 제외")
    for lo, hi in [(0, 1), (1, 2), (2, 3.5), (3.5, 5), (5, 8), (8, 99)]:
        xs = [r for r in rows if lo <= abs(r["margin"] - r["mk"]) < hi]
        print(f"    {lo}~{hi}: {len(xs)}경기 모델 방향 {rec(xs, lambda r: (r['res'] - r['mk']) * (r['margin'] - r['mk']))}")
    q = [r for r in rows if r["qb"]]
    if q:
        print(f"    QB 조정 경기만: {len(q)}경기 모델 방향 {rec(q, lambda r: (r['res'] - r['mk']) * (r['margin'] - r['mk']))}")
    print("■ 총점 O/U — |모델−시장| 구간별 · 모델 방향")
    for lo, hi in [(0, 2), (2, 3), (3, 5), (5, 8), (8, 99)]:
        xs = [r for r in tr if lo <= abs(r["total"] - r["tl"]) < hi]
        print(f"    {lo}~{hi}: {len(xs)}경기 {rec(xs, lambda r: (r['tot'] - r['tl']) * (r['total'] - r['tl']))}")
    print(f"\n  잔차 SD — 모델 마진 {math.sqrt(sum((r['margin'] - r['res']) ** 2 for r in rows) / n):.1f} · 시장 {math.sqrt(sum((r['mk'] - r['res']) ** 2 for r in rows) / n):.1f}"
          f" · 총점 시장 {math.sqrt(sum((r['tl'] - r['tot']) ** 2 for r in tr) / len(tr)):.1f}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
