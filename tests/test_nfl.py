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


def test_digest_header_rule_numbers():
    """2026-11-05(발행 세션 요청 · 복기/개선/수정 동의 — NBA 방식): 규칙 개정 뒤 「적용 완료」 보고 전에 다이제스트 머리에
    규칙 번호가 실제로 찍히는지. RULES 가 N0 부터 빠짐·중복 없이 이어지고, ph_digest 가 그대로 머리에 싣는다."""
    import re
    import nfl_pull as N
    nums = [int(re.match(r"N(\d+)\.", r).group(1)) for r in N.RULES]
    assert nums == list(range(len(nums))), nums
    assert len(nums) >= 13
    src = open(N.__file__, encoding="utf-8").read()
    assert '["## 운용 규칙(N)", ""] + [f"- {r}" for r in RULES]' in src


def test_first_piece_keeps_parentheses_closed():
    """2026-11-21: 스프레드 픽 사유 첫 토막이 괄호 안에서 끊기지 않는다."""
    import nfl_pull as N
    assert N._first_piece("KC 러시 결장 손실 12점(뛰는 러셔 기준 80 · 전원 가용이면 92)") == "KC 러시 결장 손실 12점(뛰는 러셔 기준 80 · 전원 가용이면 92)"
    assert N._first_piece("홈 ARI 언더독 +15.5 · 다른 토막") == "홈 ARI 언더독 +15.5"
    assert N._first_piece("") == ""


def test_expected_qb_out_moves_to_next_qb(tmp_path):
    """2026-11-21(ARI Beck 주간 Q → 토요일 ESPN Out): 예상 QB 가 Out 이면 일정표 예상 → 뎁스차트 다음 QB, 꼬리표는 실제 지정 종류, qb_flag(N4)는 남는다."""
    import nfl_pull as N
    wd = str(tmp_path)
    N.wcsv(os.path.join(wd, "games.csv"), ["away", "home", "away_qb", "home_qb"], [["ARI", "KC", "Josh Johnson", "Patrick Mahomes"], ["SEA", "LA", "Sam Darnold", "Matthew Stafford"]])
    mk = lambda t, exp, d1, main, note: {"team": t, "expected_qb": exp, "depth_qb1": d1, "season_main_qb": main, "qb_report": "", "qb_flag": "백업 QB 선발 — 옛 문구", "qb_note": note}
    inj = [mk("ARI", "Carson Beck", "Carson Beck", "J.Brissett", "일정표 예상 Josh Johnson 는 묵은 값 — 최근 10주 선발·뎁스차트 QB1 Carson Beck 로 정정"),
           mk("SEA", "Sam Darnold", "Sam Darnold", "S.Darnold", ""), mk("KC", "Patrick Mahomes", "Patrick Mahomes", "P.Mahomes", "")]
    inj[2]["qb_flag"] = ""
    offs = {"ARI": {N._norm_name("Carson Beck")}, "SEA": {N._norm_name("Sam Darnold")}}
    n = N._requalify_expected_qb(wd, inj, offs, set(), {("ARI", N._norm_name("Carson Beck"))}, depth={"ARI": ["Carson Beck", "Josh Johnson"], "SEA": ["Sam Darnold", "Drew Lock"]})
    assert n == 2
    ari, sea, kc = inj
    assert ari["expected_qb"] == "Josh Johnson" and ari["qb_report"] == "Carson Beck Out(ESPN Out)"
    assert ari["qb_flag"].startswith("백업 QB 선발") and "Josh Johnson" in ari["qb_flag"] and "묵은 값" not in ari["qb_note"] and "일정표 예상 Josh Johnson 로 정정" in ari["qb_note"]
    assert sea["expected_qb"] == "Drew Lock" and "당일 비활성" in sea["qb_report"] and "뎁스차트 다음 QB Drew Lock" in sea["qb_note"] and sea["qb_flag"]
    assert kc["expected_qb"] == "Patrick Mahomes" and kc["qb_flag"] == ""


def test_qb_return_only_when_started_before_season_main():
    """2026-11-19: 「주전 복귀」 는 시즌 주전보다 먼저 선발한 적이 있는 QB 만 — 주전이 빠져 올라온 백업은 벌점(N4)."""
    import nfl_pull as N
    old = dict(N._STARTS)
    try:
        N._STARTS.clear()
        N._STARTS.update({"BAL": {1: "L.Jackson", 2: "L.Jackson", 5: "T.Huntley", 6: "T.Huntley", 7: "T.Huntley", 10: "J.Brissett"},
                          "MIA": {1: "M.Willis", 2: "M.Willis", 10: "K.McCord"}})
        assert N._is_qb_return("BAL", "Lamar Jackson", "T.Huntley")          # 먼저 선발 → 복귀
        assert not N._is_qb_return("BAL", "Jacoby Brissett", "T.Huntley")    # 주전 뒤에 처음 선발 → 백업
        assert not N._is_qb_return("MIA", "Kyle McCord", "M.Willis")
        assert not N._is_qb_return("MIA", "Quinn Ewers", "M.Willis")         # 올해 선발 없음 → 백업
    finally:
        N._STARTS.clear(); N._STARTS.update(old)
