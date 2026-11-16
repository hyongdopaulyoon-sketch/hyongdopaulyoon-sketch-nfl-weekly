"""team_track.py — 팀별 추적 한 줄(2026-11-16 Paul 「nba 팀별로 추적기는 발행문에는 안보이는데」 → 「nfl도 넣어」 — 추적기 엑셀 「팀별」 시트 값을 다이제스트·발행문에도).
    python scripts/team_track.py PIT CIN
값만(예측 확률·★·판단 근거 아님). 올 시즌 · 승자 예측 = 정식 발행 + 발행 기록 없던 주는 시장 승자 소급(킥오프 뒤 기록용 제외) · 스프레드 = 마감(기록 시점) 홈 라인.
tracker_xlsx.game_rows/team_table 과 같은 계산 — 엑셀 「팀별」 시트와 같은 값."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_T = {}


def table():
    if "v" not in _T:
        import tracker_xlsx as TX
        import picks as P
        rows = TX.game_rows()
        t = {r[0]: r for r in TX.team_table(rows)}
        sp = {}
        for r in P.rd(P.PICKS):
            if r.get("grade") == P.SP_GRADE and r.get("result") in ("W", "L", "P"):
                d = sp.setdefault(str(r["side"]).split()[0], {"W": 0, "L": 0, "P": 0}); d[r["result"]] += 1
        _T["v"] = (t, sp)
    return _T["v"]


def team_line(t):
    tb, sp = table()
    r = tb.get(t)
    if not r:
        return f"{t} — 기록 없음"
    bits = [f"전적 {r[1]}", f"우리가 승자로 예측 {r[2]}", f"상대를 승자로 예측 {r[4]}", f"팀 스프레드 {r[8]}"]
    if t in sp:
        d = sp[t]; bits.append(f"스프레드 픽이 이 팀일 때 {d['W']}-{d['L']}" + (f"-{d['P']}" if d["P"] else ""))
    return f"{t} — " + " · ".join(bits) + (" · 표본 적음" if r[16] else "")


def digest_line(a, h):
    return ("- 📒 팀별 기록(올 시즌 · 우리 예측 = 정식 발행 + 발행 기록 없던 주는 시장 승자 소급 · 값만 — 예측 확률·★·판단 근거 아님 · 추적기 엑셀 「팀별」 시트와 같은 값): "
            + team_line(a) + " / " + team_line(h))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print(digest_line(*(sys.argv[1:3] if len(sys.argv) >= 3 else ("LAC", "BAL"))))
