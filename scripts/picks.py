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
       "placed_at", "result", "score", "units", "note", "closing_line", "clv", "stake", "closing_odds", "clv_prob"]   # clv_prob = 마감 무비그 확률 − 잡은 배당 내재 확률(%p)   # stake = 베팅 크기(유닛, 빈칸 = 1) — 2026-10-01
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
            pid = f'{m["game_id"]}:{market}'
            old = keep.get(pid)
            if not grade.startswith(("관찰", "참고")):
                # 리프레시로 시장 동조가 되면 미집행·미채점 페이퍼 행을 지운다(10/1 PIT@CLE 9/28 「CLE +3 참고」 잔존)
                if old and old["status"] != "placed" and not old["result"] and old["grade"].startswith(("관찰", "참고")):
                    del keep[pid]
                continue
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


def lean(week, pid, side, line, odds="-110", note="", suffix="", grade="관심(설명문)"):
    """사람 판단 페이퍼 기록 — 모델·사람·실베팅을 따로 잰다. id = game_id:spread|total[suffix]
    suffix 를 주면(발행 판단 ':J' · 발행 방향 ':D') 모델 페이퍼 행(game_id:market)을 덮어쓰지 않는다(2026-10-01)."""
    rows = rd(PICKS); keep = {r["id"]: r for r in rows}
    game_id, market = pid.rsplit(":", 1)
    game = next((r["game"] for r in rows if r["id"].startswith(game_id + ":")), game_id.split("_", 2)[-1].replace("_", "@"))
    rid = pid + suffix
    old = keep.get(pid)
    row = {"id": rid, "season": SEASON, "week": week, "game": game, "market": market, "side": side, "line": line, "odds": odds,
           "model_value": old["model_value"] if old else "", "edge": old["edge"] if old else "", "grade": grade, "p_win": old["p_win"] if old else "",
           "status": "suggested" if suffix else (old["status"] if old and old["status"] == "placed" else "suggested"),
           "placed_at": "" if suffix else (old["placed_at"] if old else ""),
           "result": "", "score": "", "units": "", "note": note}
    keep[rid] = row; save(list(keep.values())); print(f"lean 기록: {rid} {side} ({row['status']})")


