"""경기 맥락 블록(2026-10-10 Paul 요청 2~6 · 전부 서술 전용 — 점수·등급·별점에 넣지 않는다).
  🤝 맞대결(최근 3시즌 전 경기 · 장소·점수·ATS·O/U)   — Paul 「팀대결 무조건 넣기 — 최근 3년 h2h 매치업 장소 등등」
  🏟️ 팀 비교(전적·홈/원정·ATS·O/U·PF/PA·EPA 순위·디비전/컨퍼런스 순위·최근 5경기 흐름)   — Paul 「팀 비교」 + MLB 「순위 맥락·팀 흐름」
  🦵 키커(예상 키커 · 2024~26 FG 거리별 성공률 · XP · 최장)   — Paul 「킥커 스코어 확률」
  🧑‍⚖️ 심판 크루(배정되면 2024~26 경기당 페널티·총점·홈 커버)   — MLB 「구심」에 해당
  🆕 직전 판 변동(라인·ML·Out·예상 QB)   — MLB 「🆕 직전 판」
  📋 수집 점검(다이제스트 머리)   — MLB 「📋 수집 점검」
근거: 작년 성적·리턴매치(2007~25 커버 50~51%, 우연 범위)·심판·키커는 백테스트에서 시장을 이긴 적이 없다 → 값만 적는다.
캐시: data/cache/kickers_YYYY.csv · referees_YYYY.csv (지난 시즌은 한 번만 계산, 올 시즌은 매번)."""
import json
import os
import re
from collections import defaultdict

import nfl_pull as N

DIV = {"BUF": "AFC 동부", "MIA": "AFC 동부", "NE": "AFC 동부", "NYJ": "AFC 동부",
       "BAL": "AFC 북부", "CIN": "AFC 북부", "CLE": "AFC 북부", "PIT": "AFC 북부",
       "HOU": "AFC 남부", "IND": "AFC 남부", "JAX": "AFC 남부", "TEN": "AFC 남부",
       "DEN": "AFC 서부", "KC": "AFC 서부", "LV": "AFC 서부", "LAC": "AFC 서부",
       "DAL": "NFC 동부", "NYG": "NFC 동부", "PHI": "NFC 동부", "WAS": "NFC 동부",
       "CHI": "NFC 북부", "DET": "NFC 북부", "GB": "NFC 북부", "MIN": "NFC 북부",
       "ATL": "NFC 남부", "CAR": "NFC 남부", "NO": "NFC 남부", "TB": "NFC 남부",
       "ARI": "NFC 서부", "LA": "NFC 서부", "SF": "NFC 서부", "SEA": "NFC 서부"}
H2H_SEASONS = 3          # 올 시즌 포함 앞 3시즌(2026 이면 2023~)
KICK_SEASONS = 3         # 2024~2026
FG_BANDS = ((0, 39), (40, 49), (50, 99))
_G = None


def games():
    global _G
    if _G is None:
        _G = N.rd(os.path.join(N.CACHE, "games.csv"))
    return _G


def _f(x):
    return N.fnum(x)


def _ats(x, team):
    """팀 기준 ATS 결과(W/L/P/None) — nflverse spread_line = 홈이 이만큼 유리(양수면 홈 페이버릿), result = 홈 − 원정."""
    r, s = _f(x.get("result")), _f(x.get("spread_line"))
    if r is None or s is None:
        return None
    d = (r - s) if team == x["home_team"] else (s - r)
    return "P" if d == 0 else "W" if d > 0 else "L"


def _ou(x):
    t, l = _f(x.get("total")), _f(x.get("total_line"))
    if t is None or l is None:
        return None
    return "P" if t == l else "O" if t > l else "U"


def _wl(xs, team):
    w = l = t = 0
    for x in xs:
        r = _f(x.get("result"))
        if r is None:
            continue
        mine = r if team == x["home_team"] else -r
        if mine > 0: w += 1
        elif mine < 0: l += 1
        else: t += 1
    return w, l, t


def _rec_str(w, l, t=0):
    return f"{w}-{l}" + (f"-{t}" if t else "")


def _cnt(vals, keys):
    return "-".join(str(sum(1 for v in vals if v == k)) for k in keys)


