"""발행문 검사 + 판단 기록 (2026-09-29 발행 세션 도입).
  python check_nfl.py --week 4 --file 발행문.md [--record]
검사: ① 경기 머리(🏈 AWAY@HOME) 커버리지 ② 시장 줄 스프레드·총점이 model.csv 와 같은가 ③ 판단 줄 형식·관심 ≤3·한 경기 한 시장
④ 뉴스 확인 줄 존재 ⑤ 금지 낱말(캐시아웃·헤지 권유). --record 면 관심·소액 관심을 picks.csv 에 「관심(발행)」 페이퍼로 적는다."""
import argparse
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); DATA = os.path.join(ROOT, "data")
SEASON = 2026
sys.path.insert(0, HERE)


def rd(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig", newline=""))) if os.path.exists(p) else []


def fnum(x):
    try:
        return float(str(x).replace("−", "-").strip())
    except (TypeError, ValueError):
        return None


def sections(txt):
    out = {}
    for m in re.finditer(r"(?ms)^🏈\s*([A-Z]{2,3})@([A-Z]{2,3})\b[^\n]*\n(.*?)(?=^🏈|^🏁|\Z)", txt):
        out[f"{m.group(1)}@{m.group(2)}"] = m.group(3)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, required=True); ap.add_argument("--file", required=True); ap.add_argument("--record", action="store_true")
    a = ap.parse_args()
    wd = os.path.join(DATA, f"{SEASON}-w{a.week:02d}")
    games = rd(os.path.join(wd, "games.csv")); model = {f'{r["away"]}@{r["home"]}': r for r in rd(os.path.join(wd, "model.csv"))}
    txt = open(a.file, encoding="utf-8").read().replace("−", "-")
    secs = sections(txt)
    문제, 판단들 = [], []
    keys = [f'{g["away"]}@{g["home"]}' for g in games]
    missing = [k for k in keys if k not in secs]
    if missing:
        문제.append(f"커버리지: 발행문에 없는 경기 {len(missing)}: {', '.join(missing)}")
    for k, body in secs.items():
        if k not in model:
            문제.append(f"{k}: 이번 주 경기가 아님(경기 키 오타?)"); continue
        m = model[k]
        mk = re.search(r"스프레드 홈 ([+-]?[\d.]+)\s*·\s*총점 ([\d.]+)", body)
        if not mk:
            문제.append(f"{k}: 시장 줄 형식(「스프레드 홈 x · 총점 y」) 없음")
        else:
            if fnum(mk.group(1)) != fnum(m["mkt_spread_home"]):
                문제.append(f"{k}: 스프레드 홈 {mk.group(1)} ≠ 다이제스트 {m['mkt_spread_home']}")
            if fnum(mk.group(2)) != fnum(m["mkt_total"]):
                문제.append(f"{k}: 총점 {mk.group(2)} ≠ 다이제스트 {m['mkt_total']}")
        if not re.search(r"(?m)^- 뉴스 확인", body):
            문제.append(f"{k}: 「뉴스 확인(웹)」 줄 없음")
        j = re.search(r"(?m)^- 판단:\s*(패스|소액 관심|관심)(?:\s*·\s*(스프레드|총점)\s*·\s*([^\n]+))?", body)
        if not j:
            문제.append(f"{k}: 판단 줄 없음/형식 오류"); continue
        verdict, market, side = j.group(1), j.group(2), (j.group(3) or "").strip()
        if verdict != "패스" and not (market and side):
            문제.append(f"{k}: {verdict}인데 시장·쪽 라인이 없음")
        if verdict != "패스":
            if market == "스프레드" and not re.fullmatch(r"[A-Z]{2,3} [+-][\d.]+", side):
                문제.append(f"{k}: 스프레드 쪽 형식 「팀 +3.5」 아님: {side}")
            if market == "총점" and not re.fullmatch(r"(Over|Under|오버|언더) [\d.]+", side):
                문제.append(f"{k}: 총점 쪽 형식 「Over 41.5」 아님: {side}")
            판단들.append((k, verdict, market, side))
        if re.search(r"캐시아웃|헤지(?:를|를 하|하세요|권)|라이브로 들어가", body) and not re.search(r"전제가 깨|QB 부상", body):
            문제.append(f"{k}: 캐시아웃·헤지·라이브 권유 문구(금지)")
    n관심 = sum(1 for x in 판단들 if x[1] == "관심")
    if n관심 > 3:
        문제.append(f"「관심」 {n관심}경기 — 주당 최대 3")
    print(f"■ NFL 발행문 검사 week {a.week}: 경기 {len(secs)}/{len(keys)} · 판단 {len(판단들)}(관심 {n관심}) · 문제 {len(문제)}")
    for x in 문제:
        print("  ✗", x)
    for k, v, mk, sd in 판단들:
        print(f"  · {k} {v} · {mk} · {sd}")
    if a.record and 판단들:
        import picks as P
        for k, v, mk, sd in 판단들:
            gid = next((r["game_id"] for r in games if f'{r["away"]}@{r["home"]}' == k), None)
            if not gid:
                continue
            market = "spread" if mk == "스프레드" else "total"
            sd = sd.replace("오버", "Over").replace("언더", "Under")
            line = sd.split()[-1]
            P.lean(a.week, f"{gid}:{market}", sd, line, "-110", f"발행 판단 {v}")
        rows = P.rd(P.PICKS)
        for r in rows:
            if r["grade"] == "관심(설명문)" and int(r["week"]) == a.week and r["note"].startswith("발행 판단"):
                r["grade"] = "관심(발행)"
        P.save(rows)
    return 1 if 문제 else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
