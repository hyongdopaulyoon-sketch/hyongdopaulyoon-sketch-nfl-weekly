"""시장 라인 기준 「각도」 백테스트 — nflverse games.csv 마감 스프레드·총점·휴식·디비전만으로(2015~2025 정규시즌).
각도마다 ATS(또는 O/U) 승률과 시즌별 일관성(손익분기 52.4% 넘긴 시즌 수)을 찍는다. 사후 선택 위험을 줄이려고 각도는 아래 목록으로 고정한다."""
import os, sys, csv
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__)); CACHE = os.path.join(os.path.dirname(HERE), "data", "cache")
def f(x):
    try: return float(x)
    except (TypeError, ValueError): return None
G = [g for g in csv.DictReader(open(os.path.join(CACHE, "games.csv"), encoding="utf-8-sig"))
     if g["game_type"] == "REG" and 2015 <= int(g["season"]) <= 2025 and f(g["spread_line"]) is not None and f(g["result"]) is not None]
for g in G:
    g["s"] = int(g["season"]); g["sp"] = f(g["spread_line"]); g["res"] = f(g["result"]); g["tl"] = f(g["total_line"]); g["tot"] = f(g["total"])
    g["ar"] = f(g["away_rest"]) or 7; g["hr"] = f(g["home_rest"]) or 7
    g["home_cover"] = (g["res"] - g["sp"]) > 0; g["push"] = (g["res"] - g["sp"]) == 0
    g["over"] = (g["tot"] - g["tl"]) > 0 if (g["tl"] is not None and g["tot"] is not None) else None; g["tpush"] = (g["tot"] == g["tl"]) if g["tl"] is not None else True
def ats(rows, side):   # side(g) -> True 면 홈 커버가 승
    w = sum(1 for g in rows if not g["push"] and g["home_cover"] == side(g)); l = sum(1 for g in rows if not g["push"] and g["home_cover"] != side(g))
    by = defaultdict(lambda: [0, 0])
    for g in rows:
        if g["push"]: continue
        by[g["s"]][0 if g["home_cover"] == side(g) else 1] += 1
    ok = sum(1 for s, (a, b) in by.items() if a + b and a / (a + b) > 0.524)
    return f"{w}-{l} {100 * w / (w + l):.1f}% · 시즌 {ok}/{len(by)} 손익분기 위" if w + l else "0"
def ou(rows, over):
    xs = [g for g in rows if g["over"] is not None and not g["tpush"]]
    w = sum(1 for g in xs if g["over"] == over); l = len(xs) - w
    by = defaultdict(lambda: [0, 0])
    for g in xs: by[g["s"]][0 if g["over"] == over else 1] += 1
    ok = sum(1 for s, (a, b) in by.items() if a + b and a / (a + b) > 0.524)
    return f"{w}-{l} {100 * w / (w + l):.1f}% · 시즌 {ok}/{len(by)} 손익분기 위" if w + l else "0"
print(f"■ 표본 {len(G)}경기 2015~2025 정규시즌 · 손익분기 52.4%")
A = [
 ("홈 언더독(스프레드 +) — 홈 커버", lambda g: g["sp"] < 0, lambda g: True),
 ("원정 언더독 — 원정 커버", lambda g: g["sp"] > 0, lambda g: False),
 ("언더독 전부 — 독 커버", lambda g: True, lambda g: g["sp"] < 0),
 ("큰 페이버릿 −10 이상 — 독 커버", lambda g: abs(g["sp"]) >= 10, lambda g: g["sp"] < 0),
 ("페이버릿 −7~−9.5 — 독 커버", lambda g: 7 <= abs(g["sp"]) < 10, lambda g: g["sp"] < 0),
 ("디비전 경기 언더독 — 독 커버", lambda g: g["div_game"] == "1", lambda g: g["sp"] < 0),
 ("휴식 우위 3일+ 팀 커버(홈)", lambda g: g["hr"] - g["ar"] >= 3, lambda g: True),
 ("휴식 우위 3일+ 팀 커버(원정)", lambda g: g["ar"] - g["hr"] >= 3, lambda g: False),
 ("목요일 경기 홈 커버", lambda g: g["weekday"] == "Thursday", lambda g: True),
 ("바이 뒤 팀(휴식 13+) 커버(홈)", lambda g: g["hr"] >= 13, lambda g: True),
 ("바이 뒤 팀(휴식 13+) 커버(원정)", lambda g: g["ar"] >= 13, lambda g: False),
 ("지붕 실외 · 12월 이후 홈 커버", lambda g: g["roof"] in ("outdoors", "open") and g["gameday"][5:7] in ("12", "01"), lambda g: True),
]
for name, cond, side in A:
    rows = [g for g in G if cond(g)]
    print(f"  {name:32s} {len(rows):4d}경기 · {ats(rows, side)}")
print("■ 총점")
B = [
 ("전체 언더", lambda g: True, False),
 ("총점 라인 50+ 언더", lambda g: g["tl"] is not None and g["tl"] >= 50, False),
 ("총점 라인 ≤40 오버", lambda g: g["tl"] is not None and g["tl"] <= 40, True),
 ("실외 · 12월~1월 언더", lambda g: g["roof"] in ("outdoors", "open") and g["gameday"][5:7] in ("12", "01"), False),
 ("디비전 경기 언더", lambda g: g["div_game"] == "1", False),
 ("목요일 언더", lambda g: g["weekday"] == "Thursday", False),
 ("돔 오버", lambda g: g["roof"] in ("dome", "closed"), True),
]
for name, cond, over in B:
    rows = [g for g in G if cond(g)]
    print(f"  {name:32s} {len(rows):4d}경기 · {ou(rows, over)}")
