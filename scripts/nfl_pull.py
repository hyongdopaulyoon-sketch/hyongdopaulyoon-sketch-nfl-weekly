"""NFL 주간 수집·모델·다이제스트 (2026-09-28 Paul 결정: 스프레드+총점 · 별도 레포 · 무료 데이터 · 이번 주부터).

데이터(전부 무료·키 없음):
  · ESPN 공개 스코어보드 — 주간 일정·상태·점수·DraftKings 스프레드/총점/ML·날씨·실내 여부
  · nflverse(GitHub releases) — schedules(휴식일·예상 QB·지붕·마감 라인) · play_by_play(EPA) · injuries(주간 부상 보고) · depth_charts(QB1)

단계: sources → ratings → slate → injuries → model → digest   (results 는 채점용, picks.py 가 부른다)
사용: python nfl_pull.py --week 4 [--phase 이름] [--force]
출력: data/2026-wNN/  games.csv · injuries.csv · model.csv · DIGEST.md   /  data/ratings.csv(시즌 공통)

MLB 에서 가져온 교훈을 처음부터 박는다 — 표본이 1/9 이라 축 가중치 실측은 불가능: 점수는 「모델 − 시장」 하나,
시장과 같은 의견(|엣지| 작음)은 비집행(MLB C19-12), 값이 대체·얇음(※)이면 후보 제외(MLB D13-8), 리스크는 값만 적고 단정 금지.
"""
import argparse
import csv
import gzip
import io
import json
import math
import os
import re
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta

SEASON = 2026
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(DATA, "cache")
NFLVERSE = "https://github.com/nflverse/nflverse-data/releases/download/"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
ESPN2NV = {"WSH": "WAS", "LAR": "LA"}          # ESPN 약칭 → nflverse 약칭(정본은 nflverse)
NV2ESPN = {v: k for k, v in ESPN2NV.items()}

# ── 모델 상수(N 규칙 — 다이제스트 헤더에 그대로 실린다) ──
PLAYS = 62.0          # 팀당 경기 공격 플레이 수(EPA/플레이 → 점수 환산)
HFA = 1.5             # 홈 이점(점) — 2020년대 실측 1.5~2.0
PRIOR_PLAYS = 600.0   # 전 시즌 사전확률 가중(플레이 수 환산 ≈ 10경기)
PRIOR_SHRINK = 0.7    # 전 시즌 값은 30% 0 쪽으로 회귀(연도 간 상관)
DECAY = 0.90          # 주차 감쇠(최근 주 1.0, 한 주 전 0.9 …)
SD_MARGIN = 13.0      # 마진 잔차 표준편차(스프레드 커버 확률)
SD_TOTAL = 10.5       # 총점 잔차 표준편차
QB_ADJ = 4.5          # 예상 선발 QB 가 시즌 주전과 다르면 −4.5점(표시·판정 둘 다)
EDGE_SPREAD = (2.0, 3.5)   # (참고, 후보) 문턱 — 그 밑은 「시장 동조 — 비집행」
EDGE_TOTAL = (3.0, 5.0)
THIN_PLAYS = 150      # 2026 플레이 수가 이 밑이면 ※(값 얇음 — 후보 제외)


# ───────────────────────── 공용 ─────────────────────────
def log(msg):
    print(msg, flush=True)


def fetch(url, path, max_age_h=6, force=False):
    """URL → path 캐시. max_age_h 시간 안이면 재사용. 실패해도 옛 캐시가 있으면 그것을 쓴다."""
    if os.path.exists(path) and not force and (time.time() - os.path.getmtime(path)) < max_age_h * 3600:
        return path
    try:
        req = urllib.request.Request(url)      # UA 는 urllib 기본값 — ESPN 이 다른 UA 문자열에 403 을 준다(2026-09-28 실측)
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        log(f"  fetched {os.path.basename(path)} ({len(data):,} bytes)")
    except Exception as e:
        if os.path.exists(path):
            log(f"  ⚠️ fetch 실패({type(e).__name__}) — 캐시 사용: {os.path.basename(path)}")
        else:
            raise
    return path