# ───────────────────────── 🤝 맞대결 ─────────────────────────
def h2h_block(a, h):
    rows = [x for x in games() if {x["away_team"], x["home_team"]} == {a, h} and x.get("result") not in ("", None)
            and int(x["season"]) >= N.SEASON - H2H_SEASONS]
    rows.sort(key=lambda x: (x["season"], int(x["week"])))
    hdr = [f"- 🤝 **맞대결(최근 {H2H_SEASONS}시즌 {N.SEASON - H2H_SEASONS}~ · 플레이오프 포함 · 값만 — 2006~25 직전 맞대결 진 팀 리턴매치 커버 51.5%, 우연 범위)**:"]
    if not rows:
        return hdr + [f"  ↳ {N.SEASON - H2H_SEASONS}~{N.SEASON - 1} 맞대결 없음", ""]
    wa, wl_, _ = _wl(rows, a)
    here = [x for x in rows if x["home_team"] == h]
    ha, hl_, _ = _wl(here, a)
    ats_a = [_ats(x, a) for x in rows]; ou = [_ou(x) for x in rows]
    margins = [(_f(x["result"]) if x["home_team"] == h else -_f(x["result"])) for x in rows]   # 홈(h) 기준 점수 차
    tots = [_f(x["total"]) for x in rows if _f(x["total"]) is not None]
    L = hdr + ["", f"| 시즌·주차 | 날짜 | 장소 | 점수(원정–홈) | 승자·점수 차 | 마감 스프레드(홈) → ATS | 총점 라인 → O/U |", "|---|---|---|---|---|---|---|"]
    for x in rows:
        r = _f(x["result"]); win = x["home_team"] if r > 0 else x["away_team"] if r < 0 else "무"
        wk = {"WC": "WC", "DIV": "DIV", "CON": "CONF", "SB": "SB"}.get(x["game_type"], f"{x['week']}주")
        s = _f(x["spread_line"]); tl = _f(x["total_line"])
        ats_h = _ats(x, x["home_team"]); ou_ = _ou(x)
        L.append(f"| {x['season']} {wk} | {x['gameday']} | {x['stadium'] or x['location']}({x['home_team']} 홈{' · ' + x['roof'] if x.get('roof') else ''}) | "
                 f"{x['away_team']} {_f(x['away_score']):g}–{_f(x['home_score']):g} {x['home_team']} | {win} {abs(r):g}점 | "
                 f"{'' if s is None else x['home_team'] + ' ' + format(-s, '+g')} → {('홈 커버' if ats_h == 'W' else '원정 커버' if ats_h == 'L' else '푸시') if ats_h else '—'} | "
                 f"{'' if tl is None else f'{tl:g}'} → {ou_ or '—'} |")
    L += ["", f"  ↳ 요약: 전적 {a} {_rec_str(wa, wl_)} {h}({len(rows)}경기) · {h} 홈에서 {a} {_rec_str(ha, hl_)} {h}({len(here)}경기) · "
          f"{a} ATS {_cnt(ats_a, 'WLP')} · O/U {_cnt(ou, 'OUP')} · 평균 점수 차 {h} {sum(margins) / len(margins):+.1f} · 평균 총점 {sum(tots) / len(tots):.1f}"
          + (f" · 최근 3경기 총점 {' · '.join(f'{t:g}' for t in tots[-3:])}" if tots else ""), ""]
    return L


