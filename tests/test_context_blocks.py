import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import context_blocks as CB   # noqa: E402
import check_nfl as CK        # noqa: E402


def test_ats_uses_nflverse_sign_convention():
    # spread_line 양수 = 홈 페이버릿 · result = 홈 − 원정. 홈 -4.5 에서 홈이 2점 승 → 홈 ATS L, 원정 W
    x = {"home_team": "DAL", "away_team": "TB", "result": "2", "spread_line": "4.5", "total": "50", "total_line": "47.5"}
    assert CB._ats(x, "DAL") == "L" and CB._ats(x, "TB") == "W" and CB._ou(x) == "O"
    x["result"] = "4.5"
    assert CB._ats(x, "DAL") == "P"


def test_h2h_block_counts(monkeypatch):
    monkeypatch.setattr(CB, "_G", [
        {"season": "2025", "week": "9", "game_type": "REG", "gameday": "2025-11-02", "stadium": "Acrisure", "location": "Home", "roof": "outdoors",
         "away_team": "IND", "home_team": "PIT", "away_score": "20", "home_score": "27", "result": "7", "total": "47", "spread_line": "-3.5", "total_line": "51.5"},
        {"season": "2024", "week": "4", "game_type": "REG", "gameday": "2024-09-29", "stadium": "Lucas Oil", "location": "Home", "roof": "closed",
         "away_team": "PIT", "home_team": "IND", "away_score": "24", "home_score": "27", "result": "3", "total": "51", "spread_line": "-2.5", "total_line": "40"},
        {"season": "2019", "week": "1", "game_type": "REG", "gameday": "2019-09-08", "stadium": "x", "location": "Home", "roof": "outdoors",
         "away_team": "PIT", "home_team": "IND", "away_score": "0", "home_score": "3", "result": "3", "total": "3", "spread_line": "0", "total_line": "40"},
    ])
    L = CB.h2h_block("IND", "PIT")
    body = "\n".join(L)
    assert "2019" not in body                                   # 3시즌 창 밖
    assert "전적 IND 1-1 PIT(2경기)" in body and "PIT 홈에서 IND 0-1 PIT(1경기)" in body
    assert "IND ATS 1-1-0" in body and "O/U 1-1-0" in body


def test_changes_line_reports_only_diffs():
    prev = {"spread_home": "-2.5", "total": "44.5", "ml": "+120/-140", "qb": {"IND": "D.Jones", "PIT": "A.Rodgers"}, "out": {"IND": ["A"], "PIT": []}}
    cur = {"spread_home": "-3.5", "total": "44.5", "ml": "+120/-140", "qb": {"IND": "D.Jones", "PIT": "M.Rudolph"}, "out": {"IND": ["A", "B"], "PIT": []}}
    ln = CB.changes_line(prev, cur, "10-10 04:10")
    assert "스프레드(홈) -2.5 → -3.5" in ln and "PIT 예상 QB A.Rodgers → M.Rudolph" in ln and "IND Out 추가 B" in ln and "총점" not in ln
    assert CB.changes_line({}, cur, "x") is None
    assert CB.changes_line(cur, cur, "x").endswith("없음")


def test_check_nfl_ml_side_pattern():
    assert re.fullmatch(CK.ML_SIDE, "DAL ML -520") and re.fullmatch(CK.ML_SIDE, "IND ML") and not re.fullmatch(CK.ML_SIDE, "DAL -8.5")
    assert "- 키커:" in CK.MUST_LINES and "- 맞대결:" in CK.MUST_LINES
