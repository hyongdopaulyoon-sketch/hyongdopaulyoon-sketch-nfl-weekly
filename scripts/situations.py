"""상황별 백테스트 — 「정보가 나온 직후 시장이 과/소반응하는가」 (2026-10-01 Paul 질문 → 사전 등록).
  python scripts/situations.py
기준은 돌리기 전에 아래로 고정했다(사후 선택 금지 — 이 파일을 실행 전에 커밋).

데이터: nflverse games.csv(마감 spread_line·total_line·QB 선발 이름·휴식·바람) · injuries_YYYY · snap_counts_YYYY(data/cache/hist).
판정: 스프레드 −110 손익분기 52.4%. 각 항목은 「그 상황 팀에 걸었을 때」 ATS(푸시 제외)를 낸다 — 50% 아래로 크게 벗어나면 반대(페이드)가 신호.
보고: W-L · % · 우연 95% 폭(±1.96·√(.25/n)) · z · 시즌별 52.4% 넘은 시즌 수(같은 방향 일관성) — 12개 안팎을 함께 보므로
       |z|≥2.64(본페로니 0.05/12)만 「강한 신호」, 1.96~2.64 는 「약한 신호 — 다중 비교로 우연 가능」.

① QB(2006~2025 정규시즌, 팀별 시즌 내 시간순)
  - 주전 = 그 시즌 그 팀의 직전 경기들 중 선발 횟수 최다 QB(동률이면 더 최근 선발). 직전 경기가 2경기 미만이면 판정 안 함(시즌 첫 2경기 제외 — 비시즌 교체는 몇 달 전 공개).
  - 백업 k번째 선발 = 선발 QB ≠ 주전 이고 그 QB 의 이번 시즌 직전 선발 수 = k−1 (k = 1, 2, 3).
  - 주전 복귀 = 선발 QB = 주전 이고 직전 경기 선발 ≠ 주전.
  - 결과: 그 팀 ATS · 그 경기 총점 O/U.
② 주전 결장(2013~2025 — snap_counts 2012 파일 비어 있음)
  - 주전 = 그 팀 직전 3경기 중 출전한 경기의 평균 max(공격, 수비) 스냅 비율 ≥ 60%.
  - 결장 = 그 주 부상 보고 report_status ∈ {Out, Doubtful} 이고 이름(정규화)이 주전과 일치. (IR 은 보고에 없어 제외 — 오래된 공개 정보)
  - (a) 주전 결장 ≥3 팀 ATS (b) ≥5 팀 ATS (c) 양 팀 결장 차 ≥3 → 결장 많은 팀 ATS (d) OL(T·G·C·OL) ≥2 (e) CB ≥2 (f) WR ≥2 — 모두 그 팀 ATS.
③ 큰 라인 이동(오픈→마감 2점+) — 무료 오픈 라인 자료 없음(nflverse 는 마감만, 외부 아카이브 403) → 「자료 없음」, line_history.csv 4주차부터 전향 적립.
④ (2006~2025) (h) 목요일 원정 팀(원정 휴식 ≤4일) ATS (i) 실외(outdoors·open) 바람 ≥15mph 경기 언더.
팀 약칭은 연고 이전을 현재로 통일(OAK→LV · SD→LAC · STL→LA · LAR→LA).
"""
import csv, math, os, re, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__)); CACHE = os.path.join(os.path.dirname(HERE), "data", "cache"); HIST = os.path.join(CACHE, "hist")
TEAM = {"OAK": "LV", "SD": "LAC", "STL": "LA", "LAR": "LA"}
BE = 0.524


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def tm(t):
    return TEAM.get(t, t)


def norm(n):
    n = re.sub(r"[.'\-]", "", (n or "").lower())
    return " ".join(w for w in n.split() if w not in ("jr", "sr", "ii", "iii", "iv", "v"))


