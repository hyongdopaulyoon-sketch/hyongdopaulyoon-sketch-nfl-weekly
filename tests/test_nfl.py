import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import nfl_pull as N   # noqa: E402
import picks as P      # noqa: E402


def test_cov_cap_and_a14_side():
    """2026-11-24: 커버리지 점수는 결장으로 못 오른다(상한 = 전원 가용 값 · 상한 전 값은 cov_raw) · A14 = 15점+ 오른 팀의 상대 쪽(두 팀 다면 없음)."""
    import team_hex as TH
    sc, raw = TH.cap_cov({"커버리지": 87, "러시": 40}, {"커버리지": 38, "러시": 55})
    assert sc == {"커버리지": 38, "러시": 40} and raw == 87
    assert TH.cap_cov({"커버리지": 30}, {"커버리지": 45}) == ({"커버리지": 30}, None) and TH.cap_cov(None, None) == (None, None)
    v = {"DET": {"cov_raw": 87, "full": {"커버리지": 38}}, "GB": {"cov_raw": None, "full": {"커버리지": 60}}}
    assert P.a14_side(v, "DET", "GB", -3.5) == ("GB -3.5", "DET", 49, 87, 38)
    assert P.a14_side(v, "GB", "DET", -3.5) == ("GB +3.5", "DET", 49, 87, 38)
    v["GB"] = {"cov_raw": 80, "full": {"커버리지": 60}}
    assert P.a14_side(v, "DET", "GB", -3.5) is None
    v["GB"] = {"cov_raw": 70, "full": {"커버리지": 60}}; v["DET"]["cov_raw"] = 50
    assert P.a14_side(v, "DET", "GB", -3.5) is None     # +12 · +10 — 둘 다 15 미만
    assert "A14" in P.ANGLE_GRADES and P.ANGLE_TARGET["A14"] == 30


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


def test_sack_context_line_and_flag(monkeypatch):
    """2026-11-22: 색 맥락 줄 — 수비 색률·QB 본인 색률 순위(값만) · 「색 잘 당하는 QB 대 색률 상위 8 수비」 는 한쪽만 해당일 때 꼬리."""
    import sack_context as SC
    T = {f"T{i:02d}": {"dsr": 0.10 - i * 0.002, "dsr_rank": i + 1, "qsr": 0.03 + i * 0.002, "qsr_rank": 24 - i, "qb": f"QB{i}"} for i in range(24)}
    assert SC.flag(T, "T00", "T23") and not SC.flag(T, "T23", "T00") and not SC.flag(T, "T00", "T05")
    monkeypatch.setattr(SC, "season_record", lambda before_week=None: (10, 4, 1, 10, 5))
    ln = SC.digest_line("T23", "T00", 11, {}, T)
    assert ln.startswith("- 🧱 색 맥락(값만") and "이번 주 경기하는 24팀 중" in ln and "올해+작년 드롭백 합 · 이번 주 선발 24명 중" in ln and "T00 10.0%(1위)" in ln and "QB23 7.6%(1위 — 색을 잘 당하는 쪽)" in ln
    assert "해당: 색 잘 당하는 QB(T23) 대 색률 상위 8 수비(T00)" in ln and "올해 수비 쪽 스프레드 10-4-1(승자 10-5)" in ln
    assert "해당:" not in SC.digest_line("T10", "T12", 11, {}, T) and SC.digest_line("X", "Y", 11, {}, T) == ""