# ───────────────────────── 🏟️ 팀 비교 ─────────────────────────
def standings():
    """2026 정규시즌 결과 → {team: dict(w,l,t,div_w,div_l,conf_w,conf_l,home,away,pf,pa,last5,streak,div_rank,conf_rank)} — 동률은 승률순(NFL 타이브레이크 미적용)."""
    rows = [x for x in games() if x["season"] == str(N.SEASON) and x["game_type"] == "REG" and x.get("result") not in ("", None)]
    rows.sort(key=lambda x: (int(x["week"]), x["gameday"]))
    S = defaultdict(lambda: dict(w=0, l=0, t=0, dw=0, dl=0, cw=0, cl=0, hw=0, hl=0, aw=0, al=0, pf=0, pa=0, g=[], ats=[], ou=[]))
    for x in rows:
        r = _f(x["result"]); hs, as_ = _f(x["home_score"]), _f(x["away_score"])
        for t, o, mine, pf, pa, home in ((x["home_team"], x["away_team"], r, hs, as_, True), (x["away_team"], x["home_team"], -r, as_, hs, False)):
            s = S[t]
            k = "w" if mine > 0 else "l" if mine < 0 else "t"
            s[k] += 1; s["pf"] += pf; s["pa"] += pa
            if DIV.get(t) == DIV.get(o): s["dw" if mine > 0 else "dl"] += (mine != 0)
            if DIV.get(t, "")[:3] == DIV.get(o, "")[:3]: s["cw" if mine > 0 else "cl"] += (mine != 0)
            if home: s["hw" if mine > 0 else "hl"] += (mine != 0)
            else: s["aw" if mine > 0 else "al"] += (mine != 0)
            s["g"].append((int(x["week"]), ("vs " if home else "@ ") + o, f"{pf:g}-{pa:g}", "W" if mine > 0 else "L" if mine < 0 else "T", _ats(x, t), _ou(x)))
            s["ats"].append(_ats(x, t)); s["ou"].append(_ou(x))
    def pct(s):
        n = s["w"] + s["l"] + s["t"]
        return (s["w"] + 0.5 * s["t"]) / n if n else 0
    for t in DIV:
        S[t]  # 결과 없는 팀도 행 생성
    for grp, key in (("div", DIV.get), ("conf", lambda t: DIV.get(t, "")[:3])):
        by = defaultdict(list)
        for t in DIV:
            by[key(t)].append(t)
        for members in by.values():
            order = sorted(members, key=lambda t: (-pct(S[t]), -(S[t]["pf"] - S[t]["pa"])))
            for i, t in enumerate(order, 1):
                S[t][grp + "_rank"] = i; S[t][grp + "_n"] = len(order)
    for t, s in S.items():
        st = ""
        for g in reversed(s["g"]):
            if not st: st = g[3]
            elif g[3] == st[0]: st += g[3]
            else: break
        s["streak"] = f"{st[0]}{len(st)}" if st else "—"
    return S


def team_compare_block(a, h, rt):
    S = standings()
    off_rank = {t: i for i, t in enumerate(sorted(rt, key=lambda t: -(_f(rt[t].get("off")) or 0)), 1)}
    def_rank = {t: i for i, t in enumerate(sorted(rt, key=lambda t: (_f(rt[t].get("def")) or 0)), 1)}       # 수비 EPA 낮을수록 좋음
    net_rank = {t: i for i, t in enumerate(sorted(rt, key=lambda t: -(_f(rt[t].get("net_pts_per_game")) or 0)), 1)}
    def row(t):
        s = S[t]; n = s["w"] + s["l"] + s["t"]
        return s, n
    sa, na = row(a); sh, nh = row(h)
    def flow(s):
        return " · ".join(f"{wk}주 {opp} {sc} {res}{'(ATS ' + ats + ')' if ats else ''}" for wk, opp, sc, res, ats, ou in s["g"][-5:]) or "—"
    rec, _done = N._prior_and_h2h(); py = N.SEASON - 1
    def prior(t):
        w, l = rec.get((py, t), [0, 0])
        return f"{py} 시즌 {w}-{l}" + (f"({w / (w + l):.3f})" if w + l else "")
    L = [f"- 🏟️ **팀 비교(값만 — 2026 정규시즌 · 순위는 32팀 중 · 동률은 승률순, NFL 타이브레이크 미적용)**:", "",
         f"| 항목 | {a} | {h} |", "|---|---|---|",
         f"| 작년 성적(2025) | {prior(a)} | {prior(h)} |",   # 10/10 발행 세션 제안 — 요약표 「2025 시즌」 열 원본(값만: 작년 승률 .25+ 차 커버 50.3%)
         f"| 전적(홈 / 원정) | {_rec_str(sa['w'], sa['l'], sa['t'])} (홈 {sa['hw']}-{sa['hl']} / 원정 {sa['aw']}-{sa['al']}) | {_rec_str(sh['w'], sh['l'], sh['t'])} (홈 {sh['hw']}-{sh['hl']} / 원정 {sh['aw']}-{sh['al']}) |",
         f"| 순위 맥락 | {DIV.get(a, '?')} {sa.get('div_rank', '?')}/{sa.get('div_n', 4)}위 · 컨퍼런스 {sa.get('conf_rank', '?')}/{sa.get('conf_n', 16)}위 · 디비전 {sa['dw']}-{sa['dl']} · 컨퍼런스 {sa['cw']}-{sa['cl']} | "
         f"{DIV.get(h, '?')} {sh.get('div_rank', '?')}/{sh.get('div_n', 4)}위 · 컨퍼런스 {sh.get('conf_rank', '?')}/{sh.get('conf_n', 16)}위 · 디비전 {sh['dw']}-{sh['dl']} · 컨퍼런스 {sh['cw']}-{sh['cl']} |",
         f"| ATS(마감 라인) / O·U | ATS {_cnt(sa['ats'], 'WLP')} · O/U {_cnt(sa['ou'], 'OUP')} | ATS {_cnt(sh['ats'], 'WLP')} · O/U {_cnt(sh['ou'], 'OUP')} |",
         f"| 득실(경기당) | {sa['pf'] / na if na else 0:.1f} / {sa['pa'] / na if na else 0:.1f} (차 {(sa['pf'] - sa['pa']) / na if na else 0:+.1f}) | {sh['pf'] / nh if nh else 0:.1f} / {sh['pa'] / nh if nh else 0:.1f} (차 {(sh['pf'] - sh['pa']) / nh if nh else 0:+.1f}) |",
         f"| EPA 순위(공격 / 수비 / 순마진) | {off_rank.get(a, '?')}위 / {def_rank.get(a, '?')}위 / {net_rank.get(a, '?')}위 | {off_rank.get(h, '?')}위 / {def_rank.get(h, '?')}위 / {net_rank.get(h, '?')}위 |",
         f"| 최근 5경기 흐름(연속 {sa['streak']}) | {flow(sa)} | — |",
         f"| 최근 5경기 흐름(연속 {sh['streak']}) | — | {flow(sh)} |",
         "", "  ↳ 순위·흐름은 서술 재료(2023~25 라인·일정 15항목 전부 잡음 — 「순위가 높으니 이긴다」로 쓰지 않는다). 시즌 막판엔 플레이오프 확정·탈락 여부를 발행 세션이 웹으로 확인한다.", ""]
    return L