def place(week, pid=None, all_candidates=False, line=None, odds=None, note="", side=None, stake=None):
    rows = rd(PICKS); n = 0
    if pid and side:
        # 실베팅 쪽이 모델 페이퍼 행과 다르면(예: 모델 Over, Paul Under) 페이퍼 행은 두고 ":P" 행을 따로 만든다(2026-09-28 LA@DEN 사고)
        base = next((r for r in rows if r["id"] == pid), None)
        if base is None or base["side"].split()[0] != side.split()[0] or base["status"] == "placed" and base["side"] != side:
            game = base["game"] if base else next((r["game"] for r in rows if r["id"].startswith(pid.rsplit(":", 1)[0] + ":")), pid.rsplit(":", 1)[0].split("_", 2)[-1].replace("_", "@"))
            row = {k: "" for k in HDR}
            row.update({"id": pid + ":P", "season": SEASON, "week": week, "game": game, "market": pid.rsplit(":", 1)[1], "side": side,
                        "line": line or "", "odds": odds or "-110", "grade": "실베팅", "status": "placed",
                        "placed_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "note": note, "stake": stake or ""})
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
            if stake: r["stake"] = stake
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
    elif r["market"] == "ml":                       # 머니라인(2026-10-04): side 'CIN ML' — 이기면 W, 비기면 P
        team = r["side"].split()[0]
        mine, theirs = (sa, sh) if team == a else (sh, sa)
        d = mine - theirs
    else:
        d = (sa + sh) - fnum(r["side"].split()[1]); d = d if r["side"].startswith("Over") else -d
    return ("P" if d == 0 else "W" if d > 0 else "L"), score


def _closing_dk(week):
    """{game_id: dict} — results 단계가 저장한 DK 마감(closing.csv). 없으면 빈 dict."""
    wd = os.path.join(DATA, f"{SEASON}-w{week:02d}")
    out = {}
    for r in rd(os.path.join(wd, "closing.csv")):
        out[f'{SEASON}_{week:02d}_{r["game"].replace("@", "_")}'] = r
    return out


def _imp(o):
    o = fnum(o)
    if o is None or o == 0:
        return None
    return (-o / (-o + 100)) if o < 0 else (100 / (o + 100))


def clv_price(r, c):
    """가격 CLV(%p) — 같은 라인일 때만: 마감 무비그 확률(우리 쪽) − 우리가 잡은 배당의 내재 확률. + = 우리가 싸게 샀다. (마감 배당, CLV%p)"""
    if not c:
        return None, None
    a, h = r["game"].split("@")
    parts = r["side"].split()
    mine_p = _imp(r.get("odds"))
    if mine_p is None or not parts:
        return None, None
    def nv(x, y):
        px, py = _imp(x), _imp(y)
        return px / (px + py) if px and py else None
    if r["market"] == "ml":
        o_close, o_other = (c.get("ml_home"), c.get("ml_away")) if parts[0] == h else (c.get("ml_away"), c.get("ml_home"))
    elif r["market"] == "spread":
        hl = fnum(c.get("spread_home"))
        if hl is None or len(parts) < 2:
            return None, None
        team_line = hl if parts[0] == h else -hl
        if fnum(parts[1]) != team_line:
            return None, None                        # 라인이 다르면 점 CLV 만(가격 비교 불가)
        o_close, o_other = (c.get("sp_home_odds"), c.get("sp_away_odds")) if parts[0] == h else (c.get("sp_away_odds"), c.get("sp_home_odds"))
    else:
        if len(parts) < 2 or fnum(parts[1]) != fnum(c.get("total")):
            return None, None
        o_close, o_other = (c.get("over_odds"), c.get("under_odds")) if parts[0] == "Over" else (c.get("under_odds"), c.get("over_odds"))
    p = nv(o_close, o_other)
    return (o_close, None) if p is None else (o_close, 100 * (p - mine_p))


def _closing(week):
    """{game_id: (홈 스프레드(베팅 표기, 홈 +3 = 3), 총점)} — nflverse games.csv 마감(spread_line = 홈 기대 마진 → 부호 반전),
    없으면 우리 line_history 마지막 행(DraftKings, 마감 직전이 아닐 수 있음)."""
    out = {}
    for r in rd(os.path.join(DATA, "cache", "games.csv")):
        if r.get("season") == str(SEASON) and r.get("week") == str(week) and fnum(r.get("spread_line")) is not None:
            out[r["game_id"]] = (-fnum(r["spread_line"]), fnum(r.get("total_line")))
    wd = os.path.join(DATA, f"{SEASON}-w{week:02d}")
    last = {}
    for r in rd(os.path.join(wd, "line_history.csv")):          # 시간순 누적 — 마지막 행이 이긴다
        last[f'{SEASON}_{week:02d}_{r["game"].replace("@", "_")}'] = (fnum(r["spread_home"]), fnum(r["total"]))
    for gid, v in last.items():
        out.setdefault(gid, v)
    return out


def clv_of(r, close):
    """픽 시점 라인 대비 마감 라인 이득(점, + = 우리가 더 좋은 숫자를 잡음). 스프레드 'CLE +2.5' · 총점 'Under 38.5'."""
    if not close:
        return None, None
    a, h = r["game"].split("@")
    parts = r["side"].split()
    if len(parts) < 2 or fnum(parts[1]) is None:
        return None, None
    mine = fnum(parts[1])
    if r["market"] == "spread":
        if close[0] is None:
            return None, None
        c = close[0] if parts[0] == h else -close[0]
        return c, mine - c
    if close[1] is None:
        return None, None
    c = close[1]
    return c, (c - mine) if parts[0] == "Over" else (mine - c)


TEASER_FAV, TEASER_DOG, TEASER_TOT = (-8.5, -7.5), (1.5, 2.5), 49.0   # 웡 티저 다리 — 2026-10-01 사전 등록 → **2026-10-10 폐지(Paul 「티저는 별로」)**: weekly 가 더 부르지 않는다. 기록 보존용
TEASER_GRADE = "티저 다리(관찰)"
# 다리 하나의 환산 배당(2026-10-05 정정): 2팀 티저 −120(소수 1.833)의 다리 몫 = √1.833 = 1.354 → −283(손익분기 73.9%).
# 전엔 다리마다 −120 으로 유닛을 셌다 — 손익분기 54.5% 기준이라 유닛이 부풀었다(적중률 판정은 영향 없음).
TEASER_LEG_ODDS = "-283"


def teaser(week, game=None, cents=None, src=""):
    """웡 티저 다리 페이퍼 적립(2026-10-01 Paul 「페이퍼로 기록만」) — 실베팅 아님.
    조건: 시장 스프레드(팀 기준) −7.5~−8.5 또는 +1.5~+2.5 & 총점 ≤49 → 다리 = 그 팀 라인 +6. id = game_id:spread:T.
    리프레시마다 다시 판정 — 가격이 붙었거나 채점된 행은 유지, 그 밖은 범위를 벗어나면 지운다.
    --game AWAY@HOME --cents 73 --src 'Polymarket No' 로 표시 가격을 붙인다(odds 를 미국식으로 환산 → 유닛 손익이 그 가격 기준)."""
    wd = os.path.join(DATA, f"{SEASON}-w{week:02d}")
    rows = rd(PICKS); keep = {r["id"]: r for r in rows}
    cand = {}
    for m in rd(os.path.join(wd, "model.csv")):
        hl, tot = fnum(m["mkt_spread_home"]), fnum(m["mkt_total"])
        if hl is None or tot is None or tot > TEASER_TOT:
            continue
        for team, ln in ((m["home"], hl), (m["away"], -hl)):
            if TEASER_FAV[0] <= ln <= TEASER_FAV[1] or TEASER_DOG[0] <= ln <= TEASER_DOG[1]:
                cand[f'{m["game_id"]}:spread:T'] = (f'{m["away"]}@{m["home"]}', f"{team} {ln + 6:+g}", ln, tot)
    n_new = n_del = 0
    for rid, r in list(keep.items()):
        if r["grade"] == TEASER_GRADE and int(r["week"]) == week and not r["result"] and "표시가" not in r["note"] and rid not in cand:
            del keep[rid]; n_del += 1
    for rid, (g, side, ln, tot) in cand.items():
        old = keep.get(rid)
        if old and (old["result"] or "표시가" in old["note"]):
            continue
        n_new += old is None
        keep[rid] = {k: "" for k in HDR} | {"id": rid, "season": SEASON, "week": week, "game": g, "market": "spread", "side": side,
                                           "line": side.split()[1], "odds": TEASER_LEG_ODDS, "grade": TEASER_GRADE, "status": "suggested",
                                           "note": f"원 라인 {ln:+g} · 총점 {tot:g} · 가격 미기록(2팀 −120 티저의 다리 환산 −283 · 손익분기 73.9%)"}
    if game:
        rid = next((k for k, v in keep.items() if v["grade"] == TEASER_GRADE and v["game"] == game and int(v["week"]) == week), None)
        if not rid:
            sys.exit(f"{game}: 이번 주 티저 다리 후보가 아님")
        if cents is not None:
            c = float(cents)
            keep[rid]["odds"] = f"{-100 * c / (100 - c):.0f}" if c >= 50 else f"+{100 * (100 - c) / c:.0f}"
            keep[rid]["note"] = keep[rid]["note"].split(" · 가격")[0] + f" · 가격 {src} {c:g}c(표시가 — 실베팅 아님)"
    save(list(keep.values()))
    legs = [v for v in keep.values() if v["grade"] == TEASER_GRADE and int(v["week"]) == week]
    print(f"teaser week {week}: 다리 {len(legs)}(신규 {n_new} · 제외 {n_del}) — " + " · ".join(f'{v["game"]} {v["side"]}' for v in legs))


WIND_MPH = 15.0                     # 바람 언더 — 2026-10-01 사전 등록, 조정 금지
WIND_GRADE = "바람 언더(관찰)"
# 홈 구장 좌표(2026) — 실외·개폐식 전부. 중립(해외 등) 경기는 판정하지 않는다(NWS 는 미국만).
STADIUM = {"BAL": (39.2780, -76.6227), "BUF": (42.7738, -78.7870), "CAR": (35.2258, -80.8528), "CHI": (41.8623, -87.6167),
           "CIN": (39.0955, -84.5161), "CLE": (41.5061, -81.6995), "DEN": (39.7439, -105.0201), "GB": (44.5013, -88.0622),
           "JAX": (30.3239, -81.6373), "KC": (39.0489, -94.4839), "MIA": (25.9580, -80.2389), "NE": (42.0909, -71.2643),
           "NYG": (40.8128, -74.0742), "NYJ": (40.8128, -74.0742), "PHI": (39.9008, -75.1675), "PIT": (40.4468, -80.0158),
           "SEA": (47.5952, -122.3316), "SF": (37.4030, -121.9700), "TB": (27.9759, -82.5033), "TEN": (36.1665, -86.7713),
           "WAS": (38.9077, -76.8645), "LA": (33.9535, -118.3392), "LAC": (33.9535, -118.3392), "ARI": (33.5276, -112.2626),
           "ATL": (33.7554, -84.4008), "DAL": (32.7473, -97.0945), "HOU": (29.6847, -95.4107), "IND": (39.7601, -86.1639),
           "MIN": (44.9738, -93.2581), "NO": (29.9511, -90.0812), "DET": (42.3400, -83.0456), "LV": (36.0909, -115.1833)}


def _nws_wind(lat, lon, kick_utc):
    """NWS 시간별 예보에서 킥오프 시각이 든 시간의 지속 풍속(mph, 돌풍 아님). 실패 None."""
    import json, urllib.request
    from datetime import timezone
    def get(u):
        return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "nfl-weekly-paper/1.0"}), timeout=30))
    try:
        hourly = get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}")["properties"]["forecastHourly"]
        for p in get(hourly)["properties"]["periods"]:
            a = datetime.fromisoformat(p["startTime"]).astimezone(timezone.utc); b = datetime.fromisoformat(p["endTime"]).astimezone(timezone.utc)
            if a <= kick_utc < b:
                return fnum(str(p["windSpeed"]).split()[0])
    except Exception as e:
        print(f"  NWS 실패 {lat},{lon}: {e}")
    return None