def test_official_list_needs_scratches_or_three_outs():
    """2026-11-22: 킥오프 직전 Out 한 줄(LV Bowers Q → Out)만으로는 「공식 비활성 명단 도착」 이 아니다 · 건강 제외 행이 있거나 Out 3개+ 면 도착."""
    import nfl_pull as P
    from datetime import datetime
    ko = datetime(2026, 11, 22, 21, 5)
    out = lambda hm, typ="Ankle": {"status": "Out", "date": f"2026-11-22T{hm}", "details": {"type": typ}}
    assert P._official_list([out("19:58"), {"status": "Active", "date": "2026-11-22T20:00", "details": {}}], ko) is False
    assert P._official_list([out("19:58"), out("19:40"), out("19:41")], ko) is True
    assert P._official_list([out("19:40", "Coach's Decision")], ko) is True
    assert P._official_list([out("10:00", "Coach's Decision"), out("19:58")], ko) is False      # 11시간 전 건강 제외 행은 지난 것
    assert P._official_list([{"status": "Out", "date": "2026-11-16T19:40", "details": {"type": "Coach's Decision"}}], ko) is False


def test_recent_start_run_counts_back_from_latest_game(monkeypatch):
    """2026-11-22 Paul: 교체된 QB 의 최근 연속 선발 수(NYG McCarthy 7·9·10주 = 3) — 3경기부터 새 주전(N4 감점 없음)."""
    import nfl_pull as P
    monkeypatch.setattr(P, "_STARTS", {"NYG": {1: "J.Dart", 2: "J.Winston", 6: "J.Winston", 7: "J.McCarthy", 9: "J.McCarthy", 10: "J.McCarthy"},
                                       "LV": {9: "K.Cousins", 10: "F.Mendoza"}})
    assert P._recent_start_run("NYG", "J.J. McCarthy") == 3 and P._recent_start_run("NYG", "Jameis Winston") == 0
    assert P._recent_start_run("LV", "Fernando Mendoza") == 1 and P._recent_start_run("SF", "Anyone") == 0 and P.QB_SETTLED_RUN == 3


def test_final_report_with_zero_designations_is_not_pending():
    """2026-11-22: 지정 0명 팀(NYG)은 같은 시각·이후 킥오프 팀에 지정이 있으면 「최종 보고 나옴」 · 더 이른 팀에만 있으면 아직 미발표."""
    import nfl_pull as P
    games = [{"away": "JAX", "home": "NYG", "kickoff_utc": "2026-11-22T21:05Z"}, {"away": "MIA", "home": "BUF", "kickoff_utc": "2026-11-22T18:00Z"},
             {"away": "CIN", "home": "WAS", "kickoff_utc": "2026-11-24T01:15Z"}]
    prac = {"NYG": [{"x": 1}], "CIN": [{"x": 1}], "JAX": [{"x": 1}]}
    assert P._final_report_out("NYG", {"JAX": [{"x": 1}]}, prac, games) is True
    assert P._final_report_out("NYG", {"MIA": [{"x": 1}]}, prac, games) is False     # 더 이른 경기 팀만 지정 → 판단 못 함
    assert P._final_report_out("CIN", {"JAX": [{"x": 1}], "MIA": [{"x": 1}]}, prac, games) is False   # 월요일 팀은 일요일 팀 지정으로 판단하지 않는다
    assert P._final_report_out("NYG", {"NYG": [{"x": 1}], "JAX": [{"x": 1}]}, prac, games) is False and P._final_report_out("BUF", {"JAX": [{"x": 1}]}, prac, games) is False


def test_team_table_counts_ties():
    """2026-11-22: 무승부 경기가 팀 전적(5-3-1)과 스프레드 결과에 들어간다."""
    import tracker_xlsx as TX
    base = {"발행 적중": "", "발행 예측": "", "예측 승자 커버": "", "스프레드 결과": "", "_side": ""}
    rows = [dict(base, _a="DAL", _h="NYG", **{"결과(승자)": "", "실제 마진(홈)": 0.0}, _cov=3.0),
            dict(base, _a="NYG", _h="PHI", **{"결과(승자)": "NYG", "실제 마진(홈)": -7.0}, _cov=-4.0),
            dict(base, _a="SF", _h="NYG", **{"결과(승자)": "", "실제 마진(홈)": ""}, _cov=None)]
    t = {r[0]: r for r in TX.team_table(rows)}
    assert t["NYG"][1] == "1-0-1" and t["DAL"][1] == "0-0-1" and t["PHI"][1] == "0-1" and t["NYG"][8] == "2-0" and "SF" not in t


