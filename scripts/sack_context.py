# -*- coding: utf-8 -*-
"""sack_context.py — 다이제스트 「색 맥락」 줄(값만 · 2026-11-22 Paul 「색 관련은 더 파줘봐」 → 결과 보고 → 「추천대로」).

검정(scripts/sack_lab2.py · data/sack_lab2_2026-11-22.md)에서 나온 것만 값으로 보여 준다 — 예측·★·판단·스프레드 픽을 바꾸지 않는다.
  · 색은 QB 쪽 값이 더 이어진다(시즌 전반→후반 상관: QB 본인 색률 0.48 · 공격 색 허용률 0.43 · 수비 색률 0.20).
  · 「색 잘 당하는 QB(본인 색률 상위 8) 대 색률 상위 8 수비」: 2018~25 수비 쪽 스프레드 79-113(41.1% · 8시즌 모두 50% 미만 · 시장 대비 −8.9%p) — 올해는 반대 방향.
정의는 검정과 같다: 수비 색률 = 그 주 전까지 색 ÷ 상대 드롭백(4경기+) · QB 색률 = 그 QB 의 올해(그 주 전) + 작년 색 ÷ 드롭백(150 드롭백+) · 순위 = 그 주 경기하는 팀 중.
    python scripts/sack_context.py --week 11
"""
import argparse, os, pickle, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfl_pull as N  # noqa: E402
import team_hex as TH  # noqa: E402

TOP = 8
HIST = "역사 2018~25 수비 쪽 스프레드 79-113(41.1% · 8시즌 모두 50% 미만 · 시장 대비 −8.9%p)"
PERSIST = "색은 QB 쪽 값이 더 이어진다(시즌 전반→후반 상관 — QB 본인 0.48 · 수비 0.20)"
_ST = {}


def state():
    """올해·작년 pbp → (off, dfn, qb, qprev). pbp 파일이 바뀔 때만 다시 읽는다(캐시 data/cache/sack_context_<시즌>.pkl)."""
    if "v" in _ST:
        return _ST["v"]
    import sack_lab2 as L2
    p = TH._p("play_by_play", N.SEASON)
    key = (os.path.getsize(p), int(os.path.getmtime(p))) if p else None
    cp = os.path.join(N.CACHE, f"sack_context_{N.SEASON}.pkl")
    if key and os.path.exists(cp):
        try:
            d = pickle.load(open(cp, "rb"))
            if d.get("key") == key:
                _ST["v"] = d["v"]
                return _ST["v"]
        except Exception:
            pass
    plain = lambda tbl: {k: {w: list(v) for w, v in d.items()} for k, d in tbl.items()}
    off, dfn, qb, _ = L2.load(N.SEASON)
    qprev = {}
    if TH._p("play_by_play", N.SEASON - 1):
        _, _, q0, _ = L2.load(N.SEASON - 1)
        qprev = {nm: (sum(x[0] for x in d.values()), sum(x[1] for x in d.values())) for nm, d in q0.items()}
    v = (plain(off), plain(dfn), plain(qb), qprev)
    if key:
        with open(cp + ".tmp", "wb") as f:
            pickle.dump({"key": key, "v": v}, f)
        os.replace(cp + ".tmp", cp)
    _ST["v"] = v
    return v


def team_vals(t, wk, qb_full):
    """→ {dsr, qsr, qb} (없는 값은 키 없음)."""
    off, dfn, qb, qprev = state()
    v = {}
    dw = [w for w in dfn.get(t, {}) if w < wk]
    if len(dw) >= 4:
        v["dsr"] = sum(dfn[t][w][1] for w in dw) / sum(dfn[t][w][0] for w in dw)
    if qb_full:
        n = s = 0.0
        for nm, d in qb.items():
            if N._same_person(nm, qb_full):
                for w, x in d.items():
                    if w < wk:
                        n += x[0]; s += x[1]
        for nm, (pn, ps) in qprev.items():
            if N._same_person(nm, qb_full):
                n += pn; s += ps
        if n >= 150:
            v["qsr"] = s / n; v["qb"] = qb_full
    return v


def week_table(wk, teams_qb):
    """teams_qb = {팀: 선발 QB 이름} → {팀: {dsr, qsr, qb, dsr_rank, qsr_rank}} — 순위는 값이 있는 팀 중(1 = 색률 가장 높음)."""
    T = {t: team_vals(t, wk, q) for t, q in teams_qb.items()}
    for k in ("dsr", "qsr"):
        order = sorted((t for t in T if k in T[t]), key=lambda t: -T[t][k])
        if len(order) >= 20:
            for i, t in enumerate(order):
                T[t][k + "_rank"] = i + 1
    return T


