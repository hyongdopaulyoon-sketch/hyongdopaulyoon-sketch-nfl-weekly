# -*- coding: utf-8 -*-
"""sack_allow_watch.py — 공격 색 허용률 차가 큰 경기 지켜보기(2026-11-25 Paul 「허용률 차이 큰 경기도 지켜보는걸로 하자」).

계기: 12주차 GB@LA — 공격 색 허용률 GB 6.3% / LA 3.8%(차 2.5%p)인데 수비 색률 차는 1.2%p. Paul 「허용율 차이가 크잖아 수비색율은 차이 근소」.
정의(실행 전 고정 · 바꾸지 않는다):
  · 공격 색 허용률 = 그 경기 전까지 시즌 누적 색 ÷ 드롭백(4경기+ · pbp qb_dropback 기준 — sack_lab2 의 osr 과 같음)
  · 해당 = 두 팀 차 2.0%p 이상 → 「낮은 쪽」(색을 덜 당하는 팀) · 보조 구간 3.0%p 이상 · 5주차~
  · 첫 숫자 = 낮은 쪽 승-패와 시장 기대 승률(무비그 ML) · 스프레드 승-패는 참고
값만 — 예측·★·판단·스프레드 픽·각도를 바꾸지 않는다. 다이제스트 「🧱 색 맥락」 줄 꼬리(해당 경기만)와 이 스크립트 출력으로만 본다.
재보고: 등록(12주차) 뒤 해당 30경기 또는 정규시즌 끝 중 먼저 — 그때 Paul 이 정한다.

    python scripts/sack_allow_watch.py            # 올해 + 2018~작년 기준선 다시 계산
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfl_pull as N  # noqa: E402

CUT, CUT2, MIN_G, FROM_WK = 0.02, 0.03, 4, 5
REG_WK, TARGET = 12, 30
# 등록 시점 기준선(2026-11-25 실행 · 2018~2025 · 아래 report() 가 다시 계산해 보여 준다)
BASE = "2018~2025 낮은 쪽 499승 292패(승률 63% · 시장 기대 61%) · 스프레드 393-374-24"
_REC = {}


def osr(off, t, wk):
    """그 주 전까지 공격 색 허용률(4경기 미만이면 None). off = {팀: {주: [드롭백, 색]}}."""
    ws = [w for w in (off.get(t) or {}) if w < wk]
    db = sum(off[t][w][0] for w in ws)
    return sum(off[t][w][1] for w in ws) / db if len(ws) >= MIN_G and db else None


def _nv(ml_a, ml_h):
    def imp(m):
        m = N.fnum(m)
        if m is None or m == 0:
            return None
        return (-m) / (-m + 100) if m < 0 else 100 / (m + 100)
    a, h = imp(ml_a), imp(ml_h)
    return h / (a + h) if a and h else None


def rows(season, off, before_week=None, games=None):
    """끝난 정규시즌 경기 → [{week, h, a, gap, low_home, res, mk, ph}] (두 팀 다 허용률이 있는 5주차~ 경기)."""
    out = []
    for g in (games if games is not None else N.rd(os.path.join(N.CACHE, "games.csv"))):
        if g.get("game_type") != "REG" or int(g["season"]) != season or g.get("result") in (None, ""):
            continue
        wk = int(g["week"])
        if wk < FROM_WK or (before_week and wk >= before_week):
            continue
        h, a = g["home_team"], g["away_team"]
        oh, oa = osr(off, h, wk), osr(off, a, wk)
        if oh is None or oa is None or oh == oa:
            continue
        out.append({"season": season, "week": wk, "h": h, "a": a, "gap": abs(oh - oa), "low_home": oh < oa, "res": N.fnum(g["result"]),
                    "mk": N.fnum(g.get("spread_line")), "ph": _nv(g.get("away_moneyline"), g.get("home_moneyline"))})
    return out


def summ(R, cut=CUT, sel=lambda r: True):
    """낮은 쪽 기준 → {w, l, exp(시장 기대 승률 %), aw, al, ap}. 승-패는 무비그 ML 이 있는 경기만(기대와 같은 표본)."""
    w = l = aw = al = ap = 0; ex = 0.0
    for r in R:
        if r["gap"] < cut or not sel(r) or r["res"] is None:
            continue
        lh = r["low_home"]
        if r["res"] != 0 and r["ph"] is not None:
            ok = (r["res"] > 0) == lh; w += ok; l += (not ok); ex += r["ph"] if lh else 1 - r["ph"]
        if r["mk"] is not None:
            cv = r["res"] - r["mk"]
            if cv == 0:
                ap += 1
            else:
                ok = (cv > 0) == lh; aw += ok; al += (not ok)
    return {"w": w, "l": l, "exp": 100 * ex / (w + l) if w + l else None, "aw": aw, "al": al, "ap": ap}


def fmt(s):
    n = s["w"] + s["l"]
    if not n:
        return "0경기"
    return (f"{s['w']}승 {s['l']}패(승률 {100 * s['w'] / n:.0f}% · 시장 기대 {s['exp']:.0f}% · 차 {100 * s['w'] / n - s['exp']:+.1f}%p)"
            + f" · 스프레드 {s['aw']}-{s['al']}" + (f"-{s['ap']}" if s["ap"] else ""))


def season_now(before_week=None):
    """올해 끝난 경기의 낮은 쪽 기록(sack_context 캐시 사용). → (2.0%p+ 요약, 3.0%p+ 요약, 등록 뒤 2.0%p+ 요약)"""
    if before_week not in _REC:
        import sack_context as SK
        R = rows(N.SEASON, SK.state()[0], before_week)
        _REC[before_week] = (summ(R), summ(R, CUT2), summ(R, CUT, lambda r: r["week"] >= REG_WK))
    return _REC[before_week]


def digest_tail(a, h, wk, off):
    """「🧱 색 맥락」 줄 꼬리 — 허용률 차 2.0%p 이상인 경기만(값만 · 방향 근거 아님). 해당 없으면 ''."""
    oa, oh = osr(off, a, wk), osr(off, h, wk)
    if oa is None or oh is None or abs(oa - oh) < CUT:
        return ""
    low = a if oa < oh else h
    try:
        cur = "올해 낮은 쪽 " + fmt(season_now(before_week=wk)[0])
    except Exception as e:
        cur = f"올해 값 계산 실패({type(e).__name__})"
    return (f" · 지켜보는 중(2026-11-25 Paul · 값만 · 방향 근거 아님): 공격 색 허용률 차 2.0%p 이상 — {a} {100 * oa:.1f}% / {h} {100 * oh:.1f}% · 차 {100 * abs(oa - oh):.1f}%p"
            + (" (3.0%p 이상)" if abs(oa - oh) >= CUT2 else "") + f" · 낮은 쪽 {low} · {cur}" + (f" · {BASE}" if BASE else ""))


def game_values(a, h, wk, off=None):
    """보드용 값(2026-11-26 Paul 「보드에도 색 허용률 차 보이게 해줘」) — 그 경기 전 두 팀 공격 색 허용률. 값이 없으면(4경기 미만) None.
    → {a: 원정 허용률 %, h: 홈 허용률 %, gap: 차 %p, low: 낮은 쪽 팀, watch: 2.0%p 이상, big: 3.0%p 이상}"""
    if off is None:
        import sack_context as SK
        off = SK.state()[0]
    oa, oh = osr(off, a, wk), osr(off, h, wk)
    if oa is None or oh is None:
        return None
    gap = abs(oa - oh)
    return {"a": round(100 * oa, 1), "h": round(100 * oh, 1), "gap": round(100 * gap, 1), "low": (a if oa < oh else h) if oa != oh else "",
            "watch": gap >= CUT, "big": gap >= CUT2}


def record_values(before_week=None):
    """보드용 성적(낮은 쪽 기준) — {season: 올해 2.0%p+, season_big: 올해 3.0%p+, post: 등록(12주차) 뒤 2.0%p+, base: 2018~2025 기준선 문구, target: 재보고 경기 수}.
    각 요약 = {w, l, exp(시장 기대 승률 %), aw, al, ap(스프레드 승·패·무)} · 글로는 fmt(요약)."""
    s, b, p = season_now(before_week)
    return {"season": s, "season_big": b, "post": p, "base": BASE, "target": TARGET, "reg_week": REG_WK}


def report():
    import sack_lab2 as L2
    import sack_context as SK
    hist = []
    for season in range(2018, N.SEASON):
        hist += rows(season, L2.load(season)[0])
        print(f"  {season}: 누적 {len(hist)}경기", file=sys.stderr)
    cur = rows(N.SEASON, SK.state()[0])
    n_all = len(hist)
    print(f"공격 색 허용률 차가 큰 경기 지켜보기 — 정의: 그 경기 전 시즌 누적 허용률(4경기+) 차 2.0%p 이상 → 낮은 쪽 · 5주차~")
    print(f"2018~{N.SEASON - 1}: 대상 {n_all}경기 중 2.0%p+ {sum(1 for r in hist if r['gap'] >= CUT)}경기 · 3.0%p+ {sum(1 for r in hist if r['gap'] >= CUT2)}경기")
    print("  2.0%p 이상 낮은 쪽:", fmt(summ(hist)))
    print("  3.0%p 이상 낮은 쪽:", fmt(summ(hist, CUT2)))
    print("  2.0%p 미만(참고 · 낮은 쪽):", fmt(summ([r for r in hist if r["gap"] < CUT], 0)))
    by = {}
    for r in hist:
        by.setdefault(r["season"], []).append(r)
    print("  시즌별 2.0%p+ 낮은 쪽 승-패(시장 기대): " + " · ".join(f"{s} {x['w']}-{x['l']}({x['exp']:.0f}%)" for s, x in ((s, summ(by[s])) for s in sorted(by)) if x["w"] + x["l"]))
    print(f"{N.SEASON}: 대상 {len(cur)}경기")
    print("  2.0%p 이상 낮은 쪽:", fmt(summ(cur)))
    print("  3.0%p 이상 낮은 쪽:", fmt(summ(cur, CUT2)))
    post = summ(cur, CUT, lambda r: r["week"] >= REG_WK)
    print(f"  등록 뒤({REG_WK}주차~) 2.0%p 이상:", fmt(post), f"· 재보고 = {TARGET}경기 또는 정규시즌 끝(지금 {post['w'] + post['l']}경기)")
    for r in cur:
        if r["gap"] >= CUT and r["week"] >= REG_WK - 1:
            low, oth = (r["h"], r["a"]) if r["low_home"] else (r["a"], r["h"])
            print(f"    {r['week']}주차 {r['a']}@{r['h']}: 차 {100 * r['gap']:.1f}%p · 낮은 쪽 {low} · 점수차(홈 기준) {r['res']:+.0f}")


if __name__ == "__main__":
    report()