def test_carry_ir_rows_keeps_ir_pushed_out_of_espn_list():
    """2026-11-22: ESPN 25건 밖으로 밀린 IR 선수(PHI Hurts)는 앞 판 행을 이어 붙인다 · 이번 판에 다시 나온 선수·IR 아닌 Out·이번 판에 행이 없는 팀은 건드리지 않는다."""
    import nfl_pull as P
    rows = [["PIT@PHI", "PHI", "Cole Payton", "QB", "Out", "Coach's Decision", "", "2026-11-22T16:38", 1, 0, ""],
            ["PIT@PHI", "PHI", "Will Shipley", "RB", "Active", "", "", "2026-11-22T16:41", 1, 0, ""]]
    old = [{"game": "PIT@PHI", "team": "PHI", "player": "Jalen Hurts", "pos": "QB", "status": "Out", "reason": "IR · Calf", "detail": "", "announced_utc": "2026-10-20T18:00", "official": "0", "star": "0", "snap_pct": ""},
           {"game": "PIT@PHI", "team": "PHI", "player": "Will Shipley", "pos": "RB", "status": "Out", "reason": "IR · Knee", "detail": "", "announced_utc": "2026-10-01T18:00", "official": "0", "star": "0", "snap_pct": ""},
           {"game": "PIT@PHI", "team": "PHI", "player": "Old Guy", "pos": "LB", "status": "Out", "reason": "Ankle", "detail": "", "announced_utc": "2026-11-20T18:00", "official": "0", "star": "0", "snap_pct": ""},
           {"game": "MIN@SF", "team": "SF", "player": "Far Away", "pos": "WR", "status": "Out", "reason": "IR · Knee", "detail": "", "announced_utc": "2026-11-01T18:00", "official": "0", "star": "0", "snap_pct": ""}]
    assert P._carry_ir_rows(rows, old) == 1
    assert rows[-1][:6] == ["PIT@PHI", "PHI", "Jalen Hurts", "QB", "Out", "IR · Calf"] and rows[-1][8] == 1 and len(rows) == 3
    assert P._carry_ir_rows(rows, old) == 0


def test_wx_text_picks_the_worded_field():
    """2026-11-22: ESPN 이 날씨 문구와 조건 번호를 뒤바꿔 보내도(「1」/「Sunny」) 글자 있는 쪽을 쓴다 · 둘 다 숫자면 빈칸."""
    import nfl_pull as P
    assert P._wx_text({"displayValue": "1", "conditionId": "Sunny"}) == "Sunny"
    assert P._wx_text({"displayValue": "Rain", "conditionId": "18"}) == "Rain"
    assert P._wx_text({"displayValue": "1", "conditionId": "18"}) == "" and P._wx_text(None) == "" and P._wx_text({}) == ""


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


def test_active_names_drop_from_new_info_candidates():
    """2026-11-25 GB@LA 16:21판: 🏥 줄이 「★Travis Glover(Q → Active 11-25)」 로 적은 선수는 📌 새 정보 후보에서 빠진다."""
    import stat_compare as SC
    txt = "- 🏥 결장 명단(ESPN 공식 비활성 · 발표 15:52 PT): GB Out 3 — Josh Jacobs(RB) · 출전: Micah Parsons(Q → Active 15:49), Bo Melton(Q → Active 15:56), ★Travis Glover(Q → Active 11-25) / LA Out 12 — Ty Simpson(QB)"
    act = SC.active_names(txt)
    assert {"travis glover", "micah parsons", "bo melton"} <= act and "josh jacobs" not in act and "ty simpson" not in act
    assert SC.active_names("") == set() and SC.active_names("- 🏥 결장 명단: GB Out 1 — A.J. Brown(WR)") == set()
    assert "aj brown" in SC.active_names("★A.J. Brown(D → Active 10:02)")
