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


def test_stake_scales_units(tmp_path, monkeypatch):
    # 0.5유닛 실베팅은 손익도 0.5배(2026-10-01 PIT -2.5 0.5u)
    monkeypatch.setattr(P, "PICKS", str(tmp_path / "picks.csv")); monkeypatch.setattr(P, "DATA", str(tmp_path))
    os.makedirs(tmp_path / "2026-w04")
    with open(tmp_path / "2026-w04" / "results.csv", "w", encoding="utf-8") as fh:
        fh.write("away,home,status,away_score,home_score\nPIT,CLE,STATUS_FINAL,24,20\n")
    P.save([])
    P.place(4, "2026_04_PIT_CLE:spread", line="-2.5", odds="-120", side="PIT -2.5", stake="0.5")
    P.grade(4)
    r = P.rd(P.PICKS)[0]
    assert r["result"] == "W" and abs(float(r["units"]) - 0.5 * 100 / 120) < 1e-3


def test_grade_moneyline():
    res = {"away_score": "20", "home_score": "24"}
    assert P._grade_one({"game": "JAX@CIN", "market": "ml", "side": "CIN ML"}, res)[0] == "W"
    assert P._grade_one({"game": "JAX@CIN", "market": "ml", "side": "JAX ML"}, res)[0] == "L"
    assert P.clv_of({"game": "JAX@CIN", "market": "ml", "side": "CIN ML"}, (2.5, 51.5)) == (None, None)


def test_price_helpers():
    assert N._cents_to_us(0.52) == "-108" and N._cents_to_us(0.25) == "+300"
    a, b = N._novig("-120", "+100")
    assert abs(a - 0.5217) < 1e-3 and abs(a + b - 1) < 1e-9
    # 가격 CLV: PIT -2.5 를 -108 에 잡았고 마감 PIT -2.5 -120 / CLE +100 → 마감 무비그 52.2% − 내재 51.9% = +0.3%p
    co, cp = P.clv_price({"game": "PIT@CLE", "market": "spread", "side": "PIT -2.5", "odds": "-108"},
                         {"spread_home": "+2.5", "sp_home_odds": "+100", "sp_away_odds": "-120", "total": "38.5", "over_odds": "-105", "under_odds": "-115"})
    assert co == "-120" and abs(cp - 0.3) < 0.1