# ───────────────────────── 🦵 키커 ─────────────────────────
def _kick_season(season):
    p = os.path.join(N.CACHE, f"kickers_{season}.csv")
    if season != N.SEASON and os.path.exists(p):
        return N.rd(p)
    src = os.path.join(N.CACHE, f"play_by_play_{season}.csv.gz")
    if not os.path.exists(src):
        return []
    K = defaultdict(lambda: defaultdict(int)); team = {}; longest = defaultdict(int)
    for r in N.rd(src):
        nm = r.get("kicker_player_name")
        if not nm:
            continue
        fg, xp = r.get("field_goal_result"), r.get("extra_point_result")
        if fg:
            d = _f(r.get("kick_distance")) or 0
            band = next(i for i, (lo, hi) in enumerate(FG_BANDS) if lo <= d <= hi)
            K[nm][f"fg{band}_att"] += 1
            if fg == "made":
                K[nm][f"fg{band}_made"] += 1; longest[nm] = max(longest[nm], int(d))
            elif fg == "blocked":
                K[nm]["blocked"] += 1
            team[nm] = r.get("posteam") or team.get(nm, "")
        elif xp:
            K[nm]["xp_att"] += 1; K[nm]["xp_made"] += (xp == "good")
            team[nm] = r.get("posteam") or team.get(nm, "")
    hdr = ["season", "kicker", "team", "fg0_att", "fg0_made", "fg1_att", "fg1_made", "fg2_att", "fg2_made", "xp_att", "xp_made", "blocked", "longest"]
    rows = [[season, nm, team.get(nm, ""), K[nm]["fg0_att"], K[nm]["fg0_made"], K[nm]["fg1_att"], K[nm]["fg1_made"], K[nm]["fg2_att"], K[nm]["fg2_made"],
             K[nm]["xp_att"], K[nm]["xp_made"], K[nm]["blocked"], longest[nm]] for nm in K]
    if season != N.SEASON:
        N.wcsv(p, hdr, rows)
    return [dict(zip(hdr, map(str, r))) for r in rows]


_KICK = None


def kicker_stats():
    global _KICK
    if _KICK is None:
        _KICK = [r for s in range(N.SEASON - KICK_SEASONS + 1, N.SEASON + 1) for r in _kick_season(s)]
    return _KICK


