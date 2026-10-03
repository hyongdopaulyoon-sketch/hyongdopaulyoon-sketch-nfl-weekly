"""선수 기반 득점 모델 — 팀 EPA 모델 + 「그 주 실제로 뛰는 선수」 조정(2026-10-03 사전 등록, pending_rules 같은 날 줄).
  python player_model.py --backtest            발견 구간 2018~2022 판정만
  python player_model.py --backtest --validate 발견 통과 때만 검증 구간 2023~2025 를 한 번 연다
선수 조정(공격만 — 무료 데이터에 수비·OL 개인 기록이 없다):
  QB   = 실제 선발의 개인 드롭백 EPA(수축 k=150, 사전값 = 직전 시즌 드롭백 <150 QB 평균 = 대체 수준) − 팀 최근 4경기 드롭백 가중 QB 값
  리시버 = 개인 EPA/타깃의 (팀·경기 평균 대비) 잔차(k=50) × (Out/Doubtful 빼고 다시 나눈 타깃 점유율 − 최근 4경기 점유율)
  러셔  = 같은 방식(EPA/캐리 잔차, k=60, 캐리 점유율)
  공격 EPA 조정 = 패스 비중 × (QB + 리시버) + (1 − 패스 비중) × 러셔 · 점수 = PLAYS × 조정."""
import argparse, csv, gzip, math, os, pickle, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nfl_pull as N   # noqa: E402

HIST = os.path.join(N.CACHE, "hist")
K_QB, K_REC, K_RUSH, QB_REPL_N, HIST_GAMES = 150.0, 50.0, 60.0, 150, 4
TEAM = {"OAK": "LV", "SD": "LAC", "STL": "LA", "LAR": "LA"}


