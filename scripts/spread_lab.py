"""spread_lab.py — 「스프레드를 맞히는 정의」 검정(2026-11-15 Paul 「스프레드픽도 내자 · nfl도 스프레드 맞추는 방향으로」 → 계획 3번 「오늘 바로 시작」).
  python scripts/spread_lab.py            # 2018~2025 정규시즌 3주차~ · data/spread_lab_<오늘>.md
문턱(실행 전 고정 — Paul 승인 계획): 과거 2개 이상 시즌에서 같은 방향 & 전체 53% 이상인 정의만 스프레드 픽 정의 후보. 보고는 승-패 먼저,
시즌별 50% 넘긴 시즌 수·z(50% 대비)도 같이(여러 후보를 한꺼번에 보므로 |z| 2.6 미만은 우연 가능).
후보(실행 전 고정): D1 모델 마진 쪽(현행) · D2 모델 반대쪽(차 2+/3.5+/5+) · D3 홈 언더독 +7 이상 → 홈(A7) · D4 원정 휴식 우위 3일+ → 원정 ·
D5 원정 언더독 → 원정 · D6 언더독 전부 · D7 키 넘버 3·7 넘긴 이동 반대쪽(A6 · 개장 라인 있는 2024~25) · D8 페이버릿 전부(= 예측 승자 커버).
"""
import datetime as dt
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfl_pull as N  # noqa: E402
import backtest as B  # noqa: E402

SEASONS = list(range(2018, 2026))
MIN_WEEK = 3


def pbp_path(season):
    for p in (os.path.join(N.CACHE, "hist", f"play_by_play_{season}.csv.gz"), os.path.join(N.CACHE, f"play_by_play_{season}.csv.gz")):
        if os.path.exists(p):
            return p
    return ""


def model_rows():
    games_all = N.rd(os.path.join(N.CACHE, "games.csv"))
    rows = []
    for season in SEASONS:
        pbp, pp = pbp_path(season), pbp_path(season - 1)
        if not pbp:
            print(f"  {season} pbp 없음 — 건너뜀"); continue
        cur = N._team_week_epa(pbp, season); db = B.qb_dropbacks(pbp)
        prev = N._team_week_epa(pp, season - 1) if pp else {}
        teams = sorted({t for t, _ in cur} | {t for t, _ in prev})
        gs = [g for g in games_all if g["season"] == str(season) and g["game_type"] == "REG" and g.get("result") and g.get("spread_line")]
        for wk in sorted({int(g["week"]) for g in gs}):
            rt = B.ratings_asof(cur, prev, wk, teams) if wk >= MIN_WEEK else {}
            for g in gs:
                if int(g["week"]) != wk:
                    continue
                h, aw = g["home_team"], g["away_team"]
                margin = None
                if wk >= MIN_WEEK and h in rt and aw in rt:
                    oh, dh, oa, da = rt[h]["off"], rt[h]["def"], rt[aw]["off"], rt[aw]["def"]
                    hfa = 0.0 if str(g.get("location", "")).lower() == "neutral" else N.HFA
                    mh, ma = B.main_qb_before(db, h, wk), B.main_qb_before(db, aw, wk)
                    qh = -N.QB_ADJ if (g.get("home_qb_name") and mh and not N._same_person(mh, g["home_qb_name"])) else 0.0
                    qa = -N.QB_ADJ if (g.get("away_qb_name") and ma and not N._same_person(ma, g["away_qb_name"])) else 0.0
                    margin = N.PLAYS * ((oh + da) - (oa + dh)) + hfa + qh - qa
                rows.append(dict(season=season, week=wk, margin=margin, res=N.fnum(g["result"]), mk=N.fnum(g["spread_line"]),
                                 ar=N.fnum(g.get("away_rest")) or 7, hr=N.fnum(g.get("home_rest")) or 7, gid=g["game_id"]))
        print(f"  {season}: 누적 {len(rows)}경기")
    return rows


def tally(rows, side):
    """side(r) → +1 홈 쪽 / −1 원정 쪽 / 0 해당 없음. 돌려주는 값 (w, l, p, {season: [w, l]})."""
    w = l = p = 0; by = defaultdict(lambda: [0, 0])
    for r in rows:
        s = side(r)
        if not s:
            continue
        cov = r["res"] - r["mk"]          # + = 홈 커버(nflverse spread_line = 홈 기대 마진)
        if cov == 0:
            p += 1; continue
        ok = (cov > 0) == (s > 0)
        w += ok; l += (not ok); by[r["season"]][0 if ok else 1] += 1
    return w, l, p, by