def _depth_kicker():
    """뎁스차트 최신 날짜의 K 1순위 → {team: 이름}."""
    best = {}
    for r in N.rd(os.path.join(N.CACHE, f"depth_charts_{N.SEASON}.csv")):
        if r.get("pos_abb") in ("PK", "K") and r.get("pos_rank") in ("1", "1.0"):
            if r["team"] not in best or r["dt"] > best[r["team"]][0]:
                best[r["team"]] = (r["dt"], r["player_name"])
    return {t: v[1] for t, v in best.items()}


def kicker_block(a, h, g):
    DK = _depth_kicker(); KS = kicker_stats()
    L = ["- 🦵 **키커(값만 — 예상 키커 = 뎁스차트 PK 1순위 · 성공률은 2024~26 정규+플레이오프 실측 · 「스코어 확률」 = 그 거리에서 킥이 들어갈 확률 · 점수 아님)**:", "",
         f"| 항목 | {a} | {h} |", "|---|---|---|"]
    cells = {}
    for t in (a, h):
        nm = DK.get(t, "")
        mine = [r for r in KS if nm and N._same_person(r["kicker"], nm)]
        if not mine:
            cells[t] = (nm or "뎁스차트 없음", "—", "—", "—", "—")
            continue
        def agg(rows, key):
            return sum(int(r[key]) for r in rows)
        this = [r for r in mine if r["season"] == str(N.SEASON)]
        def band_txt(rows, i):
            at, md = agg(rows, f"fg{i}_att"), agg(rows, f"fg{i}_made")
            return f"{md}/{at} {100 * md / at:.0f}%" if at else "0/0 —"
        xa, xm = agg(mine, "xp_att"), agg(mine, "xp_made")
        fg_all = sum(agg(mine, f"fg{i}_att") for i in range(3)); fg_made = sum(agg(mine, f"fg{i}_made") for i in range(3))
        this_txt = (f"{sum(agg(this, f'fg{i}_made') for i in range(3))}/{sum(agg(this, f'fg{i}_att') for i in range(3))} · 50+ {band_txt(this, 2)}" if this else "2026 킥 없음")
        cells[t] = (nm, f"{fg_made}/{fg_all} {100 * fg_made / fg_all:.0f}%" if fg_all else "—",
                    " · ".join(f"{FG_BANDS[i][0]}~{FG_BANDS[i][1] if i < 2 else ''}{'+' if i == 2 else ''}야드 {band_txt(mine, i)}" for i in range(3)),
                    f"{xm}/{xa} {100 * xm / xa:.0f}%" if xa else "—",
                    f"최장 {max(int(r['longest']) for r in mine)}야드 · 블록 {agg(mine, 'blocked')} · 2026 {this_txt}")
    labels = ("예상 키커", "FG 전체(2024~26)", "거리별 스코어 확률", "XP", "최장·블록·올해")
    for i, lab in enumerate(labels):
        L.append(f"| {lab} | {cells[a][i]} | {cells[h][i]} |")
    env = f"{g.get('roof') or '?'}" + (f" · {g.get('weather')}" if g.get("weather") else "")
    L += ["", f"  ↳ 이 경기 조건: {env} — 실외 강풍·추위면 40야드 밖 성공률이 평균보다 떨어진다(값만, 총점·키 넘버 3 서술 재료). 키커 교체(부상·영입)는 발행 세션이 웹 확인.", ""]
    return L


# ───────────────────────── 🧑‍⚖️ 심판 ─────────────────────────
def _ref_season(season):
    p = os.path.join(N.CACHE, f"referees_{season}.csv")
    if season != N.SEASON and os.path.exists(p):
        return N.rd(p)
    src = os.path.join(N.CACHE, f"play_by_play_{season}.csv.gz")
    if not os.path.exists(src):
        return []
    pen = defaultdict(lambda: [0, 0.0])
    for r in N.rd(src):
        if r.get("penalty") in ("1", "1.0"):
            pen[r["game_id"]][0] += 1; pen[r["game_id"]][1] += _f(r.get("penalty_yards")) or 0
    R = defaultdict(lambda: dict(g=0, pen=0, yds=0.0, tot=0.0, hw=0, hcov=0, over=0, dec_ats=0, dec_ou=0))
    for x in games():
        if x["season"] != str(season) or not x.get("referee") or x.get("result") in ("", None):
            continue
        s = R[x["referee"]]; s["g"] += 1; s["pen"] += pen[x["game_id"]][0]; s["yds"] += pen[x["game_id"]][1]; s["tot"] += _f(x["total"]) or 0
        s["hw"] += _f(x["result"]) > 0
        at = _ats(x, x["home_team"]); ou = _ou(x)
        if at in ("W", "L"): s["dec_ats"] += 1; s["hcov"] += at == "W"
        if ou in ("O", "U"): s["dec_ou"] += 1; s["over"] += ou == "O"
    hdr = ["season", "referee", "g", "pen", "yds", "tot", "hw", "hcov", "dec_ats", "over", "dec_ou"]
    rows = [[season, nm, s["g"], s["pen"], round(s["yds"], 1), round(s["tot"], 1), s["hw"], s["hcov"], s["dec_ats"], s["over"], s["dec_ou"]] for nm, s in R.items()]
    if season != N.SEASON:
        N.wcsv(p, hdr, rows)
    return [dict(zip(hdr, map(str, r))) for r in rows]