def tm(t):
    return TEAM.get(t, t)


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def compact(season):
    """정규시즌 pass/run 플레이 → [(week, game_id, posteam, defteam, dropback, epa, qb_id, rec_id, rush_id)] (pickle 캐시)."""
    pk = os.path.join(HIST, f"pbp_compact_{season}.pkl")
    if os.path.exists(pk):
        return pickle.load(open(pk, "rb"))
    src = os.path.join(HIST, f"play_by_play_{season}.csv.gz")
    if not os.path.exists(src):
        src = os.path.join(N.CACHE, f"play_by_play_{season}.csv.gz")
    out = []
    with gzip.open(src, "rt", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("season_type", "REG") != "REG" or r.get("play_type") not in ("pass", "run") or not r.get("posteam"):
                continue
            e = f(r.get("epa"))
            if e is None:
                continue
            db = f(r.get("qb_dropback")) == 1
            qb = (r.get("passer_player_id") or r.get("rusher_player_id")) if db else ""
            out.append((int(r["week"]), r["game_id"], tm(r["posteam"]), tm(r["defteam"]), db, e, qb or "",
                        r.get("receiver_player_id") or "" if db else "", "" if db else (r.get("rusher_player_id") or "")))
    pickle.dump(out, open(pk + ".tmp", "wb")); os.replace(pk + ".tmp", pk)
    return out


def team_week(plays):
    """{(team, week): {off_epa, off_n, def_epa, def_n}} — backtest.ratings_asof 와 같은 꼴."""
    cur = defaultdict(lambda: defaultdict(float))
    for wk, _g, pt, dt, _db, e, *_ in plays:
        cur[(pt, wk)]["off_epa"] += e; cur[(pt, wk)]["off_n"] += 1
        cur[(dt, wk)]["def_epa"] += e; cur[(dt, wk)]["def_n"] += 1
    return cur


def player_ratings(prev, cur_before, repl):
    """QB·리시버·러셔 개인 값(수축). prev = 직전 시즌 전부, cur_before = 이번 시즌 그 주 전."""
    plays = prev + cur_before
    qs, qn = defaultdict(float), defaultdict(int)
    gm_t, gm_r = defaultdict(lambda: [0.0, 0]), defaultdict(lambda: [0.0, 0])
    for wk, g, pt, dt, db, e, qb, rec, ru in plays:
        if db and qb:
            qs[qb] += e; qn[qb] += 1
        if db and rec:
            gm_t[(g, pt)][0] += e; gm_t[(g, pt)][1] += 1
        if (not db) and ru:
            gm_r[(g, pt)][0] += e; gm_r[(g, pt)][1] += 1
    rs, rn, us, un = defaultdict(float), defaultdict(int), defaultdict(float), defaultdict(int)
    for wk, g, pt, dt, db, e, qb, rec, ru in plays:
        if db and rec:
            m = gm_t[(g, pt)]; rs[rec] += e - m[0] / m[1]; rn[rec] += 1
        if (not db) and ru:
            m = gm_r[(g, pt)]; us[ru] += e - m[0] / m[1]; un[ru] += 1
    q = {p: (qs[p] + repl * K_QB) / (qn[p] + K_QB) for p in qs}
    r = {p: rs[p] / (rn[p] + K_REC) for p in rs}
    u = {p: us[p] / (un[p] + K_RUSH) for p in us}
    return q, r, u


def replacement_qb(prev):
    s, n = defaultdict(float), defaultdict(int)
    for wk, g, pt, dt, db, e, qb, *_ in prev:
        if db and qb:
            s[qb] += e; n[qb] += 1
    low = [qb for qb in n if n[qb] < QB_REPL_N]
    tot = sum(n[x] for x in low)
    return sum(s[x] for x in low) / tot if tot else 0.0


def team_hist(cur_before, prev, team):
    """팀 최근 4경기(이번 시즌 2경기 미만이면 직전 시즌 끝 4경기) 사용량: QB 드롭백·타깃·캐리·드롭백 비율."""
    def games_of(pl):
        gs = sorted({(wk, g) for wk, g, pt, *_ in pl if pt == team})
        return [g for _wk, g in gs[-HIST_GAMES:]]
    gs = games_of(cur_before)
    src = cur_before
    if len(gs) < 2:
        gs, src = games_of(prev), prev
    gs = set(gs)
    qd, tg, ca = defaultdict(int), defaultdict(int), defaultdict(int)
    ndb = nrun = 0
    for wk, g, pt, dt, db, e, qb, rec, ru in src:
        if pt != team or g not in gs:
            continue
        if db:
            ndb += 1
            if qb:
                qd[qb] += 1
            if rec:
                tg[rec] += 1
        else:
            nrun += 1
            if ru:
                ca[ru] += 1
    return qd, tg, ca, (ndb / (ndb + nrun) if ndb + nrun else 0.58)


def adjust(team, starter, outs, q, r, u, repl, hist):
    """공격 EPA/플레이 조정과 내역."""
    qd, tg, ca, pf = hist
    tot_q = sum(qd.values())
    q_hist = sum(n * q.get(p, repl) for p, n in qd.items()) / tot_q if tot_q else repl
    q_exp = q.get(starter, repl) if starter else q_hist
    dq = q_exp - q_hist

    def share_shift(cnt, val):
        tot = sum(cnt.values())
        if not tot:
            return 0.0, []
        sh = {p: n / tot for p, n in cnt.items()}
        av = {p: s for p, s in sh.items() if p not in outs}
        z = sum(av.values())
        if z <= 0:
            return 0.0, []
        new = {p: (av.get(p, 0.0) / z) for p in sh}
        missing = [p for p in sh if p in outs]
        return sum((new[p] - sh[p]) * val.get(p, 0.0) for p in sh), missing
    dr, miss_r = share_shift(tg, r)
    du, miss_u = share_shift(ca, u)
    return pf * (dq + dr) + (1 - pf) * du, dict(dq=dq, dr=dr, du=du, pf=pf, miss_r=miss_r, miss_u=miss_u)


def outs_of(season, week):
    p = os.path.join(HIST, f"injuries_{season}.csv")
    return {r["gsis_id"] for r in N.rd(p) if r.get("game_type", "REG") == "REG" and r.get("week") == str(week)
            and r.get("report_status") in ("Out", "Doubtful") and r.get("gsis_id")}


def ratings_asof(cur, prev_tw, upto_week, teams):
    out = {}
    for t in teams:
        rr = {}
        for side in ("off", "def"):
            s = n = 0.0
            for (tt, wk), v in cur.items():
                if tt == t and wk < upto_week and v.get(f"{side}_n"):
                    w = N.DECAY ** max(0, (upto_week - 1) - wk)
                    s += w * v[f"{side}_epa"]; n += w * v[f"{side}_n"]
            ps = pn = 0.0
            for (tt, wk), v in prev_tw.items():
                if tt == t and v.get(f"{side}_n"):
                    ps += v[f"{side}_epa"]; pn += v[f"{side}_n"]
            prior = N.PRIOR_SHRINK * (ps / pn) if pn else 0.0
            rr[side] = (s + prior * N.PRIOR_PLAYS) / (n + N.PRIOR_PLAYS)
        out[t] = rr
    return out


def season_rows(season, games_all):
    cur_all, prev = compact(season), compact(season - 1)
    prev_tw = team_week(prev)
    repl = replacement_qb(prev)
    gs = [g for g in games_all if g["season"] == str(season) and g["game_type"] == "REG" and g.get("result") and g.get("spread_line")]
    rows = []
    for wk in sorted({int(g["week"]) for g in gs}):
        if wk < 3:
            continue
        before = [x for x in cur_all if x[0] < wk]
        cur_tw = team_week(before)
        teams = sorted({t for t, _ in cur_tw} | {t for t, _ in prev_tw})
        rt = ratings_asof(cur_tw, prev_tw, wk, teams)
        q, r, u = player_ratings(prev, before, repl)
        outs = outs_of(season, wk)
        done = [g for g in gs if int(g["week"]) < wk]
        pts = [f(g["home_score"]) for g in done] + [f(g["away_score"]) for g in done]
        lg = sum(pts) / len(pts) if pts else 22.0
        for g in gs:
            if int(g["week"]) != wk:
                continue
            h, a = tm(g["home_team"]), tm(g["away_team"])
            if h not in rt or a not in rt:
                continue
            oh, dh, oa, da = rt[h]["off"], rt[h]["def"], rt[a]["off"], rt[a]["def"]
            hfa = 0.0 if str(g.get("location", "")).lower() == "neutral" else N.HFA
            m_team = N.PLAYS * ((oh + da) - (oa + dh)) + hfa
            t_team = 2 * lg + N.PLAYS * ((oh + da) + (oa + dh))
            ah, dh_ = adjust(h, g.get("home_qb_id"), outs, q, r, u, repl, team_hist(before, prev, h))
            aa, da_ = adjust(a, g.get("away_qb_id"), outs, q, r, u, repl, team_hist(before, prev, a))
            rows.append(dict(season=season, week=wk, mk=f(g["spread_line"]), res=f(g["result"]), tl=f(g["total_line"]), tot=f(g["total"]),
                             m_team=m_team, t_team=t_team, adj_m=N.PLAYS * (ah - aa), adj_t=N.PLAYS * (ah + aa),
                             m_pl=m_team + N.PLAYS * (ah - aa), t_pl=t_team + N.PLAYS * (ah + aa)))
    return rows


def ats(xs, sign):
    w = sum(1 for x in xs if sign(x) > 0); l = sum(1 for x in xs if sign(x) < 0)
    return w, l


def report(rows, label):
    n = len(rows)
    print(f"\n■ {label} — {n}경기")
    mae = lambda fn: sum(abs(fn(x)) for x in rows) / n
    print(f"  마진 MAE(결과 대비) — 시장 {mae(lambda x: x['mk'] - x['res']):.3f} · 팀 모델 {mae(lambda x: x['m_team'] - x['res']):.3f} · 선수 모델 {mae(lambda x: x['m_pl'] - x['res']):.3f}")
    best = min(((k, mae(lambda x, k=k: x['mk'] + k * (x['m_pl'] - x['mk']) - x['res'])) for k in [i / 20 for i in range(0, 21)]), key=lambda v: v[1])
    base = mae(lambda x: x['mk'] - x['res'])
    print(f"  ⓐ 시장 혼합: 최적 k={best[0]:.2f} · MAE {best[1]:.3f}(시장 대비 {base - best[1]:+.3f})")
    big = [x for x in rows if abs(x["m_pl"] - x["mk"]) >= 2]
    w, l = ats(big, lambda x: (x["res"] - x["mk"]) * (x["m_pl"] - x["mk"]))
    by = defaultdict(lambda: [0, 0])
    for x in big:
        s_ = (x["res"] - x["mk"]) * (x["m_pl"] - x["mk"])
        if s_:
            by[x["season"]][0 if s_ > 0 else 1] += 1
    up = sum(1 for a_, b_ in by.values() if a_ + b_ and a_ / (a_ + b_) > 0.524)
    print(f"  ⓑ |선수 모델−시장| ≥2점: {len(big)}경기 모델 방향 {w}-{l} {100 * w / max(w + l, 1):.1f}% · 손익분기 위 시즌 {up}/{len(by)}")
    adj = [x for x in rows if abs(x["adj_m"]) >= 1.5]
    w2, l2 = ats(adj, lambda x: (x["res"] - x["mk"]) * x["adj_m"])
    print(f"  ⓒ 선수 조정 |≥1.5점| 경기: {len(adj)}경기 조정 방향 {w2}-{l2} {100 * w2 / max(w2 + l2, 1):.1f}%")
    tr = [x for x in rows if x["tl"] is not None and x["tot"] is not None]
    if tr:
        print(f"  총점 MAE — 시장 {sum(abs(x['tl'] - x['tot']) for x in tr) / len(tr):.3f} · 팀 {sum(abs(x['t_team'] - x['tot']) for x in tr) / len(tr):.3f} · 선수 {sum(abs(x['t_pl'] - x['tot']) for x in tr) / len(tr):.3f}")
        ta = [x for x in tr if abs(x["adj_t"]) >= 1.5]
        w3, l3 = ats(ta, lambda x: (x["tot"] - x["tl"]) * x["adj_t"])
        print(f"    (보조) 총점 선수 조정 |≥1.5점| {len(ta)}경기 조정 방향 {w3}-{l3} {100 * w3 / max(w3 + l3, 1):.1f}%")
    print(f"  (보조) 선수 조정 크기: |조정| 평균 {sum(abs(x['adj_m']) for x in rows) / n:.2f}점 · ≥1.5점 {len(adj)}경기 · ≥3점 {sum(1 for x in rows if abs(x['adj_m']) >= 3)}경기")
    pa = best[0] > 0 and base - best[1] >= 0.05
    pb = (w + l) and w / (w + l) >= 0.535 and up >= 3
    pc = len(adj) >= 150 and (w2 + l2) and w2 / (w2 + l2) >= 0.535
    return pa or pb or pc, (pa, pb, pc)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--backtest", action="store_true"); ap.add_argument("--validate", action="store_true")
    a = ap.parse_args()
    games_all = N.rd(os.path.join(N.CACHE, "games.csv"))
    if a.backtest:
        disc = [x for s in range(2018, 2023) for x in season_rows(s, games_all)]
        ok, parts = report(disc, "발견 구간 2018~2022 (사전 등록 판정)")
        print(f"\n발견 판정: ⓐ {parts[0]} · ⓑ {bool(parts[1])} · ⓒ {bool(parts[2])} → {'통과 — 검증 대상' if ok else '불통과 — 서술 전용'}")
        if a.validate and ok:
            val = [x for s in range(2023, 2026) for x in season_rows(s, games_all)]
            ok2, parts2 = report(val, "검증 구간 2023~2025 (한 번)")
            print(f"\n검증 판정: {parts2} → {'통과' if ok2 else '불통과'}")
        elif a.validate:
            print("검증 구간은 열지 않음(발견 불통과).")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