def wind(week):
    """바람 언더 페이퍼(2026-10-01 Paul 「바람 언더도 페이퍼로 관찰해줘」) — 실베팅 아님.
    조건: 실외(roof outdoors/open) · 중립 아님 · NWS 시간별 예보 킥오프 시각 지속 풍속 ≥15mph → 그 시점 시장 총점 Under.
    판정 시점: 경기 당일(PT) 리프레시만 — 같은 날 여러 번이면 킥오프 전 마지막 판이 이긴다(미채점·킥오프 전 행은 덮어쓰기/삭제).
    킥오프가 지난 경기는 동결(소급 추가·삭제 금지). id = game_id:total:wind. 채점 때 실측 wind 를 note 에 붙인다."""
    from datetime import timezone
    wd = os.path.join(DATA, f"{SEASON}-w{week:02d}")
    rows = rd(PICKS); keep = {r["id"]: r for r in rows}
    now = datetime.now(timezone.utc); today_pt = datetime.now().date()
    seen = []
    for g in rd(os.path.join(wd, "games.csv")):
        kick = datetime.strptime(g["kickoff_utc"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
        rid = f'{g["game_id"]}:total:wind'
        old = keep.get(rid)
        if kick <= now or (old and old["result"]):
            continue                                   # 킥오프 지남 → 동결
        if kick.astimezone().date() != today_pt:
            continue                                   # 경기 당일 판만 센다(일요일 아침 · 목/월 당일)
        if g["roof"] not in ("outdoors", "open") or g.get("neutral") == "1" or g["home"] not in STADIUM or fnum(g["total"]) is None:
            keep.pop(rid, None); continue
        mph = _nws_wind(*STADIUM[g["home"]], kick)
        seen.append(f'{g["away"]}@{g["home"]} {mph if mph is not None else "?"}mph')
        if mph is None or mph < WIND_MPH:
            keep.pop(rid, None); continue
        tot = fnum(g["total"])
        tags = [t for t, ok in (("20mph+", mph >= 20), ("총점 42+", tot >= 42)) if ok]
        keep[rid] = {k: "" for k in HDR} | {"id": rid, "season": SEASON, "week": week, "game": f'{g["away"]}@{g["home"]}', "market": "total",
                                           "side": f"Under {tot:g}", "line": f"{tot:g}", "odds": "-110", "grade": WIND_GRADE, "status": "suggested",
                                           "note": f"예보 {mph:g}mph(NWS 지속·{datetime.now():%m-%d %H:%M} PT)" + (" · " + " · ".join(tags) if tags else "")}
    save(list(keep.values()))
    print(f"wind week {week}: 오늘 경기 예보 " + (" · ".join(seen) or "대상 없음") + f" → 기록 {sum(1 for v in keep.values() if v['grade'] == WIND_GRADE and int(v['week']) == week)}")


ANGLE_GRADES = {"A1": "각도 관찰 A1(원정 큰 페이버릿 반대)", "A2": "각도 관찰 A2(드라이브 우위 언더독 반대)",
                "A3": "각도 관찰 A3(결장 팀 반대 3점+ 이동 → 결장 팀)"}   # 2026-10-10 Paul 「A3는 등록해」(발행 세션 가설 — 역사 백테스트 불가, 전향만)
A3_MOVE = 3.0   # 개장→현재 스프레드 이동(점) 문턱 — 사전 등록, 조정 금지


def angles(week):
    """2026-10-04 Paul 「페이퍼 관찰로」 — 최근 3시즌 탐색(explore_recent.py)의 약한 꼴 두 개를 2026 전향으로 잰다(실베팅 아님).
    A1 원정 팀이 −7 이상 페이버릿 → 홈 언더독 쪽(홈 +라인) · A2 시즌 드라이브 득점 차(공격 − 수비 드라이브당 득점)가 상대보다 0.5+ 큰 팀이
    언더독 → 그 반대(페이버릿) 쪽. 판정: 킥오프 전 리프레시마다 다시(범위 밖이면 미채점 행 삭제), 킥오프 지난 경기는 동결.
    A3(2026-10-10) 개장→현재 스프레드가 **결장 확정 팀**(★주전 Out/Doubtful 최종 지정 또는 백업 QB 선발 — 연습 보고만이면 제외) 반대쪽으로 3점+ 이동
    → 결장 팀 쪽(현재 라인). 가설(발행 세션): 시장이 결장을 과하게 감점한다. 역사 개장 라인이 없어 백테스트 불가 — 전향만, 기존 증거는 반대(백업 QB ATS 49.9%).
    사전 등록: 각 30픽 또는 정규시즌 끝 보고 · <50% 폐기 · ≥55% & 평균 CLV ≥0 이면 Paul 상정."""
    from datetime import timezone
    import stat_research as SR
    wd = os.path.join(DATA, f"{SEASON}-w{week:02d}")
    rows = rd(PICKS); keep = {r["id"]: r for r in rows}
    games = {g["game_id"]: g for g in rd(os.path.join(wd, "games.csv"))}
    inj = {r["team"]: r for r in rd(os.path.join(wd, "injuries.csv"))}
    now = datetime.now(timezone.utc)
    try:
        T, _P, _N = SR.load(SEASON, cache=False)
    except Exception:
        T = {}
    off, de = defaultdict(list), defaultdict(list)
    for (g, wk, pt, dt), x in T.items():
        if wk < week:
            off[pt].append(x); de[dt].append(x)

    def ppd(xs):
        d = sum(x.get("dr", 0) for x in xs)
        return sum(x.get("dr_pts", 0) for x in xs) / d if d else None

    def gp(t):
        return len(off[t])
    cand = {}
    for m in rd(os.path.join(wd, "model.csv")):
        g = games.get(m["game_id"]) or {}
        a, h = m["away"], m["home"]
        hl = fnum(m["mkt_spread_home"])            # 홈 베팅 라인(+ = 홈 언더독)
        if hl is None:
            continue
        if hl >= 7:                                 # 원정 −7 이상 페이버릿
            cand[f'{m["game_id"]}:spread:A1'] = (f"{a}@{h}", f"{h} {hl:+g}", "A1", f"원정 {a} {-hl:+g} 페이버릿")
        os_ = fnum(g.get("open_spread_home"))
        if os_ is not None:                         # A3 — 결장 확정 팀 반대쪽으로 3점+ 이동
            def absent(t):
                x = inj.get(t) or {}
                return bool(x.get("qb_flag")) or ((fnum(x.get("n_starters_missing")) or 0) > 0 and not x.get("final_pending"))
            mv = hl - os_                           # + = 홈 라인이 나빠짐(원정 쪽으로 이동)
            if mv >= A3_MOVE and absent(h):
                cand[f'{m["game_id"]}:spread:A3'] = (f"{a}@{h}", f"{h} {hl:+g}", "A3", f"홈 {h} 결장 확정 · 개장 {os_:+g} → 지금 {hl:+g}(홈 기준, {mv:+g}점 반대 이동)")
            elif -mv >= A3_MOVE and absent(a):
                cand[f'{m["game_id"]}:spread:A3'] = (f"{a}@{h}", f"{a} {-hl:+g}", "A3", f"원정 {a} 결장 확정 · 개장 {os_:+g} → 지금 {hl:+g}(홈 기준, {-mv:+g}점 반대 이동)")
        if gp(a) >= 3 and gp(h) >= 3:
            na = (ppd(off[a]) or 0) - (ppd(de[a]) or 0); nh = (ppd(off[h]) or 0) - (ppd(de[h]) or 0)
            for dog, fav, dline, diff in ((h, a, hl, nh - na), (a, h, -hl, na - nh)):
                if dline > 0 and diff >= 0.5:
                    cand[f'{m["game_id"]}:spread:A2'] = (f"{a}@{h}", f"{fav} {-dline:+g}", "A2",
                                                         f"언더독 {dog} 드라이브 득점 차 우위 {diff:+.2f} → 반대 {fav}")
    n_new = n_del = 0
    for rid, r in list(keep.items()):
        if r["grade"] in ANGLE_GRADES.values() and int(r["week"]) == week and not r["result"] and rid not in cand:
            g = games.get(rid.split(":")[0]) or {}
            if g.get("kickoff_utc") and datetime.strptime(g["kickoff_utc"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc) <= now:
                continue                            # 킥오프 지남 — 동결
            del keep[rid]; n_del += 1
    for rid, (game, side, key, why) in cand.items():
        g = games.get(rid.split(":")[0]) or {}
        if g.get("kickoff_utc") and datetime.strptime(g["kickoff_utc"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc) <= now and rid in keep:
            continue
        if g.get("kickoff_utc") and datetime.strptime(g["kickoff_utc"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc) <= now:
            continue                                # 이미 시작한 경기는 새로 넣지 않는다
        n_new += rid not in keep
        keep[rid] = {k: "" for k in HDR} | {"id": rid, "season": SEASON, "week": week, "game": game, "market": "spread", "side": side,
                                           "line": side.split()[1], "odds": "-110", "grade": ANGLE_GRADES[key], "status": "suggested",
                                           "note": f"{why} · {datetime.now():%m-%d %H:%M} PT 판"}
    save(list(keep.values()))
    legs = [v for v in keep.values() if v["grade"] in ANGLE_GRADES.values() and int(v["week"]) == week]
    print(f"angles week {week}: {len(legs)}(신규 {n_new} · 제외 {n_del}) — " + " · ".join(f'{v["game"]} {v["side"]}({v["id"][-2:]})' for v in legs))


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
        st = fnum(r.get("stake")) or 1.0
        r["units"] = "0" if wl == "P" else (f"{-st:g}" if wl == "L" else f"{st * (100 / abs(o) if o < 0 else o / 100):.3f}")
        n += 1
    # CLV(2026-10-01) — 승패보다 잡음이 훨씬 작아 수십 건이면 「우리 정보가 시장보다 빨랐나」가 보인다
    close = _closing(week); nc = 0
    cdk = _closing_dk(week)
    for gid, c in cdk.items():                     # DK 마감이 있으면 그걸 마감 라인으로(nflverse 보다 우리 북과 같은 기준)
        hl, tl = fnum(c.get("spread_home")), fnum(c.get("total"))
        if hl is not None or tl is not None:
            close[gid] = (hl if hl is not None else (close.get(gid) or (None, None))[0], tl if tl is not None else (close.get(gid) or (None, None))[1])
    for r in rows:
        if int(r["week"]) == week and not r.get("clv_prob") and r["grade"] not in (TEASER_GRADE,):
            co, cp = clv_price(r, cdk.get(r["id"].split(":")[0]))
            if cp is not None:
                r["closing_odds"], r["clv_prob"] = co, f"{cp:+.1f}"
    act = {r["game_id"]: r.get("wind", "") for r in rd(os.path.join(DATA, "cache", "games.csv")) if r.get("season") == str(SEASON)}
    for r in rows:
        if r["grade"] == WIND_GRADE and int(r["week"]) == week and r["result"] and "실측" not in r["note"]:
            r["note"] += f' · 실측 wind {act.get(r["id"].split(":")[0]) or "결측"}' 
    for r in rows:
        if int(r["week"]) == week and not r.get("clv") and r["grade"] != TEASER_GRADE:
            c, v = clv_of(r, close.get(r["id"].split(":")[0]))
            if v is not None:
                r["closing_line"], r["clv"] = f"{c:g}", f"{v:+g}"; nc += 1
    save(rows); print(f"grade week {week}: {n}행 채점 · CLV {nc}행")


def stats():
    rows = [r for r in rd(PICKS) if r["result"] in ("W", "L", "P")]
    def rec(xs, units=True):
        w = sum(1 for x in xs if x["result"] == "W"); l = sum(1 for x in xs if x["result"] == "L"); p = len(xs) - w - l
        u = sum(fnum(x["units"]) or 0 for x in xs)
        pct = f"{100 * w / (w + l):.1f}%" if w + l else "—"
        return f"{w}-{l}" + (f"-{p}" if p else "") + f" {pct}" + (f" {u:+.2f}u" if units else "")
    placed = [r for r in rows if r["status"] == "placed"]; sug = [r for r in rows if r["status"] != "placed"]
    print(f"📊 NFL {SEASON} 픽 성적 — 손익분기 52.4%(−110)")
    # 2026-10-05 Paul 승인: 모델 페이퍼(관찰·참고)는 보고에서 뺀다(기록·추적기는 유지) · 발행 방향은 동전 — 적중률만(유닛 없음)
    print(f"■ 실베팅 {len(placed)}픽 {rec(placed)}")
    dirs = [r for r in rows if r["grade"].startswith("방향(발행)")]
    if dirs:
        print(f"■ 발행 방향(예측 쪽 · 돈 아님) {rec(dirs, units=False)}")
    for lab, xs in (("실베팅", placed), ("발행 판단", [r for r in rows if r["grade"].startswith("관심(발행)")]), ("발행 방향", dirs)):
        cv = [fnum(r.get("clv")) for r in xs if fnum(r.get("clv")) is not None]
        cp = [fnum(r.get("clv_prob")) for r in xs if fnum(r.get("clv_prob")) is not None]
        if cv:
            print(f"  평균 CLV {lab}: {sum(cv) / len(cv):+.2f}점(n {len(cv)} · 우리 쪽 이동 {sum(1 for v in cv if v > 0)} / 반대 {sum(1 for v in cv if v < 0)})")
        if cp and lab == "실베팅":
            print(f"  평균 가격 CLV {lab}: {sum(cp) / len(cp):+.1f}%p(n {len(cp)} — 마감 무비그 확률 − 잡은 배당 확률, ML 포함)")
    for lab, key in (("시장", "market"), ("등급", "grade"), ("주차", "week")):
        by = defaultdict(list)
        for r in placed: by[r[key]].append(r)
        print(f"  {lab}: " + " · ".join(f"{k} {rec(v)}" for k, v in sorted(by.items(), key=lambda kv: str(kv[0]))))
    for g in ("새 정보(관찰)", "새 정보(판 이전·대조)", TEASER_GRADE, WIND_GRADE, *ANGLE_GRADES.values()):
        xs = [r for r in rows if r["grade"] == g]
        if xs:
            print(f"  페이퍼 {g}: {rec(xs)}")
    bk = sorted({r["grade"] for r in rows if r["grade"].endswith("(소급)")})
    if bk:   # 2026-10-05 1~3주차 소급(backfill_weeks.py) — 전향 판정 표본과 따로
        print("  소급 백테스트(기록용 · 전향 판정에 안 섞음): " + " · ".join(f'{g} {rec([r for r in rows if r["grade"] == g])}' for g in bk))


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("suggest"); s.add_argument("--week", type=int, required=True)
    p = sub.add_parser("place"); p.add_argument("--week", type=int, required=True); p.add_argument("--id"); p.add_argument("--all-candidates", action="store_true")
    p.add_argument("--line"); p.add_argument("--odds"); p.add_argument("--note", default=""); p.add_argument("--stake", help="베팅 크기(유닛) — 기본 1"); p.add_argument("--side", help="모델 행과 다른 쪽이면 별도 :P 행")
    l = sub.add_parser("lean"); l.add_argument("--week", type=int, required=True); l.add_argument("--id", required=True); l.add_argument("--side", required=True)
    l.add_argument("--line", required=True); l.add_argument("--odds", default="-110"); l.add_argument("--note", default="")
    g = sub.add_parser("grade"); g.add_argument("--week", type=int, required=True)
    sub.add_parser("wind").add_argument("--week", type=int, required=True)
    sub.add_parser("angles").add_argument("--week", type=int, required=True)
    t = sub.add_parser("teaser"); t.add_argument("--week", type=int, required=True); t.add_argument("--game"); t.add_argument("--cents"); t.add_argument("--src", default="")
    sub.add_parser("stats")
    a = ap.parse_args()
    if a.cmd == "suggest": suggest(a.week)
    elif a.cmd == "place": place(a.week, a.id, a.all_candidates, a.line, a.odds, a.note, a.side, a.stake)
    elif a.cmd == "lean": lean(a.week, a.id, a.side, a.line, a.odds, a.note)
    elif a.cmd == "grade": grade(a.week)
    elif a.cmd == "teaser": teaser(a.week, a.game, a.cents, a.src)
    elif a.cmd == "wind": wind(a.week)
    elif a.cmd == "angles": angles(a.week)
    else: stats()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
