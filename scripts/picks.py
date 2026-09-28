"""픽로그(data/picks.csv) — suggest(모델 후보·참고 적재) · place(실제 베팅 표시) · grade(채점) · stats(성적).

  python picks.py suggest --week 4          model.csv 의 후보·참고를 status=suggested 로 적재(같은 주 재실행 시 갱신, placed 는 보존)
  python picks.py place --week 4 --id 2026_04_PIT_CLE:spread [--line -3 --odds -110]   실제 베팅 → status=placed(라인·배당 갱신 가능)
  python picks.py place --week 4 --all-candidates                                       관찰 등급 전부 placed
  python picks.py grade --week 4            results.csv(nfl_pull --phase results) 로 W/L/P 채점
  python picks.py stats                     집행(placed) 성적 — 주별·시장별·등급별·엣지 구간별 · 손익분기 52.4%

한 행 = 한 시장(스프레드/총점). id = game_id:market. 성적은 placed 만 센다(N7). suggested 는 「모델이 그렇게 말했다」 기록.
"""
import argparse
import csv
import os
import sys
from collections import defaultdict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); DATA = os.path.join(ROOT, "data")
PICKS = os.path.join(DATA, "picks.csv")
HDR = ["id", "season", "week", "game", "market", "side", "line", "odds", "model_value", "edge", "grade", "p_win", "status",
       "placed_at", "result", "score", "units", "note"]
SEASON = 2026