def rd(path):
    if not os.path.exists(path):
        return []
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def wcsv(path, hdr, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(hdr); w.writerows(rows)
    os.replace(path + ".tmp", path)
    log(f"  wrote {os.path.relpath(path, ROOT)} ({len(rows)} rows)")


def fnum(x):
    try:
        return float(str(x).strip())
    except (TypeError, ValueError):
        return None


def norm_cdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def utc_to_et(iso):
    """ESPN UTC('2026-10-02T00:15Z') → (ET datetime, PT datetime). 서머타임은 11월 첫 일요일 02:00 까지."""
    d = datetime.strptime(iso[:16], "%Y-%m-%dT%H:%M")
    yr = d.year
    nov1 = datetime(yr, 11, 1)
    dst_end = nov1 + timedelta(days=(6 - nov1.weekday()) % 7)   # 11월 첫 일요일
    mar = datetime(yr, 3, 8)
    dst_start = mar + timedelta(days=(6 - mar.weekday()) % 7)   # 3월 둘째 일요일
    off = 4 if dst_start + timedelta(hours=7) <= d < dst_end + timedelta(hours=6) else 5
    et = d - timedelta(hours=off)
    return et, et - timedelta(hours=3)


def week_dir(week):
    p = os.path.join(DATA, f"{SEASON}-w{int(week):02d}")
    os.makedirs(p, exist_ok=True)
    return p


# ───────────────────────── 단계 ─────────────────────────
def ph_sources(week, force=False):
    """nflverse 원본 5개 + ESPN 스코어보드(주간) 캐시."""
    os.makedirs(CACHE, exist_ok=True)
    fetch(NFLVERSE + "schedules/games.csv", os.path.join(CACHE, "games.csv"), 6, force)
    fetch(NFLVERSE + f"injuries/injuries_{SEASON}.csv", os.path.join(CACHE, f"injuries_{SEASON}.csv"), 6, force)
    fetch(NFLVERSE + f"depth_charts/depth_charts_{SEASON}.csv", os.path.join(CACHE, f"depth_charts_{SEASON}.csv"), 24, force)
    fetch(NFLVERSE + f"pbp/play_by_play_{SEASON}.csv.gz", os.path.join(CACHE, f"play_by_play_{SEASON}.csv.gz"), 12, force)
    fetch(NFLVERSE + f"pbp/play_by_play_{SEASON - 1}.csv.gz", os.path.join(CACHE, f"play_by_play_{SEASON - 1}.csv.gz"), 24 * 30, force)
    fetch(f"{ESPN}?week={week}&seasontype=2&dates={SEASON}", os.path.join(week_dir(week), "espn_scoreboard.json"), 0.5, force)
    # 고급 데이터(2026-10-01 — 다이제스트 서술 전용, 점수·등급엔 안 씀): 스냅 비율 · PFR 압박 · NGS QB
    for sub, name, age in (("snap_counts", f"snap_counts_{SEASON}.csv", 12),
                           ("pfr_advstats", f"advstats_week_def_{SEASON}.csv", 12), ("pfr_advstats", f"advstats_week_pass_{SEASON}.csv", 12),
                           ("pfr_advstats", f"advstats_week_def_{SEASON - 1}.csv", 24 * 30), ("pfr_advstats", f"advstats_week_pass_{SEASON - 1}.csv", 24 * 30),
                           ("nextgen_stats", "ngs_passing.csv.gz", 12), ("ftn_charting", f"ftn_charting_{SEASON}.csv", 12)):
        fetch(NFLVERSE + f"{sub}/{name}", os.path.join(CACHE, name), age, force)
    import adv_players as AP   # 2026-10-10 Paul 「넣어」 — PFR rec/rush · NGS receiving/rushing 미러(서술 전용)
    AP.fetch_all(force)


def _team_week_epa(pbp_path, season):
    """{(team, week): {off_epa, off_n, off_pass_epa, off_pass_n, off_rush_epa, off_rush_n, def_…}} — 정규시즌, 런/패스 플레이만."""
    acc = defaultdict(lambda: defaultdict(float))
    for r in rd(pbp_path):
        if r.get("season_type", "REG") != "REG" or r.get("play_type") not in ("pass", "run"):
            continue
        e = fnum(r.get("epa"))
        if e is None or not r.get("posteam") or not r.get("defteam"):
            continue
        wk = int(r["week"]); kind = "pass" if r["play_type"] == "pass" else "rush"
        o = acc[(r["posteam"], wk)]; d = acc[(r["defteam"], wk)]
        o["off_epa"] += e; o["off_n"] += 1; o[f"off_{kind}_epa"] += e; o[f"off_{kind}_n"] += 1
        d["def_epa"] += e; d["def_n"] += 1; d[f"def_{kind}_epa"] += e; d[f"def_{kind}_n"] += 1
    return acc


def ph_ratings(week, force=False):
    """EPA/플레이 팀 레이팅 — 2026 주차 감쇠 가중 + 2025 사전확률(회귀). data/ratings.csv"""
    out = os.path.join(DATA, "ratings.csv")
    cur = _team_week_epa(os.path.join(CACHE, f"play_by_play_{SEASON}.csv.gz"), SEASON)
    prev = _team_week_epa(os.path.join(CACHE, f"play_by_play_{SEASON - 1}.csv.gz"), SEASON - 1)
    teams = sorted({t for t, _ in cur} | {t for t, _ in prev})
    last_wk = max((w for _, w in cur), default=0)
    games = [g for g in rd(os.path.join(CACHE, "games.csv")) if g["season"] == str(SEASON) and g["game_type"] == "REG" and g.get("home_score")]
    pts = defaultdict(lambda: [0.0, 0.0, 0])   # for, against, games
    for g in games:
        hs, as_ = fnum(g["home_score"]), fnum(g["away_score"])
        if hs is None or as_ is None:
            continue
        pts[g["home_team"]][0] += hs; pts[g["home_team"]][1] += as_; pts[g["home_team"]][2] += 1
        pts[g["away_team"]][0] += as_; pts[g["away_team"]][1] += hs; pts[g["away_team"]][2] += 1
    rows = []
    for t in teams:
        r = {"team": t}
        for side in ("off", "def"):
            for kind in ("", "_pass", "_rush"):
                k_epa, k_n = f"{side}{kind}_epa", f"{side}{kind}_n"
                s = n = 0.0
                for (tt, wk), v in cur.items():
                    if tt == t and v.get(k_n):
                        w = DECAY ** max(0, last_wk - wk)
                        s += w * v[k_epa]; n += w * v[k_n]
                ps = pn = 0.0
                for (tt, wk), v in prev.items():
                    if tt == t and v.get(k_n):
                        ps += v[k_epa]; pn += v[k_n]
                prior = PRIOR_SHRINK * (ps / pn) if pn else 0.0
                r[f"{side}{kind}"] = round((s + prior * PRIOR_PLAYS) / (n + PRIOR_PLAYS), 4)
                if kind == "":
                    r[f"{side}_plays_{SEASON}"] = int(sum(v.get(k_n, 0) for (tt, wk), v in cur.items() if tt == t))
        gp = pts[t][2]
        r["gp"] = gp; r["pf_pg"] = round(pts[t][0] / gp, 1) if gp else ""; r["pa_pg"] = round(pts[t][1] / gp, 1) if gp else ""
        r["net_pts_per_game"] = round(PLAYS * (r["off"] - r["def"]), 1)     # 평균 상대 기준 기대 마진(홈 이점 제외)
        rows.append(r)
    hdr = ["team", "off", "off_pass", "off_rush", "def", "def_pass", "def_rush", f"off_plays_{SEASON}", f"def_plays_{SEASON}", "gp", "pf_pg", "pa_pg", "net_pts_per_game"]
    wcsv(out, hdr, [[r.get(h, "") for h in hdr] for r in rows])
    return rows


def _parse_spread(details, home_abbr):
    """ESPN 'PIT -3' → 홈 기준 스프레드(홈이 3점 페이버릿이면 -3.0). 못 읽으면 None."""
    m = re.match(r"([A-Z]{2,3}) ([+-]?[\d.]+)", str(details or ""))
    if not m:
        return None
    fav, pts = m.group(1), float(m.group(2))
    fav = ESPN2NV.get(fav, fav)
    return pts if fav == home_abbr else -pts


PRICE_COLS = ["sp_home_odds", "sp_away_odds", "over_odds", "under_odds", "open_spread_home", "open_sp_home_odds", "open_sp_away_odds",
              "open_total", "open_over_odds", "open_under_odds", "open_ml_away", "open_ml_home"]


def _espn_prices(odds):
    """ESPN odds 블록(스코어보드 odds[0] 또는 summary pickcenter[0]) → 양쪽 배당·개장 값(2026-10-04 가격 블록).
    스프레드 라인은 홈 기준(홈 +2.5 = 홈 언더독). 값이 없으면 빈칸."""
    def g(*path):
        x = odds or {}
        for k in path:
            x = (x or {}).get(k) if isinstance(x, dict) else None
        return x if x not in (None, "") else ""
    num = lambda v: str(v).lstrip("ou") if v != "" else ""
    return {"sp_home_line": g("pointSpread", "home", "close", "line"), "sp_home_odds": g("pointSpread", "home", "close", "odds"),
            "sp_away_odds": g("pointSpread", "away", "close", "odds"),
            "total_line": num(g("total", "over", "close", "line")), "over_odds": g("total", "over", "close", "odds"), "under_odds": g("total", "under", "close", "odds"),
            "ml_away": g("moneyline", "away", "close", "odds"), "ml_home": g("moneyline", "home", "close", "odds"),
            "open_spread_home": g("pointSpread", "home", "open", "line"), "open_sp_home_odds": g("pointSpread", "home", "open", "odds"),
            "open_sp_away_odds": g("pointSpread", "away", "open", "odds"), "open_total": num(g("total", "over", "open", "line")),
            "open_over_odds": g("total", "over", "open", "odds"), "open_under_odds": g("total", "under", "open", "odds"),
            "open_ml_away": g("moneyline", "away", "open", "odds"), "open_ml_home": g("moneyline", "home", "open", "odds")}


def _implied(o):
    o = fnum(o)
    if o is None or o == 0:
        return None
    return (-o / (-o + 100)) if o < 0 else (100 / (o + 100))


def _novig(o1, o2):
    p1, p2 = _implied(o1), _implied(o2)
    return (p1 / (p1 + p2), p2 / (p1 + p2)) if p1 and p2 else (None, None)


def _cents_to_us(c):
    """예측시장 가격(0~1) → 미국식 배당 문자열."""
    if c is None or not 0 < c < 1:
        return "?"
    return f"{-100 * c / (1 - c):.0f}" if c >= 0.5 else f"+{100 * (1 - c) / c:.0f}"


def _poly(g):
    """Polymarket 경기 시장(gamma 공개 API · slug nfl-{원정}-{홈}-{UTC 날짜}) → 사는 가격(ask, 0~1).
    {"ml": {팀: c}, "spread": {(팀, 라인): c}, "total": {(Over|Under, 라인): c}} — 없거나 실패하면 None. 수수료 미반영."""
    try:
        day = g["kickoff_utc"][:10]
        slug = f"nfl-{g['away'].lower()}-{g['home'].lower()}-{day}"
        path = os.path.join(week_dir_from_game(g), f"poly_{slug}.json")
        # Polymarket 은 urllib 기본 UA 에 403(ESPN 과 반대) — 이 요청에만 브라우저 UA(2026-10-04 실측)
        if not (os.path.exists(path) and time.time() - os.path.getmtime(path) < 1800):
            req = urllib.request.Request(f"https://gamma-api.polymarket.com/events?slug={slug}", headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=30).read()
            open(path + ".tmp", "wb").write(data); os.replace(path + ".tmp", path)
        ev = (json.load(open(path, encoding="utf-8")) or [None])[0]
        if not ev:
            return None
    except Exception:
        return None
    out = {"ml": {}, "spread": {}, "total": {}}
    nick = {}
    for m in ev.get("markets", []) or []:
        if m.get("sportsMarketType") == "moneyline":
            oc = json.loads(m.get("outcomes") or "[]")
            if len(oc) == 2:
                nick = {oc[0]: g["away"], oc[1]: g["home"]}
    for m in ev.get("markets", []) or []:
        if m.get("closed"):
            continue
        try:
            oc = json.loads(m.get("outcomes") or "[]"); ask0 = float(m.get("bestAsk")); bid0 = float(m.get("bestBid"))
        except (TypeError, ValueError):
            continue
        ask1 = 1 - bid0                              # 두 번째 쪽을 사는 가격
        t = m.get("sportsMarketType")
        if t == "moneyline" and len(oc) == 2:
            out["ml"][nick.get(oc[0], oc[0])] = ask0; out["ml"][nick.get(oc[1], oc[1])] = ask1
        elif t == "spreads" and len(oc) == 2 and m.get("line") is not None:
            ln = float(m["line"])
            out["spread"][(nick.get(oc[0], oc[0]), ln)] = ask0; out["spread"][(nick.get(oc[1], oc[1]), -ln)] = ask1
        elif t == "totals" and len(oc) == 2 and m.get("line") is not None:
            ln = float(m["line"])
            out["total"][(oc[0], ln)] = ask0; out["total"][(oc[1], ln)] = ask1
    return out


def _poly_lines(a, h, g):
    """💵 블록 아래 「가격 비교」 — DK 와 같은 라인의 Polymarket 사는 가격, 쪽별로 더 싼 곳."""
    pm = _poly(g)
    if not pm:
        return []
    hl, tl = fnum(g.get("spread_home")), fnum(g.get("total"))
    imp = lambda o: _implied(o)
    rows, best = [], []

    def cmp(label, dk_odds, c):
        if c is None:
            return
        us = _cents_to_us(c)
        rows.append(f"{label} {c * 100:.0f}c({us})")
        d, q = imp(dk_odds), c
        if d is not None:
            best.append(f"{label}: " + (f"Polymarket {us}" if q < d - 1e-9 else f"DK {dk_odds}" if d < q - 1e-9 else f"같음 {dk_odds}"))
    cmp(f"{a} ML", g.get("ml_away"), pm["ml"].get(a)); cmp(f"{h} ML", g.get("ml_home"), pm["ml"].get(h))
    if hl is not None:
        cmp(f"{h} {hl:+g}", g.get("sp_home_odds"), pm["spread"].get((h, hl))); cmp(f"{a} {-hl:+g}", g.get("sp_away_odds"), pm["spread"].get((a, -hl)))
    if tl is not None:
        cmp(f"Over {tl:g}", g.get("over_odds"), pm["total"].get(("Over", tl))); cmp(f"Under {tl:g}", g.get("under_odds"), pm["total"].get(("Under", tl)))
    if not rows:
        return ["    ↳ Polymarket: 같은 라인 시장 없음(다른 라인만 있음)"]
    return [f"    ↳ Polymarket(사는 가격 · 조회 {datetime.now():%H:%M} PT · 수수료 미반영): " + " · ".join(rows),
            "    ↳ 쪽별 더 좋은 가격(같은 라인): " + " · ".join(best)]


def week_dir_from_game(g):
    """경기 행 → 그 주 폴더(game_id 2026_04_… 에서 주차)."""
    try:
        return week_dir(int(str(g.get("game_id", "")).split("_")[1]))
    except Exception:
        return CACHE


def _price_block(a, h, g, hist):
    """💵 가격 — DK 양쪽 배당 · 무비그 확률 · 손익분기 · 개장 → 지금 · 라인 이력(시각별). 서술·기록용(판단 근거는 발행 규칙대로)."""
    if not g.get("sp_home_odds") and not g.get("ml_home"):
        return []
    hl = fnum(g.get("spread_home"))
    pct = lambda v: f"{100 * v:.1f}%" if v is not None else "—"
    sh, sa = _novig(g.get("sp_home_odds"), g.get("sp_away_odds"))
    po, pu = _novig(g.get("over_odds"), g.get("under_odds"))
    ma, mh = _novig(g.get("ml_away"), g.get("ml_home"))
    L = []
    if hl is not None:
        L.append(f"- 💵 가격(DK · 조회 {datetime.now():%m-%d %H:%M} PT): 스프레드 {h} {hl:+g} {g.get('sp_home_odds') or '?'} / {a} {-hl:+g} {g.get('sp_away_odds') or '?'}"
                 f" · 총점 {g.get('total')} O {g.get('over_odds') or '?'} / U {g.get('under_odds') or '?'} · ML {a} {g.get('ml_away') or '?'} / {h} {g.get('ml_home') or '?'}")
        L.append(f"    ↳ 무비그 확률(수수료 뺀 시장 확률): {h} 커버 {pct(sh)} / {a} 커버 {pct(sa)} · Over {pct(po)} / Under {pct(pu)} · 승리 {a} {pct(ma)} / {h} {pct(mh)}")
        be = lambda o: pct(_implied(o))
        L.append(f"    ↳ 손익분기(지금 배당으로 이만큼 맞혀야 본전): {h} {hl:+g} {be(g.get('sp_home_odds'))} · {a} {-hl:+g} {be(g.get('sp_away_odds'))} · "
                 f"Over {be(g.get('over_odds'))} · Under {be(g.get('under_odds'))} · {a} ML {be(g.get('ml_away'))} · {h} ML {be(g.get('ml_home'))}")
        if g.get("open_spread_home") or g.get("open_total"):
            L.append(f"    ↳ 개장 → 지금: 스프레드 {h} {g.get('open_spread_home') or '?'}({g.get('open_sp_home_odds') or '?'}) → {hl:+g}({g.get('sp_home_odds') or '?'})"
                     f" · 총점 {g.get('open_total') or '?'}(O {g.get('open_over_odds') or '?'}) → {g.get('total')}(O {g.get('over_odds') or '?'})"
                     f" · ML {h} {g.get('open_ml_home') or '?'} → {g.get('ml_home') or '?'}")
    L += _poly_lines(a, h, g)
    pts = [x for x in hist if x.get("sp_home_odds")]
    if pts:
        pick = [pts[0]] + pts[1:-1][-3:] + ([pts[-1]] if len(pts) > 1 else [])
        L.append("    ↳ 라인 이력(우리 조회 시각): " + " | ".join(
            f"{x['pulled_at']} {h} {x['spread_home']}({x.get('sp_home_odds') or '?'}) · 총점 {x['total']}(O {x.get('over_odds') or '?'})" for x in pick))
    return L


TEAM_KR = {"ARI": "애리조나 카디널스", "ATL": "애틀랜타 팰컨스", "BAL": "볼티모어 레이븐스", "BUF": "버펄로 빌스", "CAR": "캐롤라이나 팬서스",
           "CHI": "시카고 베어스", "CIN": "신시내티 벵골스", "CLE": "클리블랜드 브라운스", "DAL": "댈러스 카우보이스", "DEN": "덴버 브롱코스",
           "DET": "디트로이트 라이언스", "GB": "그린베이 패커스", "HOU": "휴스턴 텍선스", "IND": "인디애나폴리스 콜츠", "JAX": "잭슨빌 재규어스",
           "KC": "캔자스시티 치프스", "LV": "라스베이거스 레이더스", "LAC": "LA 차저스", "LA": "LA 램스", "MIA": "마이애미 돌핀스",
           "MIN": "미네소타 바이킹스", "NE": "뉴잉글랜드 패트리어츠", "NO": "뉴올리언스 세인츠", "NYG": "뉴욕 자이언츠", "NYJ": "뉴욕 제츠",
           "PHI": "필라델피아 이글스", "PIT": "피츠버그 스틸러스", "SF": "샌프란시스코 49ers", "SEA": "시애틀 시호크스", "TB": "탬파베이 버커니어스",
           "TEN": "테네시 타이탄스", "WAS": "워싱턴 커맨더스"}     # 2026-10-04 팀명 표시(다이제스트 경기 제목 · 보드)


def _predict_line(a, h, res):
    """🔮 예측(2026-10-04 Paul 「결과 예측을 하라」) — 경기 절 맨 위. 시장(가장 정확) + 우리 드라이브 모델(두 번째 의견)."""
    if not res:
        return []
    m, d = res.get("시장"), res.get("모델")
    L = []
    if m:
        mg = m["sh"] - m["sa"]
        fav = h if mg > 0 else a
        import predictions as _PR
        L.append(f'- 🔮 **예측**: 이길 팀 **{m["pick"]} {100 * m["p"]:.0f}% {_PR.star_str(m["p"])}**(2018~25 이 별 적중 {_PR.STAR_HIT[_PR.stars(m["p"])]}) · 예상 점수 **{a} {m["sa"]:.1f} – {h} {m["sh"]:.1f}** '
                 f'(시장 배당 기준 — 가장 정확) · 점수 차 {fav} {abs(mg):.1f} · 총점 {m["sa"] + m["sh"]:.1f}')
    if d:
        warn = " · ⚠️ 시장과 이길 팀이 엇갈림" if m and d["pick"] != m["pick"] else ""
        L.append(f'    ↳ 우리 드라이브 모델(두 번째 의견 · 시장보다 덜 정확): {a} {d["sa"]:.1f} – {h} {d["sh"]:.1f} → {d["pick"]}'
                 + (f' {100 * d["p"]:.0f}%' if d.get("p") is not None else "") + warn)
    return L


def _espn_names(wd):
    """{약칭: ESPN 영문 팀명} — 주간 스코어보드에서."""
    try:
        j = json.load(open(os.path.join(wd, "espn_scoreboard.json"), encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for ev in j.get("events", []):
        for t in ev["competitions"][0]["competitors"]:
            out[ESPN2NV.get(t["team"]["abbreviation"], t["team"]["abbreviation"])] = t["team"].get("displayName", "")
    return out


def ph_slate(week, force=False):
    """ESPN 주간 스코어보드 + nflverse 일정 → data/2026-wNN/games.csv"""
    wd = week_dir(week)
    j = json.load(open(os.path.join(wd, "espn_scoreboard.json"), encoding="utf-8"))
    nv = {(g["away_team"], g["home_team"]): g for g in rd(os.path.join(CACHE, "games.csv"))
          if g["season"] == str(SEASON) and g["week"] == str(week)}
    rows = []
    for ev in j.get("events", []):
        c = ev["competitions"][0]
        home = away = None; hs = as_ = ""; hrec = arec = ""
        for t in c["competitors"]:
            ab = ESPN2NV.get(t["team"]["abbreviation"], t["team"]["abbreviation"])
            rec = (t.get("records") or [{}])[0].get("summary", "")
            if t["homeAway"] == "home":
                home, hs, hrec = ab, t.get("score", ""), rec
            else:
                away, as_, arec = ab, t.get("score", ""), rec
        odds = (c.get("odds") or [{}])[0]
        spread_home = _parse_spread(odds.get("details"), home)
        _px = _espn_prices(odds)
        _ml = odds.get("moneyline") or {}
        ml_a = (((_ml.get("away") or {}).get("close") or {}).get("odds") or "")
        ml_h = (((_ml.get("home") or {}).get("close") or {}).get("odds") or "")
        et, pt = utc_to_et(ev["date"])
        wx = ev.get("weather") or {}
        g = nv.get((away, home), {})
        rows.append([ev["id"], g.get("game_id", ""), ev["date"], et.strftime("%a %m-%d %H:%M"), pt.strftime("%H:%M"),
                     away, home, arec, hrec, c.get("venue", {}).get("fullName", ""), "indoor" if c.get("venue", {}).get("indoor") else g.get("roof", ""),
                     "1" if c.get("neutralSite") else "",
                     wx.get("displayValue", ""), wx.get("temperature", ""),
                     "" if spread_home is None else spread_home, odds.get("overUnder", ""), ml_a or "", ml_h or "", (odds.get("provider") or {}).get("name", ""),
                     g.get("spread_line", ""), g.get("total_line", ""), g.get("away_rest", ""), g.get("home_rest", ""),
                     g.get("away_qb_name", ""), g.get("home_qb_name", ""), g.get("div_game", ""),
                     ev["status"]["type"]["name"], as_, hs] + [_px[k] for k in PRICE_COLS])
    hdr = ["espn_id", "game_id", "kickoff_utc", "kickoff_et", "kickoff_pt", "away", "home", "away_rec", "home_rec", "venue", "roof", "neutral",
           "weather", "temp_f", "spread_home", "total", "ml_away", "ml_home", "odds_provider", "nv_spread_line", "nv_total_line",
           "away_rest", "home_rest", "away_qb", "home_qb", "div_game", "status", "away_score", "home_score"] + PRICE_COLS
    wcsv(os.path.join(wd, "games.csv"), hdr, rows)
    # 라인 이동 기록(정보 — 뉴스가 라인에 먼저 반영된다): 리프레시마다 한 줄씩 누적
    # 2026-10-04: 배당 열 추가(sp_home_odds·sp_away_odds·over_odds·under_odds) — 옛 4열 파일은 새 머리로 다시 쓴다(옛 행 배당 칸은 빈칸)
    lh = os.path.join(wd, "line_history.csv")
    LH = ["pulled_at", "game", "spread_home", "total", "ml_away", "ml_home", "sp_home_odds", "sp_away_odds", "over_odds", "under_odds"]
    old = rd(lh)
    ts = datetime.now().strftime("%m-%d %H:%M")
    ix = {k: hdr.index(k) for k in ("spread_home", "total", "ml_away", "ml_home", "sp_home_odds", "sp_away_odds", "over_odds", "under_odds")}
    new_rows = [[r.get(k, "") for k in LH] for r in old] + [[ts, f"{r[5]}@{r[6]}"] + [r[ix[k]] for k in LH[2:]] for r in rows]
    wcsv(lh, LH, new_rows)


def _qb1_by_team():
    """뎁스차트 최신 QB1 {team: name} · pbp 2026 드롭백 최다 QB {team: name}"""
    dc = defaultdict(dict)
    for r in rd(os.path.join(CACHE, f"depth_charts_{SEASON}.csv")):
        if r.get("pos_abb") == "QB" and r.get("pos_rank") == "1":
            prev = dc[r["team"]]
            if not prev or r["dt"] > prev["dt"]:
                dc[r["team"]] = {"dt": r["dt"], "name": r["player_name"]}
    db = defaultdict(lambda: defaultdict(int))
    for r in rd(os.path.join(CACHE, f"play_by_play_{SEASON}.csv.gz")):
        if r.get("play_type") == "pass" and r.get("passer_player_name") and r.get("posteam"):
            db[r["posteam"]][r["passer_player_name"]] += 1
    main_qb = {t: max(v, key=v.get) for t, v in db.items()}
    return {t: v["name"] for t, v in dc.items()}, main_qb


def _same_person(short, full):
    """pbp 'J.Love' 와 뎁스차트 'Jordan Love' 대조 — 성 일치 + 이니셜."""
    if not short or not full:
        return False
    m = re.match(r"([A-Z])\.\s*(.+)", short)
    if not m:
        return short.split()[-1].lower() == full.split()[-1].lower()
    return full.split()[0][0].upper() == m.group(1) and full.split()[-1].lower() == m.group(2).split()[-1].lower()


def _norm_name(n):
    n = re.sub(r"[.'\-]", "", (n or "").lower())
    return " ".join(w for w in n.split() if w not in ("jr", "sr", "ii", "iii", "iv", "v"))


STARTER_SNAP = 0.60   # 최근 3경기 출전 경기 평균 스냅 비율 60%+ = 주전급


def _snap_pct():
    """{(team, 정규화 이름): 최근 팀 3경기 중 출전 경기의 평균 max(공격, 수비) 스냅 비율} — 결장자가 「얼마나 뛰던 선수」인지."""
    rows = [r for r in rd(os.path.join(CACHE, f"snap_counts_{SEASON}.csv")) if r.get("game_type", "REG") == "REG"]
    team_weeks = defaultdict(set)
    for r in rows:
        team_weeks[r["team"]].add(int(r["week"]))
    acc = defaultdict(list)
    for r in rows:
        if int(r["week"]) in sorted(team_weeks[r["team"]])[-3:]:
            v = max(fnum(r.get("offense_pct")) or 0, fnum(r.get("defense_pct")) or 0)
            if v > 0:
                acc[(r["team"], _norm_name(r["player"]))].append(v)
    return {k: sum(v) / len(v) for k, v in acc.items()}


def _press_by_team(season):
    """PFR 주간 고급 기록 → {team: (수비 압박/경기, 공격 피압박/경기, 경기 수)}."""
    d = rd(os.path.join(CACHE, f"advstats_week_def_{season}.csv")); o = rd(os.path.join(CACHE, f"advstats_week_pass_{season}.csv"))
    dp, op, gm = defaultdict(float), defaultdict(float), defaultdict(set)
    for r in d:
        if r.get("game_type", "REG") == "REG":
            dp[r["team"]] += fnum(r.get("def_pressures")) or 0; gm[r["team"]].add(r["game_id"])
    for r in o:
        if r.get("game_type", "REG") == "REG":
            op[r["team"]] += fnum(r.get("times_pressured")) or 0
    return {t: (dp[t] / len(g), op[t] / len(g), len(g)) for t, g in gm.items() if g}


def _rank(vals, t, high_first=True):
    order = sorted(vals, key=lambda k: vals[k], reverse=high_first)
    return order.index(t) + 1 if t in order else None


def _ngs_qb(team, qb):
    """NGS 시즌 합계(week 0) — 예상 선발 QB 의 2026 값, 없으면 2025. (시즌, 투구 시간, CPOE, 공격성%, 시도)"""
    rows = [r for r in rd(os.path.join(CACHE, "ngs_passing.csv.gz")) if r.get("week") == "0" and r.get("season_type") == "REG"]
    last = (qb or "").split()[-1].lower() if qb else ""
    for season in (str(SEASON), str(SEASON - 1)):
        for r in rows:
            if r["season"] == season and r["player_display_name"].split()[-1].lower() == last and (qb or "")[:1] == r["player_display_name"][:1] \
                    and (season != str(SEASON) or ESPN2NV.get(r["team_abbr"], {"LAR": "LA"}.get(r["team_abbr"], r["team_abbr"])) == team):
                return season, fnum(r["avg_time_to_throw"]), fnum(r["completion_percentage_above_expectation"]), fnum(r["aggressiveness"]), r["attempts"]
    return None


# 2026-10-04 실제 수치 표 — 안정성 r(홀/짝 경기 상관, 2017~2025 직접 측정 · scripts/stat_research.py)를 각 수치 옆에 적는다.
# r ≥ .45 실력(반복된다) · .30~.45 중간 · < .25 운(다음 경기를 거의 예측 못 함). 지어낸 기준 없이 이 측정값만 쓴다.
STAB = {"ppd_o": .61, "td_o": .61, "sc_o": .54, "ppd_d": .36, "qb_cmp": .40, "qb_cpoe": .41, "qb_ypa": .48, "qb_epa": .47, "qb_td": .39,
        "qb_int": .03, "qb_sack": .46, "wr_catch": .50, "wr_ypt": .34, "wr_td": .18, "rb_ypc": .27, "rb_sr": .33}


# 2026-10-05 개선안 3(Paul 승인 · MLB 「소표본 문턱 숫자 고정 + 자동 라벨 + 원값/보정 병기」): 얇은 표본 문턱
THIN_QB_DB, THIN_WR_TGT, THIN_RB_CAR = 150, 30, 40
K_QB = 150          # QB EPA/드롭백 수축 — 선수 모델 사전 등록(7e975b8)과 같은 k, 사전값 = 2026 리그 평균


def _qb_shrunk(x, P):
    """QB 한 명 합계 x → 리그 평균 쪽으로 수축한 EPA/드롭백."""
    tot_e = sum(v.get("epa", 0) for (k, _p, _g), v in P.items() if k == "qb")
    tot_d = sum(v.get("db", 0) for (k, _p, _g), v in P.items() if k == "qb") or 1
    lg = tot_e / tot_d
    return (x.get("epa", 0) + K_QB * lg) / (x.get("db", 0) + K_QB)


def _qb_of(t, RS, inj):
    """(이름, 드롭백, 원 EPA/드롭백, 보정 EPA) — 예상 선발 QB(없으면 드롭백 최다)."""
    if not RS:
        return None
    _T, P, NM = RS
    agg = defaultdict(lambda: defaultdict(float))
    for (k, pid, g), x in P.items():
        if k == "qb" and NM.get(pid, ("", ""))[1] == t:
            for kk, vv in x.items():
                agg[pid][kk] += vv
    if not agg:
        return None
    exp = (inj.get(t) or {}).get("expected_qb") or ""
    pid = next((pp for pp in agg if exp and _same_person(NM[pp][0], exp)), None)
    if pid is None and exp:
        return exp, 0, None, None                     # 예상 선발이 2026 드롭백 0 — 다른 QB 값으로 채우지 않는다(10/5 ATL Penix ← C.Rush 오표시)
    pid = pid or max(agg, key=lambda pp: agg[pp].get("db", 0))
    x = agg[pid]; db = x.get("db", 0)
    return NM[pid][0], int(db), (x.get("epa", 0) / db if db else None), _qb_shrunk(x, P)


# ⚖️ 저울질 표(2026-10-05 개선안 1 · MLB 보드 세션 상의) — 값만. 점수 칸 = 백테스트 근거(점수 0 = 시장이 이미 반영).
# MLB 교훈: 점수 0 항목에 「유리/불리·우위·중대」 낱말을 찍으면 발행 세션이 근거로 써 버린다 → 방향 낱말 없이 값과 근거만.
BAL_EVID = {
    "qb": "0 — 2018~22 선수 모델 QB 조정 방향 45%(n370 · 시장이 더 정확, 7e975b8)",
    "press": "0 — 2018~22 압박 미스매치 −0.19점 p .64(F3 · n632)",
    "pass": "0 — 팀 EPA 모델 점수 차 오차 10.48 > 시장 9.92(1,151경기)",
    "rest": "0 — 2023~25 라인·일정 15항목 전부 잡음(BH) · 목요일 원정 48.9%",
    "wx": "0 — 바람 15mph+ 언더는 따로 관찰 중(2006~25 55%, 최근 3년 53% — 약한 신호)",
    "inj": "0 — 주전 결장 수 차 −0.15점/명 p .44(F1 · n2,110) · 라인 뒤 발표분만 「새 정보」 관찰",
    "line": "정보 — 움직였다 = 시장이 이미 소화",
}


_PRIOR = None


def _prior_and_h2h():
    """nflverse 캐시 → ({(시즌, 팀): [승, 패]}, 정규시즌 끝난 경기 목록) — 저울질 표 「작년 성적 · 최근 맞대결」(10/5 Paul 「응」)."""
    global _PRIOR
    if _PRIOR is None:
        rec = defaultdict(lambda: [0, 0]); done = []
        for x in rd(os.path.join(CACHE, "games.csv")):
            if x.get("game_type") != "REG" or x.get("result") in ("", None):
                continue
            r = int(float(x["result"])); s_ = int(x["season"]); done.append(x)
            if r:
                rec[(s_, x["home_team"])][0 if r > 0 else 1] += 1; rec[(s_, x["away_team"])][1 if r > 0 else 0] += 1
        _PRIOR = (rec, done)
    return _PRIOR


def _balance_table(a, h, g, RS, inj, P26, PRO):
    """⚖️ 저울질 표 — 경기마다 같은 7행. 표시 전용(재계산 없음 — 값은 다이제스트 다른 표와 같은 원천)."""
    L = ["- ⚖️ **저울질 표(값만 — 점수 칸은 백테스트 근거 · 점수 0 = 시장이 이미 반영 · 「유리/불리」로 읽지 않는다)**:", "",
         f"| 항목 | {a} | {h} | 점수 · 근거 |", "|---|---|---|---|"]
    q = {t: _qb_of(t, RS, inj) for t in (a, h)}

    def qcell(t):
        x = q[t]
        if x and x[2] is None:
            return f"{x[0]} — 2026 드롭백 0(기록 없음 ※ 얇음)"
        if not x:
            return "—"
        nm, db, raw, sh = x
        return f"{nm} 원 {raw:+.2f} → 보정 {sh:+.2f}(드롭백 {db}{' ※ 얇음' if db < THIN_QB_DB else ''})"
    L.append(f"| QB 수준(EPA/드롭백 · k={K_QB}) | {qcell(a)} | {qcell(h)} | {BAL_EVID['qb']} |")

    def pcell(o, d):
        if o not in P26 or d not in P26:
            return "—"
        return f"피압박 {P26[o][1]:.1f}/경기 vs {d} 압박 {P26[d][0]:.1f}/경기"
    L.append(f"| 패스 보호 vs 상대 압박 | {pcell(a, h)} | {pcell(h, a)} | {BAL_EVID['press']} |")

    def ecell(o, d):
        if o not in PRO or d not in PRO or PRO[o].get("o_pepa") is None or PRO[d].get("d_pepa") is None:
            return "—"
        return f"공격 {PRO[o]['o_pepa']:+.3f} vs {d} 수비 {PRO[d]['d_pepa']:+.3f}"
    L.append(f"| 패스 공격 vs 상대 패스 수비(드롭백 EPA) | {ecell(a, h)} | {ecell(h, a)} | {BAL_EVID['pass']} |")
    L.append(f"| 휴식 | {g.get('away_rest') or '?'}일 | {g.get('home_rest') or '?'}일{' · 디비전' if g.get('div_game') == '1' else ''} | {BAL_EVID['rest']} |")
    wx = f"{g.get('roof') or '?'} · {g.get('weather') or '예보 없음'}" + (f" {g.get('temp_f')}°F" if g.get("temp_f") else "")
    L.append(f"| 날씨 | {wx} | (같은 구장) | {BAL_EVID['wx']} |")

    def icell(t):
        x = inj.get(t) or {}
        n = str(x.get("n_starters_missing") or "0")
        return f"★주전 {'연습 불참' if x.get('final_pending') else 'Out/Doubtful'} {n}명"
    L.append(f"| 주전 결장(스냅 60%+) | {icell(a)} | {icell(h)} | {BAL_EVID['inj']} |")
    rec, done = _prior_and_h2h()
    py = SEASON - 1

    def prior(t):
        w, l = rec.get((py, t), [0, 0])
        return f"{py} {w}-{l}" + (f"({w / (w + l):.3f})" if w + l else "")
    mt = sorted([x for x in done if {x["away_team"], x["home_team"]} == {a, h} and int(x["season"]) >= SEASON - 3],
                key=lambda x: (x["season"], int(x["week"])))[-4:]
    ha = sum(1 for x in mt if (int(float(x["result"])) > 0) == (x["home_team"] == a) and int(float(x["result"])) != 0)
    hh = sum(1 for x in mt if (int(float(x["result"])) > 0) == (x["home_team"] == h) and int(float(x["result"])) != 0)
    last2 = " · ".join(f'{x["season"]} {x["away_team"]} {x["away_score"]}–{x["home_score"]} {x["home_team"]}' for x in mt[-2:])
    L.append(f"| 작년 성적 | {prior(a)} | {prior(h)} | 0 — 2007~25 작년 승률 .25+ 높은 팀 커버 50.3%(n1,934) · 시장 확률과 실제 승률 일치(37.5% vs 38.3%) |")
    L.append(f"| 최근 맞대결({SEASON - 3}~ · 최근 {len(mt)}경기) | {a} {ha}승 | {h} {hh}승{' · ' + last2 if last2 else ''} | "
             f"0 — 2006~25 직전 맞대결 진 팀 리턴매치 커버 51.5%(n2,594 · 손익분기 52.4% 미만, 우연 범위) · MLB H2H 도 기각(9/1·9/5) |")
    os_, ns_, ot_, nt_ = (fnum(g.get("open_spread_home")), fnum(g.get("spread_home")), fnum(g.get("open_total")), fnum(g.get("total")))
    mv = (f"스프레드(홈) {os_:+g} → {ns_:+g}" if os_ is not None and ns_ is not None else "스프레드 개장값 없음") +          (f" · 총점 {ot_:g} → {nt_:g}" if ot_ is not None and nt_ is not None else "")
    L.append(f"| 라인 개장 → 지금 | {mv} | | {BAL_EVID['line']} |")
    L += ["", "  ↳ 점수 합계 0 — 이 표는 🔮 시장 예측을 바꾸지 않는다. 점수를 받을 수 있는 후보는 발행 세션이 채우는 「라인 뒤 새 정보」뿐(관찰 중 · 30픽 판정).", ""]
    return L


def _stab(key):
    r = STAB[key]
    return f"r {r:.2f}·" + ("실력" if r >= .45 else "중간" if r >= .25 else "운")


def _real_stats():
    """2026 플레이별 기록 → (팀-경기 합계, 선수-경기 합계, 이름) — stat_research.load 재사용(진행 중 시즌은 캐시 안 함)."""
    import stat_research as SR
    try:
        return SR.load(SEASON, cache=False)
    except Exception as e:
        log(f"  실제 수치 계산 실패: {type(e).__name__}")
        return None


def _real_stats_block(a, h, RS, inj, games_row, model_row):
    """📈 실제 수치 — 드라이브 득점 확률(공격·상대 수비) · 드라이브 기반 예상 득점 vs 시장 내재 득점 · QB·리시버·러셔 실제 성적.
    서술 전용 — 드라이브 모델은 2018~2025 1,618경기에서 시장보다 덜 정확(점수 차 오차 10.38 vs 9.92)."""
    if not RS:
        return []
    import stat_research as SR
    T, P, NM = RS
    off, de = defaultdict(list), defaultdict(list)
    for (g, wk, pt, dt), x in T.items():
        off[pt].append(x); de[dt].append(x)
    allx = list(T.values())
    lg = sum(x.get("dr_pts", 0) for x in allx) / max(sum(x.get("dr", 0) for x in allx), 1)

    def rate(rows, num, den, mult=1):
        b = sum(r.get(den, 0) for r in rows)
        if num == "score":
            a_ = sum(r.get("dr_td", 0) + r.get("dr_fg", 0) for r in rows)
        else:
            a_ = sum(r.get(num, 0) for r in rows)
        return (mult * a_ / b) if b else None

    def drives(rows):
        return int(sum(r.get("dr", 0) for r in rows))
    L = []
    ppd = {}
    for t, opp in ((a, h), (h, a)):
        ppd[t] = (SR.shrunk_ppd(off[t], lg, SR.K_OFF), SR.shrunk_ppd(de[opp], lg, SR.K_DEF))
    exp_a = SR.DRIVES_PG * (ppd[a][0] + ppd[a][1] - lg) - HFA / 2
    exp_h = SR.DRIVES_PG * (ppd[h][0] + ppd[h][1] - lg) + HFA / 2
    hl, tot = fnum(model_row.get("mkt_spread_home")), fnum(model_row.get("mkt_total"))
    mk_h = (tot - hl) / 2 if hl is not None and tot is not None else None
    mk_a = (tot + hl) / 2 if hl is not None and tot is not None else None

    def novig(ml_a, ml_h):
        def imp(o):
            o = fnum(o)
            if o is None:
                return None
            return (-o / (-o + 100)) if o < 0 else (100 / (o + 100))
        pa_, ph_ = imp(ml_a), imp(ml_h)
        return (pa_ / (pa_ + ph_), ph_ / (pa_ + ph_)) if pa_ and ph_ else (None, None)
    wa, wh = novig(games_row.get("ml_away"), games_row.get("ml_home"))
    pct = lambda v: f"{v:.0f}%" if v is not None else "—"
    num = lambda v, fm: (fm.format(v) if v is not None else "—")
    L += ["- 📈 **실제 수치(서술 — 점수 아님 · 창: 2026 정규시즌 전체(프리시즌·플레이오프 제외) · 각 수치 옆 r = 2017~2025 실측 안정성: 실력 ≥.45 / 중간 / 운 <.25 · "
          f"※ 얇음 = QB 드롭백 <{THIN_QB_DB} · 리시버 타깃 <{THIN_WR_TGT} · 러셔 캐리 <{THIN_RB_CAR} → 근거 금지)**:", "",
          f"| 수치 | {a} | {h} |", "|---|---|---|"]
    L.append(f"| 공격 드라이브당 득점({_stab('ppd_o')}) — 원값(드라이브 수) → 보정 | {num(rate(off[a], 'dr_pts', 'dr'), '{:.2f}')}({drives(off[a])}) → {ppd[a][0]:.2f} | {num(rate(off[h], 'dr_pts', 'dr'), '{:.2f}')}({drives(off[h])}) → {ppd[h][0]:.2f} |")
    L.append(f"| 공격 드라이브 TD 확률({_stab('td_o')}) | {pct(rate(off[a], 'dr_td', 'dr', 100))} | {pct(rate(off[h], 'dr_td', 'dr', 100))} |")
    L.append(f"| 공격 드라이브 득점(TD+FG) 확률({_stab('sc_o')}) | {pct(rate(off[a], 'score', 'dr', 100))} | {pct(rate(off[h], 'score', 'dr', 100))} |")
    L.append(f"| 상대 수비가 내준 드라이브당 득점({_stab('ppd_d')}) — 원값 → 보정 | {h} 수비 {num(rate(de[h], 'dr_pts', 'dr'), '{:.2f}')} → {ppd[a][1]:.2f} | {a} 수비 {num(rate(de[a], 'dr_pts', 'dr'), '{:.2f}')} → {ppd[h][1]:.2f} |")
    L.append(f"| 예상 득점 — 드라이브 모델(리그 {lg:.2f}/드라이브 · 경기당 {SR.DRIVES_PG:.0f}드라이브) / 시장 내재 | {exp_a:.1f} / {num(mk_a, '{:.1f}')} | {exp_h:.1f} / {num(mk_h, '{:.1f}')} |")
    L.append(f"| 승리 확률 — 시장(ML 무비그) | {pct(wa * 100 if wa else None)} | {pct(wh * 100 if wh else None)} |")

    def team_players(t, kind):
        agg = defaultdict(lambda: defaultdict(float))
        for (k, pid, g), x in P.items():
            if k == kind and NM.get(pid, ("", ""))[1] == t:
                for kk, vv in x.items():
                    agg[pid][kk] += vv
        return agg

    def qb_cell(t):
        agg = team_players(t, "qb")
        if not agg:
            return "—"
        exp = (inj.get(t) or {}).get("expected_qb") or ""
        pid = next((pp for pp in agg if exp and _same_person(NM[pp][0], exp)), None)
        if pid is None and exp:
            return f"{exp}: 2026 기록 없음(드롭백 0 ※ 얇음 — 근거 금지)"
        pid = pid or max(agg, key=lambda pp: agg[pp].get("db", 0))
        x = agg[pid]
        att = x.get("att", 0) or 1
        cp = (x["cpoe"] / x["cpoe_n"]) if x.get("cpoe_n") else None
        db = x.get("db", 0)
        thin = (f" · ※ 얇음(드롭백 {int(db)} < {THIN_QB_DB} — 근거 금지 · 보정 EPA {_qb_shrunk(x, P):+.2f})" if db < THIN_QB_DB else "")
        return (f"{NM[pid][0]}: 완성 {100 * x.get('cmp', 0) / att:.0f}%({_stab('qb_cmp')}) · CPOE {num(cp, '{:+.1f}')}({_stab('qb_cpoe')}) · "
                f"야드/시도 {x.get('yds', 0) / att:.1f}({_stab('qb_ypa')}) · EPA/드롭백 {x.get('epa', 0) / max(x.get('db', 1), 1):+.2f}({_stab('qb_epa')}) · "
                f"TD {100 * x.get('td', 0) / att:.1f}%({_stab('qb_td')}) · 색 {100 * x.get('sack', 0) / max(x.get('db', 1), 1):.1f}%({_stab('qb_sack')}) · "
                f"INT {100 * x.get('int', 0) / att:.1f}%({_stab('qb_int')}) · 시도 {int(att)} · 드롭백 {int(db)}{thin}")

    def rec_cell(t):
        agg = team_players(t, "rec")
        tops = sorted(agg, key=lambda pp: -agg[pp].get("tgt", 0))[:2]
        out = []
        for pp in tops:
            x = agg[pp]; tg = x.get("tgt", 0) or 1
            st = _status_of(NM[pp][0], inj.get(t, {}))
            out.append(f"{NM[pp][0]}{' ⚠️' + st if st else ''}: 타깃 {int(tg)}{f' ※ 얇음(<{THIN_WR_TGT} — 근거 금지)' if tg < THIN_WR_TGT else ''} · 캐치율 {100 * x.get('cmp', 0) / tg:.0f}%({_stab('wr_catch')}) · "
                       f"야드/타깃 {x.get('yds', 0) / tg:.1f}({_stab('wr_ypt')}) · TD {int(x.get('td', 0))}({_stab('wr_td')})")
        return " / ".join(out) or "—"

    def rush_cell(t):
        agg = team_players(t, "rush")
        if not agg:
            return "—"
        pp = max(agg, key=lambda q: agg[q].get("car", 0)); x = agg[pp]; c = x.get("car", 0) or 1
        st = _status_of(NM[pp][0], inj.get(t, {}))
        return (f"{NM[pp][0]}{' ⚠️' + st if st else ''}: 캐리 {int(c)}{f' ※ 얇음(<{THIN_RB_CAR} — 근거 금지)' if c < THIN_RB_CAR else ''} · 야드/캐리 {x.get('yds', 0) / c:.1f}({_stab('rb_ypc')}) · "
                f"성공률 {100 * x.get('suc', 0) / c:.0f}%({_stab('rb_sr')})")
    L.append(f"| QB(예상 선발 — 2026 실제 성적) | {qb_cell(a)} | {qb_cell(h)} |")
    L.append(f"| 리시버 상위 2(타깃순) | {rec_cell(a)} | {rec_cell(h)} |")
    L.append(f"| 러셔 1위(캐리순) | {rush_cell(a)} | {rush_cell(h)} |")
    L += ["", "  ↳ 읽는 법: r(안정성)이 높은 수치(드라이브당 득점·EPA·야드/시도·캐치율)는 실력이라 다음 경기에도 이어질 가능성이 크고, "
          "INT%·레드존 TD%·리시버 TD 수처럼 r 이 낮은 수치는 운이라 몇 경기 값으로 판단하지 않는다. 예상 득점은 드라이브 모델보다 **시장 내재 값이 더 정확**하다"
          "(2018~2025 1,618경기 점수 차 오차 시장 9.92 vs 드라이브 모델 10.38 · 총점 10.38 vs 10.83).", ""]
    return L


def _team_profile():
    """2026 정규시즌 pbp → 팀별 공격·수비 단위 성적(2026-10-03 포지션 매치업 표 — 서술 전용).
    공격/수비 각각: 드롭백 EPA·성공률 · 러시 EPA·성공률 · 색 비율 · 턴오버/경기 · 3rd down 전환율.
    선수: 타깃 점유율·EPA/타깃(리시버) · 캐리 점유율·EPA/캐리(러셔) — 상위 2명·1명."""
    o = defaultdict(lambda: defaultdict(float)); d = defaultdict(lambda: defaultdict(float))
    games = defaultdict(set); rec = defaultdict(lambda: defaultdict(lambda: [0, 0.0])); rus = defaultdict(lambda: defaultdict(lambda: [0, 0.0]))
    for r in rd(os.path.join(CACHE, f"play_by_play_{SEASON}.csv.gz")):
        if r.get("season_type", "REG") != "REG" or not r.get("posteam") or r.get("play_type") not in ("pass", "run"):
            continue
        pt, dt = r["posteam"], r["defteam"]; epa = fnum(r.get("epa")) or 0.0; suc = fnum(r.get("success")) or 0.0
        games[pt].add(r["game_id"]); games[dt].add(r["game_id"])
        db = fnum(r.get("qb_dropback")) == 1
        for side, x in (("o", o[pt]), ("d", d[dt])):
            k = "p" if db else "r"
            x[k + "n"] += 1; x[k + "epa"] += epa; x[k + "suc"] += suc
            if db:
                x["sack"] += fnum(r.get("sack")) == 1
            x["to"] += (fnum(r.get("interception")) == 1) + (fnum(r.get("fumble_lost")) == 1)
            if r.get("down") == "3":
                x["3n"] += 1; x["3c"] += fnum(r.get("first_down")) == 1 or fnum(r.get("touchdown")) == 1
        if db and r.get("receiver_player_name"):
            v = rec[pt][r["receiver_player_name"]]; v[0] += 1; v[1] += epa; o[pt]["tgt"] += 1
        if not db and r.get("rusher_player_name"):
            v = rus[pt][r["rusher_player_name"]]; v[0] += 1; v[1] += epa; o[pt]["car"] += 1
    out = {}
    for t in set(o) | set(d):
        x, y, g = o[t], d[t], max(len(games[t]), 1)
        row = {"g": g}
        for pre, z in (("o", x), ("d", y)):
            row[pre + "_pepa"] = z["pepa"] / z["pn"] if z["pn"] else None
            row[pre + "_psr"] = z["psuc"] / z["pn"] if z["pn"] else None
            row[pre + "_repa"] = z["repa"] / z["rn"] if z["rn"] else None
            row[pre + "_rsr"] = z["rsuc"] / z["rn"] if z["rn"] else None
            row[pre + "_sack"] = z["sack"] / z["pn"] if z["pn"] else None
            row[pre + "_to"] = z["to"] / g
            row[pre + "_3rd"] = z["3c"] / z["3n"] if z["3n"] else None
        row["rec"] = sorted(((n, c, e / c, c / x["tgt"]) for n, (c, e) in rec[t].items() if x["tgt"]), key=lambda v: -v[1])[:2]
        row["rus"] = sorted(((n, c, e / c, c / x["car"]) for n, (c, e) in rus[t].items() if x["car"]), key=lambda v: -v[1])[:1]
        out[t] = row
    return out


def _status_of(short, inj_row):
    """pbp 짧은 이름(「J.Jefferson」) → 그 팀 부상 줄의 상태 꼬리표(Out/Doubtful/Questionable/연습 DNP·Limited) 또는 ""."""
    for key, lab in (("out", "Out"), ("doubtful", "Doubtful"), ("questionable", "Q"), ("dnp", "연습 DNP"), ("limited", "연습 Limited")):
        for full in [x.split("(")[0].strip() for x in str(inj_row.get(key) or "").split(" · ") if x.strip()]:
            if full and _same_person(short, full):
                return lab
    return ""


def _matchup_table(a, h, PRO, P26, inj):
    """📊 포지션 매치업 — 두 방향(원정 공격 vs 홈 수비 · 홈 공격 vs 원정 수비), 영역마다 값·리그 순위. 서술 전용(N0 —
    점수·등급에 안 넣는다: 2026-10-01 특징 백테스트에서 결장·압박·CPOE 모두 마감 라인 대비 잔차 0과 미구분)."""
    if a not in PRO or h not in PRO:
        return []
    T = list(PRO)

    def rk(key, t, high=True):
        vals = {u: PRO[u][key] for u in T if PRO[u].get(key) is not None}
        return _rank(vals, t, high) if t in vals else None

    def cell(off, de, okey, dkey, fmt, o_high, d_high, unit=""):
        ov, dv = PRO[off].get(okey), PRO[de].get(dkey)
        if ov is None or dv is None:
            return "—"
        ro, rd_ = rk(okey, off, o_high), rk(dkey, de, d_high)
        return f"{off} {fmt.format(ov)}{unit}({ro}위) vs {de} {fmt.format(dv)}{unit}({rd_}위)"

    def press(off, de):
        if off not in P26 or de not in P26:
            return "—"
        ov, dv = P26[off][1], P26[de][0]
        ro = _rank({t: v[1] for t, v in P26.items()}, off, False); rd_ = _rank({t: v[0] for t, v in P26.items()}, de)
        return f"{off} 피압박 {ov:.1f}/경기({ro}위) vs {de} 압박 {dv:.1f}/경기({rd_}위)"

    def players(t):
        x, ir = PRO[t], inj.get(t, {})
        parts = [f'{n} 타깃 {sh * 100:.0f}%·EPA/타깃 {e:+.2f}' + (f' ⚠️{_status_of(n, ir)}' if _status_of(n, ir) else "") for n, c, e, sh in x["rec"]]
        parts += [f'{n} 캐리 {sh * 100:.0f}%·EPA/캐리 {e:+.2f}' + (f' ⚠️{_status_of(n, ir)}' if _status_of(n, ir) else "") for n, c, e, sh in x["rus"]]
        return " · ".join(parts) or "—"

    g = min(PRO[a]["g"], PRO[h]["g"])
    L = [f"- 📊 포지션 매치업(서술 — 점수 아님 · 2026 {g}경기{' ※ 얇음' if g < 6 else ''} · 순위는 32팀 중 · 값과 순위만(10/5 「우위」 낱말 삭제 — 점수 0 항목)):", "",
         f"| 영역 | {a} 공격 → {h} 수비 | {h} 공격 → {a} 수비 |", "|---|---|---|"]
    rows = [("패스(드롭백 EPA)", "o_pepa", "d_pepa", "{:+.3f}", True, False, ""),
            ("패스 성공률", "o_psr", "d_psr", "{:.0%}", True, False, ""),
            ("러시(EPA)", "o_repa", "d_repa", "{:+.3f}", True, False, ""),
            ("러시 성공률", "o_rsr", "d_rsr", "{:.0%}", True, False, ""),
            ("색 비율(드롭백당)", "o_sack", "d_sack", "{:.1%}", False, True, ""),
            ("턴오버/경기(공격 잃음 · 수비 뺏음)", "o_to", "d_to", "{:.1f}", False, True, ""),
            ("3rd down 전환", "o_3rd", "d_3rd", "{:.0%}", True, False, "")]
    for lab, ok, dk, fmt, oh, dh, u in rows:
        L.append(f"| {lab} | {cell(a, h, ok, dk, fmt, oh, dh, u)} | {cell(h, a, ok, dk, fmt, oh, dh, u)} |")
    L.append(f"| 패스 보호 vs 압박(PFR) | {press(a, h)} | {press(h, a)} |")
    L.append(f"| 핵심 선수(2026 점유율) | {players(a)} | {players(h)} |")
    L.append("")
    return L


def _ftn_by_team():
    """FTN 차팅 × pbp(game_id·play_id 조인) → 팀별 드롭백 성향(2026-10-01 서술 전용).
    공격: pa 플레이액션 비율 · bl_epa 블리츠 받았을 때 EPA/드롭백 · intw 가로채기 위험 패스 비율 · n 드롭백
    수비: d_bl 블리츠 비율 · d_n 상대 드롭백"""
    ftn = {(r["nflverse_game_id"], r["nflverse_play_id"]): r for r in rd(os.path.join(CACHE, f"ftn_charting_{SEASON}.csv"))}
    if not ftn:
        return {}
    o, d = defaultdict(lambda: defaultdict(float)), defaultdict(lambda: defaultdict(float))
    for r in rd(os.path.join(CACHE, f"play_by_play_{SEASON}.csv.gz")):
        if r.get("season_type", "REG") != "REG" or fnum(r.get("qb_dropback")) != 1:
            continue
        f = ftn.get((r["game_id"], str(int(fnum(r["play_id"]) or 0))))
        if not f or not r.get("posteam"):
            continue
        bl = (fnum(f.get("n_blitzers")) or 0) > 0
        x, y = o[r["posteam"]], d[r["defteam"]]
        x["n"] += 1; x["pa"] += f["is_play_action"] == "TRUE"; x["intw"] += f["is_interception_worthy"] == "TRUE"
        if bl:
            x["bl_n"] += 1; x["bl_epa"] += fnum(r.get("epa")) or 0
        y["d_n"] += 1; y["d_bl"] += bl
    out = {}
    for t in set(o) | set(d):
        x, y = o.get(t, {}), d.get(t, {})
        out[t] = {"pa": x["pa"] / x["n"] if x.get("n") else None, "intw": x["intw"] / x["n"] if x.get("n") else None,
                  "bl_epa": x["bl_epa"] / x["bl_n"] if x.get("bl_n") else None, "bl_n": int(x.get("bl_n", 0)),
                  "d_bl": y["d_bl"] / y["d_n"] if y.get("d_n") else None}
    return out


def _ftn_text(off_t, def_t, F):
    if not F or off_t not in F or def_t not in F:
        return ""
    v = lambda k: {t: x[k] for t, x in F.items() if x[k] is not None}
    o, d = F[off_t], F[def_t]
    parts = []
    if o["pa"] is not None:
        parts.append(f"{off_t} 플레이액션 {o['pa'] * 100:.0f}%(많은 순 {_rank(v('pa'), off_t)}위)")
    if o["bl_epa"] is not None:
        parts.append(f"블리츠 받을 때 EPA/드롭백 {o['bl_epa']:+.2f}(좋은 순 {_rank(v('bl_epa'), off_t)}위 · {o['bl_n']}회)")
    if o["intw"] is not None:
        parts.append(f"가로채기 위험 패스 {o['intw'] * 100:.1f}%")
    if d["d_bl"] is not None:
        parts.append(f"vs {def_t} 블리츠 {d['d_bl'] * 100:.0f}%(많은 순 {_rank(v('d_bl'), def_t)}위)")
    return " · FTN: " + " · ".join(parts) if parts else ""


def _pass_matchup_lines(off_t, def_t, qb, P26, P25, F=None):
    """「off_t 패스 공격 vs def_t 수비 압박」 한 줄 — 서술 전용."""
    dv = {t: v[0] for t, v in P26.items()}; ov = {t: v[1] for t, v in P26.items()}
    q = _ngs_qb(off_t, qb)
    qtxt = (f"QB {qb} 투구 시간 {q[1]:.2f}초 · CPOE {q[2]:+.1f} · 공격적 패스 {q[3]:.0f}%(시도 {q[4]}{', 2025' if q[0] != str(SEASON) else ''})" if q and q[1] is not None
            else f"QB {qb or '?'} NGS 기록 없음")
    def_ = P26.get(def_t); off_ = P26.get(off_t)
    dtxt = (f"{def_t} 수비 압박 경기당 {def_[0]:.1f}(리그 {_rank(dv, def_t)}위)" if def_ else f"{def_t} 수비 압박 기록 없음")
    otxt = (f"{off_t} 공격 피압박 경기당 {off_[1]:.1f}(적은 순 {_rank(ov, off_t, high_first=False)}위)" if off_ else "")
    n = min(def_[2] if def_ else 0, off_[2] if off_ else 0)
    p25 = []
    if def_t in P25:
        p25.append(f"{def_t} 압박 {P25[def_t][0]:.1f}")
    if off_t in P25:
        p25.append(f"{off_t} 피압박 {P25[off_t][1]:.1f}")
    thin = f" ※ 2026 {n}경기 — 얇음" if n and n < 6 else ""
    return (f"- 패스 매치업(서술 — 점수 아님) {off_t} 공격 → {def_t} 수비: {qtxt} · {otxt} vs {dtxt}{thin}"
            + (f" (2025 경기당: {' · '.join(p25)})" if p25 else "") + _ftn_text(off_t, def_t, F))


def ph_injuries(week, force=False):
    """nflverse 부상 보고(해당 주, 없으면 최신 주) + 뎁스차트 QB1 → data/2026-wNN/injuries.csv (팀별 한 줄)"""
    wd = week_dir(week)
    inj = rd(os.path.join(CACHE, f"injuries_{SEASON}.csv"))
    weeks = sorted({int(r["week"]) for r in inj})
    use = week if week in weeks else (max(weeks) if weeks else None)
    by, prac = defaultdict(list), defaultdict(list)
    for r in inj:
        if use is not None and int(r["week"]) == use:
            if r.get("report_status"):
                by[r["team"]].append(r)
            elif r.get("practice_status"):
                prac[r["team"]].append(r)
    qb1, main_qb = _qb1_by_team()
    games = rd(os.path.join(wd, "games.csv"))
    teams = sorted({g["away"] for g in games} | {g["home"] for g in games})
    snap = _snap_pct()

    def nm(r):
        # 「이름(포지션 · 스냅 n%)」 — 최근 3경기 출전 경기 평균, 60%+ 는 ★주전급 (2026-10-01)
        v = snap.get((r["team"], _norm_name(r["full_name"])))
        return f'{r["full_name"]}({r["position"]}' + (f' · {"★" if v >= STARTER_SNAP else ""}스냅 {v * 100:.0f}%' if v else "") + ")"

    def n_star(rs):
        return sum(1 for r in rs if (snap.get((r["team"], _norm_name(r["full_name"]))) or 0) >= STARTER_SNAP)
    rows = []
    for t in teams:
        out = [nm(r) for r in by[t] if r["report_status"] == "Out"]
        dbt = [nm(r) for r in by[t] if r["report_status"] == "Doubtful"]
        q = [nm(r) for r in by[t] if r["report_status"] == "Questionable"]
        qb_rep = next((f'{r["full_name"]} {r["report_status"]}' for r in by[t] if r["position"] == "QB" and r["report_status"] in ("Out", "Doubtful", "Questionable")), "")
        exp = next((g["away_qb"] if g["away"] == t else g["home_qb"] for g in games if t in (g["away"], g["home"])), "")
        # 벌점(qb_flag): ⓐ 예상 선발이 뎁스차트 QB1 이 아니다(백업 선발) ⓑ 보고가 QB Out/Doubtful.
        # 정보(qb_note): 예상 선발 = QB1 인데 시즌 드롭백 최다 QB 와 다르다 → 주전 복귀(레이팅은 대체 QB 표본이 섞여 있음) — 벌점 아님.
        flag, note = "", ""
        d1 = qb1.get(t, "")
        if exp and d1 and d1.split()[-1].lower() != exp.split()[-1].lower():
            flag = f"백업 QB 선발 — 뎁스차트 QB1 {d1} 대신 예상 선발 {exp}"
        elif exp and main_qb.get(t) and not _same_person(main_qb[t], exp):
            note = f"주전 복귀 — 시즌 드롭백 최다 {main_qb[t]}, 예상 선발 {exp}(레이팅에 대체 QB 표본 섞임)"
        if qb_rep and ("Out" in qb_rep or "Doubtful" in qb_rep):
            flag = (flag + " · " if flag else "") + f"QB 보고 {qb_rep}" + (f"({use}주차 보고 — 잠정)" if use and int(use) != int(week) else "")
        # 최종 지정(Out/Q) 전엔 nflverse 가 연습 보고만 올린다 → 「Out 0」이 아니라 「미발표」(2026-10-01 PIT@CLE: 다이제스트 0, 실제 C·G·WR Out)
        pending = "" if by[t] else ("미발표" if prac[t] else "")
        dnp = [nm(r) for r in prac[t] if r["practice_status"].startswith("Did Not")]
        lim = [nm(r) for r in prac[t] if r["practice_status"].startswith("Limited")]
        starters = n_star([r for r in by[t] if r["report_status"] in ("Out", "Doubtful")]) if by[t] else n_star(
            [r for r in prac[t] if r["practice_status"].startswith("Did Not")])
        qb_prac = next((f'{r["full_name"]} {"DNP" if r["practice_status"].startswith("Did Not") else "Limited"}' for r in prac[t]
                        if r["position"] == "QB" and r["practice_status"].startswith(("Did Not", "Limited"))), "")
        if pending and qb_prac:
            note = (note + " · " if note else "") + f"QB 연습 {qb_prac}(최종 지정 미발표 — 잠정)"
        rows.append([t, use or "", exp, d1, main_qb.get(t, ""), qb_rep, flag, note, len(out), len(dbt), len(q),
                     " · ".join(out), " · ".join(dbt), " · ".join(q), pending, len(dnp), len(lim), " · ".join(dnp), " · ".join(lim), starters])
    wcsv(os.path.join(wd, "injuries.csv"), ["team", "report_week", "expected_qb", "depth_qb1", "season_main_qb", "qb_report", "qb_flag", "qb_note",
                                             "n_out", "n_doubtful", "n_questionable", "out", "doubtful", "questionable",
                                             "final_pending", "n_dnp", "n_limited", "dnp", "limited", "n_starters_missing"], rows)


def ph_model(week, force=False):
    """게임별 모델 마진·총점·승률 vs 시장 → 엣지·판정. data/2026-wNN/model.csv"""
    wd = week_dir(week)
    rt = {r["team"]: r for r in rd(os.path.join(DATA, "ratings.csv"))}
    inj = {r["team"]: r for r in rd(os.path.join(wd, "injuries.csv"))}
    games = rd(os.path.join(wd, "games.csv"))
    lg = [fnum(r["pf_pg"]) for r in rt.values() if fnum(r["pf_pg"]) is not None]
    lg_ppg = sum(lg) / len(lg) if lg else 22.0
    rows = []
    for g in games:
        a, h = g["away"], g["home"]
        ra, rh = rt.get(a), rt.get(h)
        if not ra or not rh:
            continue
        oa, da, oh, dh = fnum(ra["off"]), fnum(ra["def"]), fnum(rh["off"]), fnum(rh["def"])
        margin = PLAYS * ((oh + da) - (oa + dh)) + (0.0 if g.get("neutral") == "1" else HFA)   # 홈 기준 기대 마진(중립 구장 HFA 0)
        qb_adj_h = -QB_ADJ if (inj.get(h, {}).get("qb_flag")) else 0.0
        qb_adj_a = -QB_ADJ if (inj.get(a, {}).get("qb_flag")) else 0.0
        margin += qb_adj_h - qb_adj_a
        total = 2 * lg_ppg + PLAYS * ((oh + da) + (oa + dh)) + qb_adj_h + qb_adj_a
        p_home = norm_cdf(margin / SD_MARGIN)
        thin = [t for t, r in ((a, ra), (h, rh)) if int(r.get(f"off_plays_{SEASON}") or 0) < THIN_PLAYS]
        mk_sp = fnum(g["spread_home"]); mk_sp = mk_sp if mk_sp is not None else fnum(g["nv_spread_line"]) and -fnum(g["nv_spread_line"])
        mk_tot = fnum(g["total"]) if fnum(g["total"]) is not None else fnum(g["nv_total_line"])
        # nflverse spread_line 은 홈 기준 「홈 − 원정」 기대 마진(양수 = 홈 페이버릿) → 홈 스프레드 = −spread_line
        edge_sp = None if mk_sp is None else margin - (-mk_sp)
        edge_tot = None if mk_tot is None else total - mk_tot
        def band(e, th):
            # 2026-09-28 백테스트(2024·2025 정규시즌 ~450경기): 모델 방향 ATS ≈ 45%, 괴리 3.5점+ 구간은 시장이 맞았다(2025 31%).
            # 그래서 모델−시장 괴리는 **베팅 후보가 아니라 관찰(페이퍼) 대상**이다. 실베팅은 Paul 판단(QB·뉴스·라인 이동)으로 place.
            if e is None:
                return "시장 결측"
            return "관찰(큰 괴리 — 페이퍼)" if abs(e) >= th[1] else "참고" if abs(e) >= th[0] else "시장 동조"
        sp_side = "" if edge_sp is None else (f"{h} {mk_sp:+g}" if edge_sp > 0 else f"{a} {-mk_sp:+g}")
        tot_side = "" if edge_tot is None else (f"Over {mk_tot:g}" if edge_tot > 0 else f"Under {mk_tot:g}")
        sp_grade, tot_grade = band(edge_sp, EDGE_SPREAD), band(edge_tot, EDGE_TOTAL)
        if thin:
            sp_grade += " ※"; tot_grade += " ※"
        p_cover = "" if edge_sp is None else round(norm_cdf(abs(edge_sp) / SD_MARGIN) * 100, 1)
        p_tot = "" if edge_tot is None else round(norm_cdf(abs(edge_tot) / SD_TOTAL) * 100, 1)
        rows.append([g["game_id"] or g["espn_id"], a, h, round(margin, 1), round(p_home * 100, 1), round(total, 1),
                     "" if mk_sp is None else mk_sp, "" if mk_tot is None else mk_tot,
                     "" if edge_sp is None else round(edge_sp, 1), sp_side, sp_grade, p_cover,
                     "" if edge_tot is None else round(edge_tot, 1), tot_side, tot_grade, p_tot,
                     qb_adj_a, qb_adj_h, "※" if thin else "", ",".join(thin)])
    wcsv(os.path.join(wd, "model.csv"),
         ["game_id", "away", "home", "model_margin_home", "p_home_win", "model_total", "mkt_spread_home", "mkt_total",
          "edge_spread", "spread_side", "spread_grade", "p_cover", "edge_total", "total_side", "total_grade", "p_total",
          "qb_adj_away", "qb_adj_home", "thin", "thin_teams"], rows)


RULES = [
    "N0. **모델은 베팅 신호가 아니다(2026-09-28 백테스트 확정).** 2024·2025 정규시즌 ~450경기에서 EPA 모델 방향 ATS ≈ 45%, 모델−시장 괴리 3.5점+ 구간은 시장이 맞았다(2025 15-33). 마감 라인 MAE 는 시장 10.1 < 모델 11.3. 단순 각도(홈독·디비전독·휴식·바이·목요일·실외 12월 등 19개, 2015~25 2,895경기)도 전부 50~54%·시즌 일관성 없음. → 모델·괴리는 **정보·리스크 서술과 페이퍼 추적**에만 쓴다.",
    "N1. **점수는 「모델 − 시장」 하나다(페이퍼).** 모델 = EPA/플레이 팀 레이팅(2026 주차 감쇠 0.9 · 2025 사전확률 600플레이·30% 회귀) × 62플레이 + 홈 1.5점 + QB 교체 −4.5점. 축·가중치 실측은 표본(주 16경기)이 안 돼 하지 않는다 — MLB 에서 배운 것.",
    "N2. **등급은 세 가지 — 시장 동조 / 참고 / 관찰(큰 괴리 — 페이퍼)**. 스프레드 2.0·3.5점, 총점 3.0·5.0점 문턱. 「후보」 등급은 없다 — 실베팅은 Paul 이 QB·부상 뉴스·라인 이동을 보고 정하고 picks.py place 로 기록한다. 관찰 등급은 suggested(페이퍼)로 자동 적립해 모델이 시장보다 나은지 계속 잰다.",
    "N3. **※ 값 얇음** — 어느 한 팀의 2026 플레이가 150 미만이면 후보 제외(참고까지). 대체값으로 4★ 를 세우지 않는다(MLB D13-8).",
    "N4. **QB 가 전부다** — 예상 선발 QB 가 시즌 주전과 다르거나 보고가 Out/Doubtful 이면 −4.5점을 모델에 넣고 리스크 첫 줄에 쓴다. 일요일 아침 최종 리프레시 전엔 「잠정」.",
    "N5. **리스크는 값만 적는다** — 휴식일·디비전·날씨(바람 15mph+·강수)·부상 수는 사실로만, 「그래서 이긴다/진다」로 단정하지 않는다(MLB B14·B10-1 교훈).",
    "N6. **손익분기** — 스프레드·총점 −110 기준 52.4%. 시즌 목표는 이기는 것보다 **기록·검증**(약 240경기): placed(실베팅) 와 suggested(페이퍼) 를 따로 세어 사람 판단과 모델 어느 쪽이 시장을 이기는지 본다.",
    "N7. **기록** — picks.py suggest 가 관찰·참고를 picks.csv 에 「suggested」(페이퍼)로 적고, 실제 베팅한 것만 place 로 바꾼다(모델 제안이 아닌 경기도 place 가능). 채점은 월요일 grade. 성적은 placed 와 suggested 를 따로 센다.",
    "N8. **판정 개정은 주 1회(화요일)** 결과를 보고 pending_rules.md 한 줄로 남긴 뒤에만 바꾼다. 같은 주 안에서 문턱을 손대지 않는다.",
    "N9. **캐시아웃·헤지·라이브 진입은 하지 않는다** — 북의 캐시아웃 가격은 공정가보다 5~10% 나쁘고, 헤지는 수수료를 두 번 낸다. 예외는 베팅 전제가 깨졌을 때(QB 부상 등)뿐(2026-09-28 PHI@CHI 전반 7-0 질문).",
    "N10. **발행은 claude.ai NFL 발행 세션이 한다(2026-09-29 Paul)** — 이 다이제스트를 붙여넣으면 경기별 발행문(예측·방향·시장·뉴스 확인(웹)·**맞대결·📊 스탯 비교(말로, 전 행)·팀 비교·심판(2026-10-10 Paul 필수)**·맥락·결론·판단)을 쓰고 「판단: 패스/소액 관심/관심」(돈을 거느냐)과 **「방향: 스프레드 쪽 · 총점 쪽」(패스여도 필수 — 2026-10-01 Paul 「결정 없이 서술만」)** 을 낸다. 로컬은 check_nfl.py 로 숫자·형식을 대조하고 판단(관심(발행))·방향(방향(발행))을 따로 페이퍼로 기록한다. 발행 세션의 몫은 **최신 뉴스(QB 확정·새 부상·라인 이동) 확인** — 다이제스트 부상 보고는 전 주차 것일 수 있다.",
    "N11. **ML(이길 팀)이 주인공이다(2026-10-10 Paul 「티저는 버리고 ML에 집중」)** — 🔮 예측(시장 ML 무비그 확률·★)이 모든 경기의 첫 줄이고, 판단·실베팅은 ML 도 기록한다(「판단: 관심 · ML · 팀 배당」). 2018~25 실측: 시장 페이버릿 ML 을 배당대로 걸면 ★★★★ −1.6% · ★★★ −1.9% · ★★ −3.1% · ★ −9.6%(언더독은 ★ 구간만 +4.3%) — 별이 많을수록 잘 맞지만 수수료 때문에 자동 베팅은 손해. 그래서 ML 집중 = 예측 정확도·새 정보·가격(DK vs Polymarket 더 싼 쪽) 쪽이지 페이버릿 자동 매수가 아니다.",
    "N12. **🧩 티저 다리는 폐지(2026-10-10 Paul 「티저는 별로」)** — 다이제스트·전달문·보드·발행문에 티저를 쓰지 않는다. 과거 페이퍼 기록(4주 3-0 · 소급 10-7)은 picks.csv 에 남지만 적립을 멈췄다. 맞대결·📊 스탯 비교(말로 — 값+32팀 순위+상위/중간/하위, 발행문이 그대로 옮김)·팀 비교·키커·심판·순위·흐름 블록(🤝🏟️🦵🧑‍⚖️)은 **값만** · **스프레드 「몇 점 차면 커버」 류 설명은 발행문에 쓰지 않는다(10/10 Paul 「쓸데없는 정보」)** · — 백테스트에서 시장을 이긴 적이 없다(리턴매치 51.5% · 작년 성적 50.3% · 일정 15항목 잡음).",
]


def ph_digest(week, force=False):
    wd = week_dir(week)
    games = rd(os.path.join(wd, "games.csv"))
    model = {r["game_id"]: r for r in rd(os.path.join(wd, "model.csv"))}
    inj = {r["team"]: r for r in rd(os.path.join(wd, "injuries.csv"))}
    rt = {r["team"]: r for r in rd(os.path.join(DATA, "ratings.csv"))}
    P26, P25, FTN = _press_by_team(SEASON), _press_by_team(SEASON - 1), _ftn_by_team()
    PRO = _team_profile()
    RS = _real_stats()
    NAMES = _espn_names(wd)
    try:
        import predictions as PR
        PRED = {k: v[1] for k, v in PR.compute(week).items()}
    except Exception as e:
        log(f"  예측 계산 실패: {type(e).__name__}")
        PRED = {}
    now = datetime.now()
    L = [f"# NFL {SEASON} Week {week} — 주간 다이제스트 (생성 {now:%m-%d %H:%M} PT · ESPN DraftKings 라인 · nflverse EPA)", ""]
    L += ["## 운용 규칙(N)", ""] + [f"- {r}" for r in RULES] + [""]
    import context_blocks as CB
    import stat_compare as SC
    L += CB.collection_check(week, games, inj, rt, wd)
    prev_state = CB.load_state(week); prev_stamp = prev_state.pop("_stamp", "?"); new_state = {}
    # 서열표 — |엣지| 큰 순
    L += ["## 🏁 서열표 — 스프레드 엣지 순(모델 − 시장, 홈 기준 점)", "",
          "| # | 경기 | 킥오프 ET(PT) | 시장 스프레드(홈) | 모델 마진(홈) | 엣지 | 스프레드 판정 | 시장 총점 | 모델 총점 | 엣지 | 총점 판정 | ※ |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    order = sorted(games, key=lambda g: -abs(fnum(model.get(g["game_id"] or g["espn_id"], {}).get("edge_spread")) or 0))
    for i, g in enumerate(order, 1):
        m = model.get(g["game_id"] or g["espn_id"], {})
        L.append(f'| {i} | {g["away"]}@{g["home"]} | {g["kickoff_et"]} ({g["kickoff_pt"]} PT) | {m.get("mkt_spread_home", "")} | {m.get("model_margin_home", "")} | '
                 f'{m.get("edge_spread", "")} | {m.get("spread_side", "")} · {m.get("spread_grade", "")} | {m.get("mkt_total", "")} | {m.get("model_total", "")} | '
                 f'{m.get("edge_total", "")} | {m.get("total_side", "")} · {m.get("total_grade", "")} | {m.get("thin", "")} |')
    L.append("")
    # 레이팅 표
    L += ["## 📊 팀 레이팅(EPA/플레이 · 공격 높을수록 좋음 / 수비 낮을수록 좋음 · 순마진/경기)", "",
          "| 팀 | 공격 | 패스 | 러시 | 수비 | 패스 | 러시 | 순마진 | 2026 플레이 | PF/PA |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rt.values(), key=lambda r: -fnum(r["net_pts_per_game"])):
        L.append(f'| {r["team"]} | {fnum(r["off"]):+.3f} | {fnum(r["off_pass"]):+.3f} | {fnum(r["off_rush"]):+.3f} | {fnum(r["def"]):+.3f} | {fnum(r["def_pass"]):+.3f} | {fnum(r["def_rush"]):+.3f} | {fnum(r["net_pts_per_game"]):+.1f} | {r[f"off_plays_{SEASON}"]} | {r["pf_pg"]}/{r["pa_pg"]} |')
    L.append("")
    # 경기별
    for g in order:
        a, h = g["away"], g["home"]
        m = model.get(g["game_id"] or g["espn_id"], {})
        L += [f'## {a}@{h}  {g["kickoff_et"]} ET ({g["kickoff_pt"]} PT) · {g["venue"]} · {g["roof"] or "?"} · {a} {g["away_rec"]} / {h} {g["home_rec"]}'
              + (" · 디비전" if g.get("div_game") == "1" else "") + (" · **중립 구장(홈 이점 0)**" if g.get("neutral") == "1" else ""), "",
              f'- 팀: **{NAMES.get(a, a)}**({TEAM_KR.get(a, a)}) @ **{NAMES.get(h, h)}**({TEAM_KR.get(h, h)}) · 로고는 보드(Artifact)에서']
        L += _predict_line(a, h, PRED.get(f"{a}@{h}"))
        cur = CB.snapshot(g, m, inj); ch = CB.changes_line(prev_state.get(f"{a}@{h}"), cur, prev_stamp)
        if ch: L.append(ch)
        new_state[f"{a}@{h}"] = cur
        if L[-1] != "": L.append("")
        L.append(f'- 시장({g["odds_provider"] or "DK"}): 스프레드 홈 {m.get("mkt_spread_home", "?")} · 총점 {m.get("mkt_total", "?")} · ML {a} {g["ml_away"] or "?"} / {h} {g["ml_home"] or "?"}'
                 + (f' · nflverse 라인 {g["nv_spread_line"]}/{g["nv_total_line"]}' if g["nv_spread_line"] else ""))
        L += _price_block(a, h, g, [x for x in rd(os.path.join(wd, "line_history.csv")) if x["game"] == f"{a}@{h}"])
        ra, rh = rt.get(a, {}), rt.get(h, {})
        L.append(f'- 레이팅: {a} 공격 {fnum(ra.get("off", 0)):+.3f}(패 {fnum(ra.get("off_pass", 0)):+.3f}/러 {fnum(ra.get("off_rush", 0)):+.3f}) · 수비 {fnum(ra.get("def", 0)):+.3f}(패 {fnum(ra.get("def_pass", 0)):+.3f}/러 {fnum(ra.get("def_rush", 0)):+.3f}) · 순마진 {fnum(ra.get("net_pts_per_game", 0)):+.1f} · PF/PA {ra.get("pf_pg")}/{ra.get("pa_pg")}')
        L.append(f'- 레이팅: {h} 공격 {fnum(rh.get("off", 0)):+.3f}(패 {fnum(rh.get("off_pass", 0)):+.3f}/러 {fnum(rh.get("off_rush", 0)):+.3f}) · 수비 {fnum(rh.get("def", 0)):+.3f}(패 {fnum(rh.get("def_pass", 0)):+.3f}/러 {fnum(rh.get("def_rush", 0)):+.3f}) · 순마진 {fnum(rh.get("net_pts_per_game", 0)):+.1f} · PF/PA {rh.get("pf_pg")}/{rh.get("pa_pg")}')
        L.append(f'- 모델: 홈 마진 {m.get("model_margin_home", "?")} · 홈 승률 {m.get("p_home_win", "?")}% · 총점 {m.get("model_total", "?")}'
                 + (f' · QB 조정 {a} {m.get("qb_adj_away")} / {h} {m.get("qb_adj_home")}' if (fnum(m.get("qb_adj_away")) or fnum(m.get("qb_adj_home"))) else ""))
        L.append(f'- **스프레드**: 엣지 {m.get("edge_spread", "?")}점 → {m.get("spread_side", "—")} · **{m.get("spread_grade", "?")}** · 커버 확률 {m.get("p_cover", "?")}%')
        L.append(f'- **총점**: 엣지 {m.get("edge_total", "?")}점 → {m.get("total_side", "—")} · **{m.get("total_grade", "?")}** · 확률 {m.get("p_total", "?")}%')
        ia, ih = inj.get(a, {}), inj.get(h, {})
        for t, x in ((a, ia), (h, ih)):
            L.append(f'- 부상·QB {t}: 예상 QB {x.get("expected_qb") or "?"}(시즌 주전 {x.get("season_main_qb") or "?"})'
                     + (f' ⚠️ {x["qb_flag"]}' if x.get("qb_flag") else "") + (f' · ⓘ {x["qb_note"]}' if x.get("qb_note") else "")
                     + (f' · ⚠️ 최종 지정 미발표 — 연습 보고 DNP {x.get("n_dnp", 0)}' + (f'({x["dnp"]})' if x.get("dnp") else "")
                        + f' · Limited {x.get("n_limited", 0)}' + (f'({x["limited"]})' if x.get("limited") else "") + ' — 발행 세션 웹 확인 필수'
                        if x.get("final_pending") else
                        f' · Out {x.get("n_out", 0)} / Doubtful {x.get("n_doubtful", 0)} / Questionable {x.get("n_questionable", 0)}')
                     + (f' — Out: {x["out"]}' if x.get("out") else "") + (f' — Doubtful: {x["doubtful"]}' if x.get("doubtful") else "")
                     + (f' — Questionable: {x["questionable"]}' if x.get("questionable") else "")
                     + (f' · ★주전급(스냅 60%+) {"Out/Doubtful" if not x.get("final_pending") else "연습 불참"} {x["n_starters_missing"]}명'
                        if str(x.get("n_starters_missing") or "0") not in ("0", "") else "")
                     + (f' (보고 {x.get("report_week")}주차)' if x.get("report_week") and str(x.get("report_week")) != str(week) else ""))
        L += SC.build(a, h, RS, PRO, rt, inj, g)   # 📊 스탯 비교(말로) — 2026-10-10 Paul 「숫자만 있어 이해 어려움」
        L += CB.h2h_block(a, h) + CB.team_compare_block(a, h, rt) + CB.kicker_block(a, h, g) + CB.referee_block(g)
        L += _balance_table(a, h, g, RS, inj, P26, PRO)
        L += _real_stats_block(a, h, RS, inj, g, m)
        L += _matchup_table(a, h, PRO, P26, inj)
        for o_, d_, x in ((a, h, ia), (h, a, ih)):
            L.append(_pass_matchup_lines(o_, d_, x.get("expected_qb"), P26, P25, FTN))
        hist = [x for x in rd(os.path.join(wd, "line_history.csv")) if x["game"] == f"{a}@{h}"]
        if len(hist) >= 2 and (hist[0]["spread_home"] != hist[-1]["spread_home"] or hist[0]["total"] != hist[-1]["total"]):
            L.append(f'- 라인 이동: 스프레드(홈) {hist[0]["spread_home"]} → {hist[-1]["spread_home"]} · 총점 {hist[0]["total"]} → {hist[-1]["total"]} ({hist[0]["pulled_at"]} → {hist[-1]["pulled_at"]}) — 정보(뉴스 반영), 방향 근거 아님')
        wx = f'{g["weather"]} {g["temp_f"]}°F' if g["weather"] else "예보 없음"
        L.append(f'- 맥락(값만 — N5): 휴식 {a} {g["away_rest"] or "?"}일 / {h} {g["home_rest"] or "?"}일 · 날씨 {wx} · 지붕 {g["roof"] or "?"}'
                 + (" · ⚠️ 목요일 경기(짧은 휴식)" if any(str(x) == "4" for x in (g["away_rest"], g["home_rest"])) else ""))
        risks = []
        if ia.get("qb_flag"): risks.append(f'{a} {ia["qb_flag"]} → 모델 −{QB_ADJ}점')
        if ih.get("qb_flag"): risks.append(f'{h} {ih["qb_flag"]} → 모델 −{QB_ADJ}점')
        for t, x in ((a, ia), (h, ih)):
            if x.get("qb_note"): risks.append(f'{t} {x["qb_note"]}')
        if g.get("neutral") == "1": risks.append("중립 구장 — 홈 이점 0")
        if m.get("thin"): risks.append(f'※ 값 얇음 {m.get("thin_teams")} — 후보 제외')
        if g["roof"] in ("outdoors", "open", "") and re.search(r"rain|snow|storm|shower", g["weather"], re.I): risks.append(f'실외 강수 예보({g["weather"]}) — 총점 쪽 참고')
        L.append("- 리스크: " + (" · ".join(risks) if risks else "자동 항목 없음") + " · 〔직접 서술 — 값만, 단정 금지〕")
        L.append("")
    out = os.path.join(wd, "DIGEST.md")
    txt = "\n".join(L)
    open(out + ".tmp", "w", encoding="utf-8").write(txt); os.replace(out + ".tmp", out)
    snap = os.path.join(wd, f"DIGEST-{now:%m%d-%H%M}.md")
    open(snap, "w", encoding="utf-8").write(txt)
    new_state["_stamp"] = f"{now:%m-%d %H:%M}"; CB.save_state(week, new_state)   # 🆕 직전 판 변동용(2026-10-10)
    log(f"  wrote {os.path.relpath(out, ROOT)} ({len(L)} lines) + 스냅샷 {os.path.basename(snap)}")


def ph_results(week, force=False):
    """ESPN 최종 점수 → data/2026-wNN/results.csv (picks.py grade 가 읽는다)"""
    wd = week_dir(week)
    fetch(f"{ESPN}?week={week}&seasontype=2&dates={SEASON}", os.path.join(wd, "espn_scoreboard.json"), 0, True)
    j = json.load(open(os.path.join(wd, "espn_scoreboard.json"), encoding="utf-8"))
    rows = []
    for ev in j.get("events", []):
        c = ev["competitions"][0]
        d = {t["homeAway"]: (ESPN2NV.get(t["team"]["abbreviation"], t["team"]["abbreviation"]), t.get("score")) for t in c["competitors"]}
        rows.append([ev["id"], d["away"][0], d["home"][0], ev["status"]["type"]["name"], d["away"][1], d["home"][1]])
    wcsv(os.path.join(wd, "results.csv"), ["espn_id", "away", "home", "status", "away_score", "home_score"], rows)
    # 마감 라인·배당(2026-10-04 — CLV 용): 끝난 경기만, 경기당 1콜(캐시 — 끝난 경기의 마감은 바뀌지 않는다)
    crow = []
    for r in rows:
        if r[3] != "STATUS_FINAL":
            continue
        sp = os.path.join(wd, f"summary_{r[0]}.json")
        if not os.path.exists(sp):
            fetch(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={r[0]}", sp, 24 * 365)
        try:
            pc = (json.load(open(sp, encoding="utf-8")).get("pickcenter") or [{}])[0]
        except Exception:
            continue
        px = _espn_prices(pc)
        crow.append([r[0], f"{r[1]}@{r[2]}", px["sp_home_line"], px["sp_home_odds"], px["sp_away_odds"], px["total_line"], px["over_odds"], px["under_odds"],
                     px["ml_away"], px["ml_home"]])
    wcsv(os.path.join(wd, "closing.csv"), ["espn_id", "game", "spread_home", "sp_home_odds", "sp_away_odds", "total", "over_odds", "under_odds",
                                           "ml_away", "ml_home"], crow)


PHASES = [("sources", ph_sources), ("ratings", ph_ratings), ("slate", ph_slate), ("injuries", ph_injuries), ("model", ph_model), ("digest", ph_digest)]


def current_week():
    try:
        j = json.load(urllib.request.urlopen(ESPN, timeout=20))
        return int(j["week"]["number"])
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=None, help="주차(기본: ESPN 현재 주차)")
    ap.add_argument("--phase", default=None, help="한 단계만(sources/ratings/slate/injuries/model/digest/results)")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    week = a.week or current_week()
    if not week:
        sys.exit("주차를 알 수 없다 — --week 로 지정")
    log(f"NFL {SEASON} week {week}")
    if a.phase == "results":
        ph_results(week, a.force); return
    for name, fn in PHASES:
        if a.phase and a.phase != name:
            continue
        log(f"[{name}]"); fn(week, a.force)
    log(f"DONE -> {week_dir(week)}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