def rd(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig", newline=""))) if os.path.exists(p) else []


G = []
for g in rd(os.path.join(CACHE, "games.csv")):
    if g["game_type"] != "REG" or not (2006 <= int(g["season"]) <= 2025) or f(g["spread_line"]) is None or f(g["result"]) is None:
        continue
    g["s"], g["wk"] = int(g["season"]), int(g["week"])
    g["a"], g["h"] = tm(g["away_team"]), tm(g["home_team"])
    g["sp"], g["res"], g["tl"], g["tot"] = f(g["spread_line"]), f(g["result"]), f(g["total_line"]), f(g["total"])
    G.append(g)
G.sort(key=lambda g: (g["s"], g["gameday"], g["gametime"] or ""))


def cover(g, team):
    """team 이 커버했나 — True/False, 푸시 None. spread_line = 홈 기대 마진, result = 홈 − 원정."""
    d = g["res"] - g["sp"]
    if d == 0:
        return None
    return (d > 0) if team == g["h"] else (d < 0)


def over(g):
    if g["tl"] is None or g["tot"] is None or g["tot"] == g["tl"]:
        return None
    return g["tot"] > g["tl"]


def summarize(label, items):
    """items = [(season, win_bool)]"""
    xs = [(s, w) for s, w in items if w is not None]
    n = len(xs); w = sum(1 for _, x in xs if x)
    if not n:
        return [label, 0, "—", "—", "—", "—", "—"]
    p = w / n; band = 1.96 * math.sqrt(0.25 / n); z = (p - 0.5) / math.sqrt(0.25 / n)
    by = defaultdict(lambda: [0, 0])
    for s, x in xs:
        by[s][0 if x else 1] += 1
    up = sum(1 for a, b in by.values() if a / (a + b) > BE); down = sum(1 for a, b in by.values() if b / (a + b) > BE)
    sig = "강한 신호" if abs(z) >= 2.64 else "약한 신호(다중 비교 — 우연 가능)" if abs(z) >= 1.96 else "우연 범위"
    return [label, n, f"{w}-{n - w}", f"{p * 100:.1f}%", f"±{band * 100:.1f}", f"{z:+.2f}", f"걸기 {up}/{len(by)} · 페이드 {down}/{len(by)}", sig]


# ── ① QB ──
def qb_items():
    out = defaultdict(list)
    seq = defaultdict(list)   # (season, team) -> [(g, qb)]
    for g in G:
        for side in ("a", "h"):
            qb = g["away_qb_name" if side == "a" else "home_qb_name"]
            if qb:
                seq[(g["s"], g[side])].append((g, qb))
    for (s, t), lst in seq.items():
        starts = defaultdict(int); last = {}
        prev_qb = None
        for i, (g, qb) in enumerate(lst):
            if i >= 2:
                reg = max(starts, key=lambda q: (starts[q], last[q]))
                c, o = cover(g, t), over(g)
                if qb != reg and starts[qb] < 3:
                    k = starts[qb] + 1
                    out[f"백업 QB {k}번째 선발 — 그 팀 ATS"].append((s, c)); out[f"백업 QB {k}번째 선발 — 오버"].append((s, o))
                elif qb == reg and prev_qb != reg:
                    out["주전 QB 복귀 첫 경기 — 그 팀 ATS"].append((s, c)); out["주전 QB 복귀 첫 경기 — 오버"].append((s, o))
            starts[qb] += 1; last[qb] = i; prev_qb = qb
    return out


# ── ② 주전 결장 ──
def absence_items():
    out = defaultdict(list)
    for s in range(2013, 2026):
        snaps = rd(os.path.join(HIST, f"snap_counts_{s}.csv")); inj = rd(os.path.join(HIST, f"injuries_{s}.csv"))
        if not snaps or not inj:
            continue
        team_weeks = defaultdict(set); pct = defaultdict(dict)   # (team) -> {week}; (team, name) -> {week: pct}
        for r in snaps:
            if r.get("game_type", "REG") != "REG":
                continue
            t = tm(r["team"]); w = int(r["week"]); team_weeks[t].add(w)
            v = max(f(r.get("offense_pct")) or 0, f(r.get("defense_pct")) or 0)
            if v > 1.5:     # 일부 해는 0~100 표기
                v /= 100
            if v > 0:
                pct[(t, norm(r["player"]))][w] = v
        outs = defaultdict(list)    # (team, week) -> [(name, pos)]
        for r in inj:
            if r.get("game_type", "REG") == "REG" and r.get("report_status") in ("Out", "Doubtful"):
                outs[(tm(r["team"]), int(r["week"]))].append((norm(r["full_name"]), r.get("position", "")))

        def starters_out(t, w):
            prev = sorted(x for x in team_weeks[t] if x < w)[-3:]
            if len(prev) < 3:
                return None
            cnt = {"all": 0, "OL": 0, "CB": 0, "WR": 0}
            for name, pos in outs.get((t, w), []):
                vals = [pct.get((t, name), {}).get(x) for x in prev]
                vals = [v for v in vals if v]
                if vals and sum(vals) / len(vals) >= 0.60:
                    cnt["all"] += 1
                    if pos in ("T", "G", "C", "OL", "OT", "OG"):
                        cnt["OL"] += 1
                    elif pos == "CB":
                        cnt["CB"] += 1
                    elif pos == "WR":
                        cnt["WR"] += 1
            return cnt
        for g in G:
            if g["s"] != s:
                continue
            ca, ch = starters_out(g["a"], g["wk"]), starters_out(g["h"], g["wk"])
            for t, c, o in ((g["a"], ca, ch), (g["h"], ch, ca)):
                if c is None:
                    continue
                cv = cover(g, t)
                if c["all"] >= 3: out["(a) 주전 결장 3명+ 팀 ATS"].append((s, cv))
                if c["all"] >= 5: out["(b) 주전 결장 5명+ 팀 ATS"].append((s, cv))
                if o is not None and c["all"] - o["all"] >= 3: out["(c) 결장 차 3명+ — 많은 팀 ATS"].append((s, cv))
                if c["OL"] >= 2: out["(d) 주전 OL 2명+ 결장 팀 ATS"].append((s, cv))
                if c["CB"] >= 2: out["(e) 주전 CB 2명+ 결장 팀 ATS"].append((s, cv))
                if c["WR"] >= 2: out["(f) 주전 WR 2명+ 결장 팀 ATS"].append((s, cv))
    return out


# ── ④ ──
def misc_items():
    out = defaultdict(list)
    for g in G:
        ar = f(g["away_rest"])
        if g["weekday"] == "Thursday" and ar is not None and ar <= 4:
            out["(h) 목요일 원정 팀(휴식 ≤4) ATS"].append((g["s"], cover(g, g["a"])))
        if g["roof"] in ("outdoors", "open") and (f(g["wind"]) or 0) >= 15:
            o = over(g)
            out["(i) 실외 바람 15mph+ — 언더"].append((g["s"], None if o is None else not o))
    return out


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(f"■ 상황별 백테스트 — 경기 {len(G)}(2006~2025 정규시즌) · 손익분기 52.4% · 강한 신호 |z|≥2.64")
    hdr = ["상황", "n", "W-L", "적중", "우연 95%폭", "z", "시즌 일관성(52.4%↑)", "판정"]
    for title, items in (("① QB", qb_items()), ("② 주전 결장(2013~)", absence_items()), ("④ 휴식·바람", misc_items())):
        print(f"\n{title}")
        print(" | ".join(hdr))
        for k in sorted(items):
            print(" | ".join(str(x) for x in summarize(k, items[k])))
    print("\n③ 큰 라인 이동: 자료 없음(무료 오픈 라인 없음) — line_history.csv 전향 적립")


if __name__ == "__main__":
    main()