def rd(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig", newline=""))) if os.path.exists(p) else []


def save(rows):
    os.makedirs(DATA, exist_ok=True)
    with open(PICKS + ".tmp", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=HDR); w.writeheader(); w.writerows(rows)
    os.replace(PICKS + ".tmp", PICKS)


def fnum(x):
    try:
        return float(str(x).strip())
    except (TypeError, ValueError):
        return None


def suggest(week):
    wd = os.path.join(DATA, f"{SEASON}-w{week:02d}")
    model = rd(os.path.join(wd, "model.csv"))
    rows = rd(PICKS)
    keep = {r["id"]: r for r in rows}
    n_new = n_upd = 0
    for m in model:
        for market, side, line, val, edge, grade, p in (
                ("spread", m["spread_side"], m["mkt_spread_home"], m["model_margin_home"], m["edge_spread"], m["spread_grade"], m["p_cover"]),
                ("total", m["total_side"], m["mkt_total"], m["model_total"], m["edge_total"], m["total_grade"], m["p_total"])):
            if not grade.startswith(("관찰", "참고")):
                continue
            pid = f'{m["game_id"]}:{market}'
            old = keep.get(pid)
            if old and old["status"] == "placed":
                continue                                   # 실제 베팅한 행은 모델이 바뀌어도 건드리지 않는다
            row = {"id": pid, "season": SEASON, "week": week, "game": f'{m["away"]}@{m["home"]}', "market": market, "side": side,
                   "line": line, "odds": "-110", "model_value": val, "edge": edge, "grade": grade, "p_win": p, "status": "suggested",
                   "placed_at": "", "result": "", "score": "", "units": "", "note": ""}
            if old:
                old.update(row); n_upd += 1
            else:
                keep[pid] = row; n_new += 1
    save(list(keep.values()))
    print(f"suggest week {week}: 신규 {n_new} · 갱신 {n_upd} · 전체 {len(keep)}행 → {os.path.relpath(PICKS, ROOT)}")


def lean(week, pid, side, line, odds="-110", note=""):
    """설명문 판단(관심) 기록 — 사람(수정 세션) 의견을 페이퍼로 남겨 모델·사람·실베팅을 따로 잰다. id = game_id:spread|total"""
    rows = rd(PICKS); keep = {r["id"]: r for r in rows}
    game_id, market = pid.rsplit(":", 1)
    game = next((r["game"] for r in rows if r["id"].startswith(game_id + ":")), game_id.split("_", 2)[-1].replace("_", "@"))
    old = keep.get(pid)
    row = {"id": pid, "season": SEASON, "week": week, "game": game, "market": market, "side": side, "line": line, "odds": odds,
           "model_value": old["model_value"] if old else "", "edge": old["edge"] if old else "", "grade": "관심(설명문)", "p_win": old["p_win"] if old else "",
           "status": old["status"] if old and old["status"] == "placed" else "suggested", "placed_at": old["placed_at"] if old else "",
           "result": "", "score": "", "units": "", "note": note}
    keep[pid] = row; save(list(keep.values())); print(f"lean 기록: {pid} {side} ({row['status']})")


def place(week, pid=None, all_candidates=False, line=None, odds=None, note="", side=None):
    rows = rd(PICKS); n = 0
    if pid and side:
        # 실베팅 쪽이 모델 페이퍼 행과 다르면(예: 모델 Over, Paul Under) 페이퍼 행은 두고 ":P" 행을 따로 만든다(2026-09-28 LA@DEN 사고)
        base = next((r for r in rows if r["id"] == pid), None)
        if base is None or base["side"].split()[0] != side.split()[0] or base["status"] == "placed" and base["side"] != side:
            game = base["game"] if base else next((r["game"] for r in rows if r["id"].startswith(pid.rsplit(":", 1)[0] + ":")), pid.rsplit(":", 1)[0].split("_", 2)[-1].replace("_", "@"))
            row = {k: "" for k in HDR}
            row.update({"id": pid + ":P", "season": SEASON, "week": week, "game": game, "market": pid.rsplit(":", 1)[1], "side": side,
                        "line": line or "", "odds": odds or "-110", "grade": "실베팅", "status": "placed",
                        "placed_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "note": note})
            rows = [r for r in rows if r["id"] != row["id"]] + [row]
            save(rows); print(f"placed(별도 행) {row['id']} {side}"); return
    for r in rows:
        if int(r["week"]) != week:
            continue
        if (pid and r["id"] == pid) or (all_candidates and r["grade"].startswith("관찰")):
            r["status"] = "placed"; r["placed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            if line is not None: r["line"] = line
            if odds is not None: r["odds"] = odds
            if note: r["note"] = note
            n += 1
    save(rows); print(f"placed {n}행")


def _grade_one(r, res):
    """스프레드: side 'CLE +3' → CLE 점수 + 3 vs 상대 · 총점: 'Over 41.5'. 반환 (W/L/P, 점수 표기)."""
    a, h = r["game"].split("@")
    sa, sh = fnum(res.get("away_score")), fnum(res.get("home_score"))
    if sa is None or sh is None:
        return None, ""
    score = f"{a} {sa:g}-{sh:g} {h}"
    if r["market"] == "spread":
        team, pts = r["side"].split()[0], fnum(r["side"].split()[1])
        mine, theirs = (sa, sh) if team == a else (sh, sa)
        d = mine + pts - theirs
    else:
        d = (sa + sh) - fnum(r["side"].split()[1]); d = d if r["side"].startswith("Over") else -d
    return ("P" if d == 0 else "W" if d > 0 else "L"), score


def grade(week):
    wd = os.path.join(DATA, f"{SEASON}-w{week:02d}")
    res = {f'{r["away"]}@{r["home"]}': r for r in rd(os.path.join(wd, "results.csv")) if r["status"] == "STATUS_FINAL"}
    rows = rd(PICKS); n = 0
    for r in rows:
        if int(r["week"]) != week or r["result"]:
            continue
        x = res.get(r["game"])
        if not x:
            continue
        wl, score = _grade_one(r, x)
        if wl is None:
            continue
        o = fnum(r["odds"]) or -110
        r["result"], r["score"] = wl, score
        r["units"] = "0" if wl == "P" else ("-1" if wl == "L" else f"{(100 / abs(o) if o < 0 else o / 100):.3f}")
        n += 1
    save(rows); print(f"grade week {week}: {n}행 채점")


def stats():
    rows = [r for r in rd(PICKS) if r["result"] in ("W", "L", "P")]
    def rec(xs):
        w = sum(1 for x in xs if x["result"] == "W"); l = sum(1 for x in xs if x["result"] == "L"); p = len(xs) - w - l
        u = sum(fnum(x["units"]) or 0 for x in xs)
        pct = f"{100 * w / (w + l):.1f}%" if w + l else "—"
        return f"{w}-{l}" + (f"-{p}" if p else "") + f" {pct} {u:+.2f}u"
    placed = [r for r in rows if r["status"] == "placed"]; sug = [r for r in rows if r["status"] != "placed"]
    print(f"📊 NFL {SEASON} 픽 성적 — 손익분기 52.4%(−110)")
    print(f"■ 집행(placed) {len(placed)}픽 {rec(placed)} · 모델 제안(미집행) {len(sug)}픽 {rec(sug)}")
    for lab, key in (("시장", "market"), ("등급", "grade"), ("주차", "week")):
        by = defaultdict(list)
        for r in placed: by[r[key]].append(r)
        print(f"  {lab}: " + " · ".join(f"{k} {rec(v)}" for k, v in sorted(by.items(), key=lambda kv: str(kv[0]))))
    by = defaultdict(list)
    for r in rows:
        e = abs(fnum(r["edge"]) or 0); by["≥5" if e >= 5 else "3.5~5" if e >= 3.5 else "2~3.5" if e >= 2 else "<2"].append(r)
    print("  엣지 구간(제안+집행 전부 — 모델 검증용): " + " · ".join(f"{k} {rec(v)}" for k, v in sorted(by.items())))


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("suggest"); s.add_argument("--week", type=int, required=True)
    p = sub.add_parser("place"); p.add_argument("--week", type=int, required=True); p.add_argument("--id"); p.add_argument("--all-candidates", action="store_true")
    p.add_argument("--line"); p.add_argument("--odds"); p.add_argument("--note", default=""); p.add_argument("--side", help="모델 행과 다른 쪽이면 별도 :P 행")
    l = sub.add_parser("lean"); l.add_argument("--week", type=int, required=True); l.add_argument("--id", required=True); l.add_argument("--side", required=True)
    l.add_argument("--line", required=True); l.add_argument("--odds", default="-110"); l.add_argument("--note", default="")
    g = sub.add_parser("grade"); g.add_argument("--week", type=int, required=True)
    sub.add_parser("stats")
    a = ap.parse_args()
    if a.cmd == "suggest": suggest(a.week)
    elif a.cmd == "place": place(a.week, a.id, a.all_candidates, a.line, a.odds, a.note, a.side)
    elif a.cmd == "lean": lean(a.week, a.id, a.side, a.line, a.odds, a.note)
    elif a.cmd == "grade": grade(a.week)
    else: stats()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
