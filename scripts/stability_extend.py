"""adv_players 안정성 r 확장 보고(2026-10-21 클라우드 세션 — 보고 전용, adv_stability.json·코드 반영 안 함).
  python scripts/stability_extend.py
adv_players.stability() 를 그대로 부르되 읽는 폴더만 data/cache/hist 로 돌린다(이 프로세스 안에서만 — 파일은 쓰지 않음).
창: 현행 2024~25 / 확장 2017~25(PFR advstats 는 미러에 2018~ 만 → PFR 지표는 2018~25) / 시즌별 r 범위.
꼬리표 문턱은 adv_players 그대로(≥.45 실력 · .25~.45 중간 · <.25 운)."""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nfl_pull as N      # noqa: E402
import adv_players as AP  # noqa: E402

N.CACHE = os.path.join(N.CACHE, "hist")   # 읽기 경로만 — AP._weekly 가 호출 때 N.CACHE 를 읽는다


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    cur = AP.stability((2024, 2025))
    ext = AP.stability(tuple(range(2017, 2026)))
    per = {s: AP.stability((s,)) for s in range(2017, 2026)}
    print("| 지표 | 자료 | 현행 2024~25 r (n) | 확장 r (n) | 확장 창 | 시즌별 r 범위 | 꼬리표 현행 → 확장 |\n|---|---|---|---|---|---|---|")
    for k, (lab, kind, _, _) in AP.METRICS.items():
        c, e = cur[k], ext[k]
        rs = [per[s][k]["r"] for s in per if per[s][k]["r"] is not None]
        win = "2018~25" if kind.startswith("pfr") else "2017~25"
        chg = "" if c["tier"] == e["tier"] else " ⚠️"
        print(f"| {lab} | {kind} | {c['r']} ({c['n']}) | {e['r']} ({e['n']}) | {win} | {min(rs):.2f}~{max(rs):.2f} | {c['tier']} → {e['tier']}{chg} |")


if __name__ == "__main__":
    main()
