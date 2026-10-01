import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import nfl_pull as N   # noqa: E402
import picks as P      # noqa: E402


def test_parse_spread_home_perspective():
    assert N._parse_spread("PIT -3", "CLE") == 3.0        # 원정 PIT 페이버릿 → 홈 +3
    assert N._parse_spread("BUF -7", "BUF") == -7.0       # 홈 페이버릿 → 홈 -7
    assert N._parse_spread("WSH -2.5", "WAS") == -2.5     # ESPN 약칭 → nflverse 약칭
    assert N._parse_spread("EVEN", "BUF") is None


def test_utc_to_et_dst():
    et, pt = N.utc_to_et("2026-10-02T00:15Z")
    assert (et.month, et.day, et.hour, et.minute) == (10, 1, 20, 15) and pt.hour == 17
    et2, _ = N.utc_to_et("2026-11-15T18:00Z")               # 11월 첫 일요일 뒤 — EST(-5)
    assert et2.hour == 13


def test_same_person():
    assert N._same_person("J.Allen", "Josh Allen") and N._same_person("C.Williams", "Caleb Williams")
    assert not N._same_person("C.Rush", "Michael Penix Jr.")


def test_norm_cdf_edge_bands():
    assert abs(N.norm_cdf(3.5 / N.SD_MARGIN) - 0.606) < 0.01
    assert N.norm_cdf(0) == 0.5


def test_grade_spread_and_total():
    res = {"away_score": "20", "home_score": "24"}
    assert P._grade_one({"game": "NE@BUF", "market": "spread", "side": "NE +7"}, res)[0] == "W"    # 20+7 > 24
    assert P._grade_one({"game": "NE@BUF", "market": "spread", "side": "BUF -7"}, res)[0] == "L"
    assert P._grade_one({"game": "NE@BUF", "market": "spread", "side": "BUF -4"}, res)[0] == "P"
    assert P._grade_one({"game": "NE@BUF", "market": "total", "side": "Over 43.5"}, res)[0] == "W"
    assert P._grade_one({"game": "NE@BUF", "market": "total", "side": "Under 43.5"}, res)[0] == "L"


def test_lean_suffix_keeps_model_row(tmp_path, monkeypatch):
    # 발행 판단(:J)·방향(:D) 기록이 모델 페이퍼 행(game_id:market)을 덮어쓰지 않는다(2026-10-01)
    monkeypatch.setattr(P, "PICKS", str(tmp_path / "picks.csv")); monkeypatch.setattr(P, "DATA", str(tmp_path))
    base = {k: "" for k in P.HDR}
    base.update({"id": "2026_04_PIT_CLE:total", "season": "2026", "week": "4", "game": "PIT@CLE", "market": "total",
                 "side": "Under 38.5", "line": "38.5", "grade": "참고", "status": "suggested"})
    P.save([base])
    P.lean(4, "2026_04_PIT_CLE:total", "Over 38.5", "38.5", suffix=":D", grade="방향(발행)")
    rows = {r["id"]: r for r in P.rd(P.PICKS)}
    assert rows["2026_04_PIT_CLE:total"]["side"] == "Under 38.5" and rows["2026_04_PIT_CLE:total"]["grade"] == "참고"
    assert rows["2026_04_PIT_CLE:total:D"]["side"] == "Over 38.5" and rows["2026_04_PIT_CLE:total:D"]["grade"] == "방향(발행)"


def test_clv_spread_and_total():
    # 픽 'CLE +2.5' · 마감 홈(CLE) +1.5 → 1점 이득 / 'PIT -2.5' · 마감 CLE +3.5(PIT -3.5) → +1 / Under 38.5 · 마감 37.5 → +1 / Over 38.5 → −1
    close = (1.5, 37.5)
    assert P.clv_of({"game": "PIT@CLE", "market": "spread", "side": "CLE +2.5"}, close) == (1.5, 1.0)
    assert P.clv_of({"game": "PIT@CLE", "market": "spread", "side": "PIT -2.5"}, (3.5, 37.5)) == (-3.5, 1.0)
    assert P.clv_of({"game": "PIT@CLE", "market": "total", "side": "Under 38.5"}, close) == (37.5, 1.0)
    assert P.clv_of({"game": "PIT@CLE", "market": "total", "side": "Over 38.5"}, close) == (37.5, -1.0)