_REF = None


def referee_block(g):
    global _REF
    gid = g.get("game_id") or ""
    x = next((y for y in games() if y["game_id"] == gid), None)
    ref = (x or {}).get("referee") or ""
    if not ref:
        return ["- 🧑‍⚖️ 심판 크루: nflverse 미배정(배정되면 자동 표시 — 보통 경기 주 후반) · 발행 세션이 웹으로 확인하면 「보도」 라벨", ""]
    if _REF is None:
        _REF = [r for s in range(N.SEASON - KICK_SEASONS + 1, N.SEASON + 1) for r in _ref_season(s)]
    mine = [r for r in _REF if r["referee"] == ref]
    if not mine:
        return [f"- 🧑‍⚖️ 심판 크루: {ref} — 2024~26 기록 없음(신임 심판)", ""]
    G = sum(int(r["g"]) for r in mine); pen = sum(int(r["pen"]) for r in mine); yds = sum(float(r["yds"]) for r in mine); tot = sum(float(r["tot"]) for r in mine)
    hw = sum(int(r["hw"]) for r in mine); hc = sum(int(r["hcov"]) for r in mine); da = sum(int(r["dec_ats"]) for r in mine); ov = sum(int(r["over"]) for r in mine); do = sum(int(r["dec_ou"]) for r in mine)
    lg_rows = _REF
    lg_g = sum(int(r["g"]) for r in lg_rows); lg_pen = sum(int(r["pen"]) for r in lg_rows) / max(lg_g, 1); lg_tot = sum(float(r["tot"]) for r in lg_rows) / max(lg_g, 1)
    return [f"- 🧑‍⚖️ 심판 크루(값만 — 2024~26 {G}경기): {ref} · 경기당 페널티 {pen / G:.1f}개 {yds / G:.0f}야드(리그 평균 {lg_pen:.1f}개) · 평균 총점 {tot / G:.1f}(리그 {lg_tot:.1f}) · "
            f"홈 승 {100 * hw / G:.0f}% · 홈 커버 {100 * hc / da if da else 0:.0f}%(n{da}) · Over {100 * ov / do if do else 0:.0f}%(n{do}) — 심판별 차이는 표본이 작아 우연 범위, 총점·페널티 서술 재료만", ""]


# ───────────────────────── 🆕 직전 판 변동 ─────────────────────────
def _state_path(week):
    return os.path.join(N.week_dir(week), "digest_state.json")


def load_state(week):
    p = _state_path(week)
    try:
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    except Exception:
        return {}


def save_state(week, state):
    p = _state_path(week)
    open(p + ".tmp", "w", encoding="utf-8").write(json.dumps(state, ensure_ascii=False, indent=0)); os.replace(p + ".tmp", p)


def snapshot(g, m, inj):
    a, h = g["away"], g["home"]
    def outs(t):
        x = inj.get(t) or {}
        return sorted(n.split("(")[0].strip() for n in str(x.get("out") or "").split(" · ") if n.strip())
    return {"spread_home": m.get("mkt_spread_home", ""), "total": m.get("mkt_total", ""), "ml": f'{g.get("ml_away") or "?"}/{g.get("ml_home") or "?"}',
            "qb": {t: (inj.get(t) or {}).get("expected_qb") or "?" for t in (a, h)}, "out": {t: outs(t) for t in (a, h)}}