def line(lab, rows, side):
    w, l, p, by = tally(rows, side)
    n = w + l
    if not n:
        return f"| {lab} | 0 | — | — | — | — | — |", None
    pct = 100 * w / n; z = (w - n / 2) / math.sqrt(n / 4)
    over = sum(1 for s, (a, b) in by.items() if a + b and a / (a + b) > 0.5); tot = sum(1 for s, (a, b) in by.items() if a + b)
    seas = " · ".join(f"{str(s)[2:]}:{a}-{b}" for s, (a, b) in sorted(by.items()))
    ok = pct >= 53 and over >= 2
    return f"| {lab} | {n} | {w}-{l}" + (f"-{p}" if p else "") + f" | {pct:.1f}% | {z:+.2f} | {over}/{tot} | {seas} |", dict(lab=lab, n=n, w=w, l=l, pct=pct, z=z, over=over, tot=tot, ok=ok)


def a6_rows():
    """개장·마감 라인(ESPN · 2024~25) — 키 넘버 3·7 넘긴 이동 반대쪽. 홈 라인 기준(− = 홈 페이버릿)."""
    out = []
    for r in N.rd(os.path.join(N.CACHE, "odds_openclose.csv")):
        o, c = N.fnum(r.get("open_spread_home")), N.fnum(r.get("close_spread_home"))
        hs, as_ = N.fnum(r.get("home_score")), N.fnum(r.get("away_score"))
        if o is None or c is None or hs is None or as_ is None or o == c:
            continue
        if not any((abs(o) < k <= abs(c)) or (abs(c) < k <= abs(o)) for k in (3.0, 7.0)):
            continue
        # 이동 방향: c < o 면 홈 쪽으로 이동(홈이 더 페이버릿) → 반대쪽 = 원정
        out.append(dict(season=int(r["season"]), res=hs - as_, mk=-c, fade=(-1 if c < o else 1)))
    return out


def main():
    rows = model_rows()
    md = [r for r in rows if r["margin"] is not None]
    L = [f"# NFL 스프레드 정의 검정 — {dt.date.today()} · 2018~2025 정규시즌 · 마감 스프레드(nflverse) · 모델 후보는 {MIN_WEEK}주차~", "",
         "문턱(실행 전 고정): 2개 이상 시즌에서 같은 방향(50% 초과) & 전체 53% 이상. z = 50% 대비(|z| 2.6 미만은 여러 후보를 한꺼번에 본 우연 가능). 손익분기 52.4%.", "",
         "| 후보 | 경기 | 승-패(-무) | 적중 | z | 50% 넘긴 시즌 | 시즌별 |", "|---|---|---|---|---|---|---|"]
    res = []

    def add(lab, rs, side):
        ln, d = line(lab, rs, side); L.append(ln)
        if d:
            res.append(d)
    gap = lambda r: r["margin"] - r["mk"]
    add("D1 모델 마진 쪽(현행 · 전 경기)", md, lambda r: (1 if gap(r) > 0 else -1) if gap(r) else 0)
    for th in (1, 2, 3.5, 5):
        add(f"D1 모델 쪽 · 차 {th}+", md, lambda r, th=th: (1 if gap(r) > 0 else -1) if abs(gap(r)) >= th else 0)
    for th in (2, 3.5, 5):
        add(f"D2 모델 반대쪽 · 차 {th}+", md, lambda r, th=th: (-1 if gap(r) > 0 else 1) if abs(gap(r)) >= th else 0)
    add("D3 홈 언더독 +7 이상 → 홈(A7)", rows, lambda r: 1 if r["mk"] <= -7 else 0)
    add("D4 원정 휴식 우위 3일+ → 원정", rows, lambda r: -1 if r["ar"] - r["hr"] >= 3 else 0)
    add("D5 원정 언더독 → 원정", rows, lambda r: -1 if r["mk"] > 0 else 0)
    add("D6 언더독 전부", rows, lambda r: (-1 if r["mk"] > 0 else 1) if r["mk"] else 0)
    add("D8 페이버릿 전부(= 예측 승자 커버)", rows, lambda r: (1 if r["mk"] > 0 else -1) if r["mk"] else 0)
    add("D7 키 넘버 3·7 넘긴 이동 반대쪽(A6 · 2024~25)", a6_rows(), lambda r: r["fade"])
    # 겹침: 모델 반대쪽 3.5+ 가 언더독·홈 언더독과 얼마나 같은 경기인가
    f35 = [r for r in md if abs(gap(r)) >= 3.5]
    dog = sum(1 for r in f35 if r["mk"] and ((-1 if gap(r) > 0 else 1) == (-1 if r["mk"] > 0 else 1)))
    L += ["", f"겹침: 「모델 반대쪽 · 차 3.5+」 {len(f35)}경기 중 언더독 쪽 {dog}경기({100 * dog / max(1, len(f35)):.0f}%)", "",
          "## 문턱 통과(2개+ 시즌 50% 초과 & 전체 53%+)", ""]
    ok = [d for d in res if d["ok"]]
    L += [f"- {d['lab']}: {d['w']}-{d['l']} {d['pct']:.1f}% · z {d['z']:+.2f} · 시즌 {d['over']}/{d['tot']}" for d in ok] or ["- 없음"]
    out = os.path.join(N.DATA, f"spread_lab_{dt.date.today()}.md")
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L)); print(f"\nwrote {out}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