def flag(T, d_team, q_team):
    """「색 잘 당하는 QB(q_team) 대 색률 상위 8 수비(d_team)」 인가."""
    return T.get(d_team, {}).get("dsr_rank", 99) <= TOP and T.get(q_team, {}).get("qsr_rank", 99) <= TOP


def season_record(before_week=None):
    """올해 끝난 경기(5주차~) 중 조건 해당(한쪽만) → 수비 쪽 (스프레드 승, 패, 무, 승자 승, 패)."""
    games = [g for g in N.rd(os.path.join(N.CACHE, "games.csv")) if g["game_type"] == "REG" and int(g["season"]) == N.SEASON and g.get("result") not in (None, "") and g.get("spread_line")]
    byw = {}
    for g in games:
        byw.setdefault(int(g["week"]), []).append(g)
    w = l = p = sw = sl = 0
    for wk, gs in sorted(byw.items()):
        if wk < 5 or (before_week and wk >= before_week):
            continue
        T = week_table(wk, {t: q for g in gs for t, q in ((g["home_team"], g.get("home_qb_name")), (g["away_team"], g.get("away_qb_name")))})
        for g in gs:
            h, a = g["home_team"], g["away_team"]
            fh, fa = flag(T, h, a), flag(T, a, h)
            if fh == fa:
                continue
            res, mk = N.fnum(g["result"]), N.fnum(g["spread_line"])
            if res != 0:
                ok = (res > 0) == fh; sw += ok; sl += (not ok)
            cv = res - mk
            if cv == 0:
                p += 1
            else:
                ok = (cv > 0) == fh; w += ok; l += (not ok)
    return w, l, p, sw, sl


def digest_line(a, h, wk, inj, T=None):
    """경기 절 한 줄(값만). inj = {팀: injuries.csv 행}. 계산할 값이 없으면 ''."""
    if T is None:
        T = week_table(wk, {t: (x.get("expected_qb") or "") for t, x in inj.items()})
    va, vh = T.get(a, {}), T.get(h, {})
    if "dsr" not in va and "dsr" not in vh:
        return ""

    def d_(t, v):
        return f"{t} {100 * v['dsr']:.1f}%({v['dsr_rank']}위)" if "dsr" in v and "dsr_rank" in v else f"{t} 값 없음"

    def q_(t, v):
        return (f"{t} {v['qb']} {100 * v['qsr']:.1f}%({v['qsr_rank']}위" + (" — 색을 잘 당하는 쪽" if v["qsr_rank"] <= TOP else "") + ")") if "qsr" in v and "qsr_rank" in v else f"{t} 값 없음(드롭백 150 미만)"
    s = (f"- 🧱 색 맥락(값만 — 방향 근거 아님 · 순위 1 = 색률 가장 높음): 수비 색률 {d_(a, va)} / {d_(h, vh)} · 선발 QB 본인 색률 {q_(a, va)} / {q_(h, vh)} · {PERSIST}")
    fh, fa = flag(T, h, a), flag(T, a, h)
    if fh != fa:
        dt_, qt_ = (h, a) if fh else (a, h)
        try:
            w, l, p, sw, sl = season_record(before_week=wk)
            cur = f"올해 수비 쪽 스프레드 {w}-{l}" + (f"-{p}" if p else "") + f"(승자 {sw}-{sl})"
        except Exception as e:
            cur = f"올해 값 계산 실패({type(e).__name__})"
        s += f" · 해당: 색 잘 당하는 QB({qt_}) 대 색률 상위 {TOP} 수비({dt_}) — {HIST} · {cur} · 역사와 올해가 반대 방향이라 관찰 값으로만"
    return s


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--week", type=int, required=True); a = ap.parse_args()
    wd = N.week_dir(a.week)
    inj = {r["team"]: r for r in N.rd(os.path.join(wd, "injuries.csv"))}
    T = week_table(a.week, {t: (x.get("expected_qb") or "") for t, x in inj.items()})
    for g in N.rd(os.path.join(wd, "games.csv")):
        print(f'{g["away"]}@{g["home"]}', digest_line(g["away"], g["home"], a.week, inj, T))
    print("올해 기록(수비 쪽 스프레드 승-패-무 · 승자 승-패):", season_record())