def changes_line(prev, cur, stamp):
    """직전 판(stamp)과 비교해 바뀐 것만 한 줄. 첫 판이면 None."""
    if not prev:
        return None
    d = []
    if prev.get("spread_home") != cur.get("spread_home"): d.append(f"스프레드(홈) {prev.get('spread_home')} → {cur.get('spread_home')}")
    if prev.get("total") != cur.get("total"): d.append(f"총점 {prev.get('total')} → {cur.get('total')}")
    if prev.get("ml") != cur.get("ml"): d.append(f"ML {prev.get('ml')} → {cur.get('ml')}")
    for t, q in cur.get("qb", {}).items():
        if prev.get("qb", {}).get(t) not in (None, q): d.append(f"{t} 예상 QB {prev['qb'][t]} → {q}")
    for t, o in cur.get("out", {}).items():
        po = set(prev.get("out", {}).get(t, [])); no = set(o)
        if no - po: d.append(f"{t} Out 추가 {', '.join(sorted(no - po))}")
        if po - no: d.append(f"{t} Out 해제 {', '.join(sorted(po - no))}")
    return f"- 🆕 직전 판({stamp}) 대비 변동: " + (" · ".join(d) if d else "없음")


# ───────────────────────── 📋 수집 점검 ─────────────────────────
def collection_check(week, games_rows, inj, rt, wd):
    nv = [x for x in games() if x["season"] == str(N.SEASON) and x["week"] == str(week)]
    pbp_w = defaultdict(int)
    for r in N.rd(os.path.join(N.CACHE, f"play_by_play_{N.SEASON}.csv.gz")):
        pbp_w[r.get("week", "")] += 1
    snap_w = {r.get("week") for r in N.rd(os.path.join(N.CACHE, f"snap_counts_{N.SEASON}.csv"))}
    poly = len([f for f in os.listdir(wd) if f.startswith("poly_")]) if os.path.isdir(wd) else 0
    inj_final = sum(1 for t, x in inj.items() if not x.get("final_pending")); inj_pend = sum(1 for t, x in inj.items() if x.get("final_pending"))
    teams = {t for g in games_rows for t in (g["away"], g["home"])}
    kick = {r["team"] for r in kicker_stats() if r["season"] == str(N.SEASON)}
    def row(item, val, ok, note=""):
        return f"| {item} | {val} | {'✅' if ok else '⚠️'} | {note} |"
    L = ["## 📋 수집 점검(스크립트 자동 — ⚠️ 는 발행 전에 리프레시 또는 웹 확인)", "", "| 항목 | 값 | 상태 | 비고 |", "|---|---|---|---|",
         row("경기 수(ESPN vs nflverse 일정)", f"{len(games_rows)} / {len(nv)}", len(games_rows) == len(nv) and len(nv) > 0, "다르면 바이·연기 확인"),
         row("DK 스프레드·총점·ML", f"{sum(1 for g in games_rows if g.get('spread_home') and g.get('total') and g.get('ml_home'))}/{len(games_rows)}", all(g.get("spread_home") and g.get("total") and g.get("ml_home") for g in games_rows), "빈 경기는 💵 블록 결측"),
         row("Polymarket 가격 파일", f"{poly}/{len(games_rows)}", poly >= len(games_rows), "없으면 「더 좋은 가격」 비교 불가"),
         row("부상 보고(최종 지정 / 연습 보고만)", f"{inj_final} / {inj_pend} 팀(이번 주 {len(teams)}팀)", inj_final + inj_pend >= len(teams), "연습 보고만이면 Out/Q 웹 확인 필수"),
         row("pbp 최신 주차", f"{max((int(k) for k in pbp_w if k.isdigit()), default=0)}주(이번 {week}주)", max((int(k) for k in pbp_w if k.isdigit()), default=0) >= week - 1, "한 주 뒤면 레이팅·📈 가 지난주 값"),
         row("스냅 카운트 최신 주차", f"{max((int(k) for k in snap_w if k and k.isdigit()), default=0)}주", max((int(k) for k in snap_w if k and k.isdigit()), default=0) >= week - 1, "★주전 판정 기준"),
         row("팀 레이팅", f"{len(rt)}/32", len(rt) == 32, ""),
         row("날씨(ESPN)", f"{sum(1 for g in games_rows if g.get('weather'))}/{len(games_rows)}", True, "실내는 없어도 정상"),
         row("키커 2026 기록 팀 수", f"{len(kick)}/32", len(kick) >= 28, "0 이면 pbp 캐시 확인"),
         ""]
    return L
