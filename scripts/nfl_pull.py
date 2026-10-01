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
                     ev["status"]["type"]["name"], as_, hs])
    hdr = ["espn_id", "game_id", "kickoff_utc", "kickoff_et", "kickoff_pt", "away", "home", "away_rec", "home_rec", "venue", "roof", "neutral",
           "weather", "temp_f", "spread_home", "total", "ml_away", "ml_home", "odds_provider", "nv_spread_line", "nv_total_line",
           "away_rest", "home_rest", "away_qb", "home_qb", "div_game", "status", "away_score", "home_score"]
    wcsv(os.path.join(wd, "games.csv"), hdr, rows)
    # 라인 이동 기록(정보 — 뉴스가 라인에 먼저 반영된다): 리프레시마다 한 줄씩 누적
    lh = os.path.join(wd, "line_history.csv")
    new = not os.path.exists(lh)
    with open(lh, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["pulled_at", "game", "spread_home", "total", "ml_away", "ml_home"])
        ts = datetime.now().strftime("%m-%d %H:%M")
        for r in rows:
            w.writerow([ts, f"{r[5]}@{r[6]}", r[14], r[15], r[16], r[17]])


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
    rows = []
    for t in teams:
        out = [f'{r["full_name"]}({r["position"]})' for r in by[t] if r["report_status"] == "Out"]
        dbt = [f'{r["full_name"]}({r["position"]})' for r in by[t] if r["report_status"] == "Doubtful"]
        q = [f'{r["full_name"]}({r["position"]})' for r in by[t] if r["report_status"] == "Questionable"]
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
        dnp = [f'{r["full_name"]}({r["position"]})' for r in prac[t] if r["practice_status"].startswith("Did Not")]
        lim = [f'{r["full_name"]}({r["position"]})' for r in prac[t] if r["practice_status"].startswith("Limited")]
        qb_prac = next((f'{r["full_name"]} {"DNP" if r["practice_status"].startswith("Did Not") else "Limited"}' for r in prac[t]
                        if r["position"] == "QB" and r["practice_status"].startswith(("Did Not", "Limited"))), "")
        if pending and qb_prac:
            note = (note + " · " if note else "") + f"QB 연습 {qb_prac}(최종 지정 미발표 — 잠정)"
        rows.append([t, use or "", exp, d1, main_qb.get(t, ""), qb_rep, flag, note, len(out), len(dbt), len(q),
                     " · ".join(out), " · ".join(dbt), " · ".join(q), pending, len(dnp), len(lim), " · ".join(dnp), " · ".join(lim)])
    wcsv(os.path.join(wd, "injuries.csv"), ["team", "report_week", "expected_qb", "depth_qb1", "season_main_qb", "qb_report", "qb_flag", "qb_note",
                                             "n_out", "n_doubtful", "n_questionable", "out", "doubtful", "questionable",
                                             "final_pending", "n_dnp", "n_limited", "dnp", "limited"], rows)


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
    "N10. **발행은 claude.ai NFL 발행 세션이 한다(2026-09-29 Paul)** — 이 다이제스트를 붙여넣으면 경기별 발행문(판단·방향·시장·뉴스 확인(웹)·매치업·맥락·모델(참고)·반대 근거·이유)을 쓰고 「판단: 패스/소액 관심/관심」(돈을 거느냐)과 **「방향: 스프레드 쪽 · 총점 쪽」(패스여도 필수 — 2026-10-01 Paul 「결정 없이 서술만」)** 을 낸다. 로컬은 check_nfl.py 로 숫자·형식을 대조하고 판단(관심(발행))·방향(방향(발행))을 따로 페이퍼로 기록한다. 발행 세션의 몫은 **최신 뉴스(QB 확정·새 부상·라인 이동) 확인** — 다이제스트 부상 보고는 전 주차 것일 수 있다.",
]


def ph_digest(week, force=False):
    wd = week_dir(week)
    games = rd(os.path.join(wd, "games.csv"))
    model = {r["game_id"]: r for r in rd(os.path.join(wd, "model.csv"))}
    inj = {r["team"]: r for r in rd(os.path.join(wd, "injuries.csv"))}
    rt = {r["team"]: r for r in rd(os.path.join(DATA, "ratings.csv"))}
    now = datetime.now()
    L = [f"# NFL {SEASON} Week {week} — 주간 다이제스트 (생성 {now:%m-%d %H:%M} PT · ESPN DraftKings 라인 · nflverse EPA)", ""]
    L += ["## 운용 규칙(N)", ""] + [f"- {r}" for r in RULES] + [""]
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
              + (" · 디비전" if g.get("div_game") == "1" else "") + (" · **중립 구장(홈 이점 0)**" if g.get("neutral") == "1" else ""), ""]
        L.append(f'- 시장({g["odds_provider"] or "DK"}): 스프레드 홈 {m.get("mkt_spread_home", "?")} · 총점 {m.get("mkt_total", "?")} · ML {a} {g["ml_away"] or "?"} / {h} {g["ml_home"] or "?"}'
                 + (f' · nflverse 라인 {g["nv_spread_line"]}/{g["nv_total_line"]}' if g["nv_spread_line"] else ""))
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
                     + (f' (보고 {x.get("report_week")}주차)' if x.get("report_week") and str(x.get("report_week")) != str(week) else ""))
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
