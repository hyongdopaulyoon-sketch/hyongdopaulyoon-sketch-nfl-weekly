"""spread_lab_ext.py — 스프레드 실마리 확대 검정(2026-11-15 Paul 「nfl 더 정교하게 비교하고 개선 · 선수 위주로」 → 계획 3번 「이대로 가자」).
  python scripts/spread_lab_ext.py        # data/spread_lab_ext_<오늘>.md
대상(실행 전 고정): spread_lab 2차에서 표본이 작았던 「생애 첫 선발 QB 의 팀 쪽」(2018~25 46-32 59.0% n78)을 2006~2025 20시즌으로 넓힌다.
정의(2차와 같게): 그 경기 전 1999~ 정규시즌 선발 기록이 없는 QB & 그 팀의 같은 시즌 직전 경기 선발과 다름(시즌 개막전 제외). 한 경기에 두 팀 다 해당이면 제외.
문턱(같음): 2개 이상 시즌 50% 초과 & 전체 53% 이상 · z 는 50% 대비. 쪼갠 줄(홈/원정 · 라인 크기 · 2번째 선발)은 참고(판정 아님).
"""
import datetime as dt
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfl_pull as N  # noqa: E402


def load():
    gs = sorted((g for g in N.rd(os.path.join(N.CACHE, "games.csv")) if g["game_type"] == "REG"), key=lambda g: (int(g["season"]), int(g["week"]), g["game_id"]))
    seen = defaultdict(int); lastq = {}; rows = []
    for g in gs:
        ft = {}
        for sd, t, q in (("h", g["home_team"], g.get("home_qb_name") or ""), ("a", g["away_team"], g.get("away_qb_name") or "")):
            k = N._norm_name(q)
            prev = lastq.get((g["season"], t))
            ft[sd] = {"n": seen[k] if k else None, "chg": bool(k) and prev not in (None, k)}
            if k:
                lastq[(g["season"], t)] = k
        for q in (g.get("home_qb_name"), g.get("away_qb_name")):
            if N._norm_name(q):
                seen[N._norm_name(q)] += 1
        if N.fnum(g.get("result")) is None or N.fnum(g.get("spread_line")) is None:
            continue
        rows.append(dict(season=int(g["season"]), res=N.fnum(g["result"]), mk=N.fnum(g["spread_line"]), h=ft["h"], a=ft["a"]))
    return rows


def tally(rows, side):
    w = l = p = 0; by = defaultdict(lambda: [0, 0])
    for r in rows:
        s = side(r)
        if not s:
            continue
        cov = r["res"] - r["mk"]
        if cov == 0:
            p += 1; continue
        ok = (cov > 0) == (s > 0)
        w += ok; l += (not ok); by[r["season"]][0 if ok else 1] += 1
    return w, l, p, by


def main():
    rows = [r for r in load() if 2006 <= r["season"] <= 2025]
    L = [f"# NFL 스프레드 실마리 확대 — {dt.date.today()} · 2006~2025 정규시즌 {len(rows)}경기 · 마감 스프레드(nflverse)", "",
         "「그 팀 쪽」 승-패. 문턱: 2개+ 시즌 50% 초과 & 전체 53%+. 첫 줄만 판정, 나머지는 참고.", "",
         "| 조건 | 경기 | 승-패(-무) | 적중 | z | 50% 넘긴 시즌 | 2006~17 | 2018~25 |", "|---|---|---|---|---|---|---|---|"]

    def one(cond):
        def side(r):
            a, h = bool(cond(r["a"], r, "a")), bool(cond(r["h"], r, "h"))
            return 0 if a == h else (1 if h else -1)
        return side

    def add(lab, side):
        w, l, p, by = tally(rows, side); n = w + l
        if not n:
            L.append(f"| {lab} | 0 | — | — | — | — | — | — |"); return None

        def part(lo, hi):
            a = sum(v[0] for s, v in by.items() if lo <= s <= hi); b = sum(v[1] for s, v in by.items() if lo <= s <= hi)
            return f"{a}-{b} {100 * a / (a + b):.1f}%" if a + b else "—"
        over = sum(1 for a, b in by.values() if a + b and a / (a + b) > 0.5); tot = sum(1 for a, b in by.values() if a + b)
        L.append(f"| {lab} | {n} | {w}-{l}" + (f"-{p}" if p else "") + f" | {100 * w / n:.1f}% | {(w - n / 2) / math.sqrt(n / 4):+.2f} | {over}/{tot} | {part(2006, 2017)} | {part(2018, 2025)} |")
        return 100 * w / n, over
    first = lambda ft, r, s: ft["n"] == 0 and ft["chg"]
    main_res = add("생애 첫 선발 QB 의 팀(시즌 중 교체)", one(first))
    add("  · 그 팀이 홈", one(lambda ft, r, s: first(ft, r, s) and s == "h"))
    add("  · 그 팀이 원정", one(lambda ft, r, s: first(ft, r, s) and s == "a"))
    add("  · 그 팀이 7점+ 언더독", one(lambda ft, r, s: first(ft, r, s) and ((r["mk"] >= 7) if s == "a" else (r["mk"] <= -7))))
    add("  · 그 팀이 3~6.5점 언더독", one(lambda ft, r, s: first(ft, r, s) and ((3 <= r["mk"] < 7) if s == "a" else (-7 < r["mk"] <= -3))))
    add("  · 그 팀이 3점 미만 언더독·페이버릿", one(lambda ft, r, s: first(ft, r, s) and ((r["mk"] < 3) if s == "a" else (r["mk"] > -3))))
    add("생애 2번째 선발 QB 의 팀", one(lambda ft, r, s: ft["n"] == 1))
    add("생애 3번째 선발 QB 의 팀", one(lambda ft, r, s: ft["n"] == 2))
    add("시즌 중 QB 교체 팀(첫 선발 아님 — 경력 있는 백업)", one(lambda ft, r, s: ft["chg"] and (ft["n"] or 0) >= 3))
    ok = bool(main_res and main_res[0] >= 53 and main_res[1] >= 2)
    L += ["", f"판정: 생애 첫 선발 QB 의 팀 쪽 — {'문턱 통과' if ok else '문턱 미달'}"]
    out = os.path.join(N.DATA, f"spread_lab_ext_{dt.date.today()}.md")
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L)); print(f"\nwrote {out}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
