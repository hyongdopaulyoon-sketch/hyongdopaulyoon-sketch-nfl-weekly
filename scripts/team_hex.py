"""team_hex.py — NFL 육각형 팀 비교(선수 위주 · 2026-11-15 Paul 「nfl 더 정교하게 비교하고 개선 · 보드에 육각형도 · 선수 위주로」 → 계획 1번 「이대로 가자」).
그 주에 실제로 뛰는 선수만으로 꼭짓점 6개를 만든다(결장·비활성·IR 은 빼고 다시 계산). 표시용 — 확률·★·판단을 바꾸지 않는다.
  python scripts/team_hex.py --backtest          # 2018~2025 꼭짓점별 승패·커버 관련 → data/hex_backtest_<오늘>.md + data/hex_baseline.json
  python scripts/team_hex.py --week 11           # 그 주 경기별 점수 → data/2026-wNN/hex.json(보드가 읽는다)
꼭짓점(재료 · 전부 그 경기 전까지의 값):
  QB        선발 QB 의 드롭백당 EPA(직전 시즌 + 올해 · 150 드롭백 수축)
  패스 무기   뛰는 리시버 타깃 상위 4명의 타깃당 EPA(타깃 가중 · 선수별 30 타깃 수축)
  러시       뛰는 러셔 캐리 상위 2명의 캐리당 EPA(캐리 가중 · 40 캐리 수축 · QB 제외)
  패스 보호   팀 드롭백당 색 허용률(낮을수록 좋음) + 최근 3경기 스냅 상위 공격 라인 5명 중 뛰는 수
  패스러시   뛰는 패스러셔 압박 상위 3명의 경기당 압박 합
  커버리지   뛰는 커버리지 선수 타깃 상위 4명의 타깃당 허용 야드(낮을수록 좋음 · 타깃 가중)
맞대결·결장 손실 검정(계획 2번 · 실행 전 고정 · 문턱 = 2개+ 시즌 50% 초과 & 전체 53%+ · 「그 팀 쪽」 승-패 · 47% 이하면 상대 쪽):
  X1 패스 미스매치: (QB + 패스 무기)/2 ≥ 70 & 상대 커버리지 ≤ 30 · X2 압박 미스매치: 패스러시 ≥ 70 & 상대 패스 보호 ≤ 30 · X3 여섯 중 5개+ 앞서는 팀 ·
  X4~X7 결장 손실(전원 가용 가정 − 실제 뛴 선수 점수) 15+ 인 팀: 패스 무기 · 패스 보호 · 패스러시 · 커버리지. 한 경기에 두 팀 다 해당이면 제외.
점수 = 기준 분포(2023~2025 팀-경기)에서의 백분위 0~100 · 50 = 리그 평균 · 재료 둘인 꼭짓점은 백분위 평균.
「뛰는 선수」: 역사 = 그 경기에 실제 기록이 있는 선수 · 실전 = 부상 보고 Out/Doubtful·IR·ESPN 명단 Out 이 아닌 선수.
"""
import argparse
import bisect
import csv
import datetime as dt
import html
import io
import json
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfl_pull as N  # noqa: E402

VERTS = ["QB", "패스 무기", "러시", "패스 보호", "패스러시", "커버리지"]
MATS = {"QB": [("qb", True)], "패스 무기": [("wr", True)], "러시": [("rb", True)], "패스 보호": [("sack", False), ("ol", True)],
        "패스러시": [("rush", True)], "커버리지": [("cov", False)]}
LAB = {"qb": "QB 드롭백당 EPA", "wr": "리시버 4명 타깃당 EPA", "rb": "러셔 2명 캐리당 EPA", "sack": "색 허용률", "ol": "뛰는 주전 라인맨",
       "rush": "패스러셔 3명 경기당 압박", "cov": "커버리지 4명 타깃당 허용 야드"}
FMT = {"qb": "{:+.2f}", "wr": "{:+.2f}", "rb": "{:+.2f}", "sack": "{:.1%}", "ol": "{:.0f}명", "rush": "{:.1f}", "cov": "{:.1f}"}
BASE = os.path.join(N.DATA, "hex_baseline.json")
OL_POS = ("T", "G", "C", "OL", "OT", "OG")
KQ, KW, KR = 150.0, 30.0, 40.0


def _p(name, season):
    for p in (os.path.join(N.CACHE, "hist", f"{name}_{season}.csv"), os.path.join(N.CACHE, f"{name}_{season}.csv"),
              os.path.join(N.CACHE, "hist", f"{name}_{season}.csv.gz"), os.path.join(N.CACHE, f"{name}_{season}.csv.gz")):
        if os.path.exists(p):
            return p
    return ""


def season_tables(season):
    """한 시즌 원자료 → 경기·팀·선수 단위 누적 재료."""
    S = {"qb": defaultdict(lambda: defaultdict(lambda: [0.0, 0.0])),        # week -> passer -> [db, epa]
         "rec": defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))),   # team -> week -> name -> [tgt, epa]
         "run": defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))),   # team -> week -> name -> [car, epa]
         "off": defaultdict(lambda: defaultdict(lambda: [0.0, 0.0])),                         # team -> week -> [db, sacks]
         "use": defaultdict(set),                                                             # (gid, team) -> 공격 기록 있는 이름
         "def": defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0.0, 0.0]))),   # team -> week -> name -> [press, tgt, yds, g]
         "dplay": defaultdict(set),                                                           # (gid, team) -> 수비 기록 있는 이름
         "ol": defaultdict(lambda: defaultdict(lambda: defaultdict(float))),                  # team -> week -> name -> off snaps
         "olplay": defaultdict(set), "passers": set(),
         "snap_off": defaultdict(set), "snap_def": defaultdict(set), "snap_offk": defaultdict(set)}   # 스냅 기록으로 본 출전(결과와 무관한 출전 판정)
    pp = _p("play_by_play", season)
    if pp:
        for x in N.rd(pp):
            if x.get("season_type", "REG") != "REG" or not x.get("posteam"):
                continue
            wk = int(x["week"]); t = x["posteam"]; key = (x["game_id"], t); e = N.fnum(x.get("epa")) or 0.0
            if x.get("qb_dropback") == "1":
                o = S["off"][t][wk]; o[0] += 1; o[1] += 1 if x.get("sack") == "1" else 0
                if x.get("passer_player_name"):
                    d = S["qb"][wk][x["passer_player_name"]]; d[0] += 1; d[1] += e; S["use"][key].add(x["passer_player_name"]); S["passers"].add(x["passer_player_name"])
            if x.get("play_type") == "pass" and x.get("receiver_player_name"):
                d = S["rec"][t][wk][x["receiver_player_name"]]; d[0] += 1; d[1] += e; S["use"][key].add(x["receiver_player_name"])
            if x.get("play_type") == "run" and x.get("rusher_player_name"):
                d = S["run"][t][wk][x["rusher_player_name"]]; d[0] += 1; d[1] += e; S["use"][key].add(x["rusher_player_name"])
    dp = _p("advstats_week_def", season)
    if dp:
        for r in csv.DictReader(open(dp, encoding="utf-8-sig")):
            if r.get("game_type") != "REG":
                continue
            t = N.ESPN2NV.get(r["team"], r["team"]); wk = int(r.get("week") or 0); nm = r["pfr_player_name"]
            d = S["def"][t][wk][nm]; d[0] += N.fnum(r.get("def_pressures")) or 0; d[1] += N.fnum(r.get("def_targets")) or 0; d[2] += N.fnum(r.get("def_yards_allowed")) or 0; d[3] += 1
            S["dplay"][(r["game_id"], t)].add(nm)
    sp = _p("snap_counts", season)
    if sp:
        for r in csv.DictReader(open(sp, encoding="utf-8-sig")):
            if r.get("game_type") != "REG":
                continue
            t = N.ESPN2NV.get(r["team"], r["team"]); wk = int(r.get("week") or 0); sn = N.fnum(r.get("offense_snaps")) or 0
            if sn > 0:
                S["snap_off"][(r["game_id"], t)].add(r["player"])
                _w = [x for x in N._norm_name(r["player"]).split() if x]
                if _w:
                    S["snap_offk"][(r["game_id"], t)].add((_w[0][0], _w[-1]))      # (이름 첫 글자, 성) — pbp 짧은 이름 「J.Jefferson」 대조용
            if (N.fnum(r.get("defense_snaps")) or 0) > 0:
                S["snap_def"][(r["game_id"], t)].add(N._norm_name(r["player"]))
            if r.get("position") not in OL_POS:
                continue
            if sn > 0:
                S["ol"][t][wk][r["player"]] += sn; S["olplay"][(r["game_id"], t)].add(r["player"])
    return S


def materials(S, PREV, team, week, qb_full, plays):
    """그 팀의 재료 값 dict(없으면 그 키 없음). plays(kind, name) → 그 선수가 뛰는가(kind = off|def|ol)."""
    out = {}
    # QB
    if qb_full:
        n = e = 0.0
        for src in ([PREV["qbtot"]] if PREV else []) + [S["qb"][w] for w in S["qb"] if w < week]:
            for nm, (a, b) in src.items():
                if N._same_person(nm, qb_full):
                    n += a; e += b
        out["qb"] = e / (n + KQ)

    def cum(tbl):
        tot = defaultdict(lambda: [0.0, 0.0])
        for w in tbl[team]:
            if w < week:
                for nm, (a, b) in tbl[team][w].items():
                    tot[nm][0] += a; tot[nm][1] += b
        return tot
    ng = len([w for w in S["off"][team] if w < week])
    use_prev = ng < 3 and PREV
    rec = cum(PREV["rec"] if use_prev else S["rec"]); run = cum(PREV["run"] if use_prev else S["run"])
    if use_prev:   # 시즌 초: 작년 누적(같은 팀 소속 기준 — 이적은 반영 못 함)
        rec = PREV["rectot"].get(team, {}); run = PREV["runtot"].get(team, {})
    wr = sorted((nm for nm in rec if plays("off", nm)), key=lambda nm: -rec[nm][0])[:4]
    if wr and sum(rec[nm][0] for nm in wr) >= 20:
        out["wr"] = sum(rec[nm][0] * (rec[nm][1] / (rec[nm][0] + KW)) for nm in wr) / sum(rec[nm][0] for nm in wr)
    rb = sorted((nm for nm in run if plays("off", nm) and nm not in S["passers"] and not (PREV and nm in PREV["passers"])), key=lambda nm: -run[nm][0])[:2]
    if rb and sum(run[nm][0] for nm in rb) >= 15:
        out["rb"] = sum(run[nm][0] * (run[nm][1] / (run[nm][0] + KR)) for nm in rb) / sum(run[nm][0] for nm in rb)
    db = sum(S["off"][team][w][0] for w in S["off"][team] if w < week); sk = sum(S["off"][team][w][1] for w in S["off"][team] if w < week)
    if db < 60 and PREV and PREV["offtot"].get(team):
        db += PREV["offtot"][team][0]; sk += PREV["offtot"][team][1]
    if db >= 60:
        out["sack"] = sk / db
    wks = sorted(w for w in S["ol"][team] if w < week)[-3:]
    if wks:
        tot = defaultdict(float)
        for w in wks:
            for nm, v in S["ol"][team][w].items():
                tot[nm] += v
        st = [nm for nm, _ in sorted(tot.items(), key=lambda kv: -kv[1])[:5]]
        if len(st) == 5:
            out["ol"] = float(sum(1 for nm in st if plays("ol", nm)))
    dtot = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    for w in S["def"][team]:
        if w < week:
            for nm, v in S["def"][team][w].items():
                for i in range(4):
                    dtot[nm][i] += v[i]
    if len([w for w in S["def"][team] if w < week]) < 3 and PREV and PREV["deftot"].get(team):
        for nm, v in PREV["deftot"][team].items():
            for i in range(4):
                dtot[nm][i] += v[i]
    pr = sorted((nm for nm in dtot if plays("def", nm) and dtot[nm][3] >= 2), key=lambda nm: -dtot[nm][0])[:3]
    if len(pr) == 3:
        out["rush"] = sum(dtot[nm][0] / dtot[nm][3] for nm in pr)
    cv = sorted((nm for nm in dtot if plays("def", nm) and dtot[nm][1] > 0), key=lambda nm: -dtot[nm][1])[:4]
    if len(cv) == 4 and sum(dtot[nm][1] for nm in cv) >= 30:
        out["cov"] = sum(dtot[nm][2] for nm in cv) / sum(dtot[nm][1] for nm in cv)
    return out


def prev_tot(S):
    """다음 시즌의 「직전 시즌」 값으로 쓸 합계."""
    P = {"qbtot": defaultdict(lambda: [0.0, 0.0]), "rectot": {}, "runtot": {}, "offtot": {}, "deftot": {}, "passers": set(S["passers"]), "rec": S["rec"], "run": S["run"]}
    for w in S["qb"]:
        for nm, (a, b) in S["qb"][w].items():
            P["qbtot"][nm][0] += a; P["qbtot"][nm][1] += b
    for key, tbl in (("rectot", S["rec"]), ("runtot", S["run"])):
        for t in tbl:
            tot = defaultdict(lambda: [0.0, 0.0])
            for w in tbl[t]:
                for nm, (a, b) in tbl[t][w].items():
                    tot[nm][0] += a; tot[nm][1] += b
            P[key][t] = tot
    for t in S["off"]:
        P["offtot"][t] = [sum(v[0] for v in S["off"][t].values()), sum(v[1] for v in S["off"][t].values())]
    for t in S["def"]:
        tot = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
        for w in S["def"][t]:
            for nm, v in S["def"][t][w].items():
                for i in range(4):
                    tot[nm][i] += v[i]
        P["deftot"][t] = tot
    return P


def pctile(base, key, v, high=True):
    xs = base.get(key) or []
    if not xs:
        return 50
    p = 100 * bisect.bisect_left(xs, v) / len(xs)
    return round(p if high else 100 - p)


def scores(base, mat):
    out = {}
    for name in VERTS:
        vs = [pctile(base, k, mat[k], hi) for k, hi in MATS[name] if k in mat]
        if not vs:
            return None
        out[name] = round(sum(vs) / len(vs))
    return out


def backtest(seasons=range(2018, 2026)):
    games = [g for g in N.rd(os.path.join(N.CACHE, "games.csv")) if g["game_type"] == "REG" and g.get("result") and g.get("spread_line")]
    PREV = None; rows = []; pool = defaultdict(list)
    p0 = season_tables(min(seasons) - 1)
    PREV = prev_tot(p0)
    for season in seasons:
        S = season_tables(season)
        for g in games:
            if int(g["season"]) != season or int(g["week"]) < 2:
                continue
            wk = int(g["week"]); gid = g["game_id"]; mats = {}
            for t, q in ((g["home_team"], g.get("home_qb_name")), (g["away_team"], g.get("away_qb_name"))):
                def plays(kind, nm, t=t):
                    # 출전 판정은 스냅 기록으로(그 경기 기록 유무로 보면 「못한 경기 = 결장」 으로 섞여 결과를 미리 보는 셈이 된다 — 2026-11-15 1차 실행에서 패스러시 결장 736경기로 부풀었음)
                    key = (gid, t)
                    if kind == "ol":
                        return nm in S["olplay"][key]
                    if kind == "def":
                        return (N._norm_name(nm) in S["snap_def"][key]) if S["snap_def"][key] else (nm in S["dplay"][key])
                    if not S["snap_offk"][key]:
                        return nm in S["use"][key]
                    _w = [x for x in N._norm_name(nm.split(".", 1)[1] if "." in nm else nm).split() if x]
                    return bool(_w) and (nm[0].lower(), _w[-1]) in S["snap_offk"][key]
                mats[t] = materials(S, PREV, t, wk, q, plays)
                mats[t + "_full"] = materials(S, PREV, t, wk, q, lambda kind, nm: True)
            rows.append(dict(season=season, res=N.fnum(g["result"]), mk=N.fnum(g["spread_line"]), h=mats[g["home_team"]], a=mats[g["away_team"]],
                             hf=mats[g["home_team"] + "_full"], af=mats[g["away_team"] + "_full"]))
            if season >= 2023:
                for m in mats.values():
                    for k, v in m.items():
                        pool[k].append(v)
        PREV = prev_tot(S); print(f"  {season}: 누적 {len(rows)}경기")
    base = {k: sorted(v) for k, v in pool.items()}
    json.dump({k: [round(x, 5) for x in v] for k, v in base.items()}, io.open(BASE + ".tmp", "w", encoding="utf-8")); os.replace(BASE + ".tmp", BASE)

    def corr(xs, ys):
        n = len(xs)
        if n < 30:
            return None
        mx, my = sum(xs) / n, sum(ys) / n
        sx = math.sqrt(sum((x - mx) ** 2 for x in xs)); sy = math.sqrt(sum((y - my) ** 2 for y in ys))
        return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy) if sx and sy else None
    sc = []
    for r in rows:
        sh, sa = scores(base, r["h"]), scores(base, r["a"])
        if sh and sa:
            sc.append((r, {v: sh[v] - sa[v] for v in VERTS}))
    L = [f"# NFL 육각형 꼭짓점 역사 측정 — {dt.date.today()} · 2018~2025 정규시즌(2주차~) {len(sc)}경기 · 실제로 뛴 선수의 경기 전 값 · 표시 재료 점검", "",
         "꼭짓점 차(홈 − 원정 점수)와 결과의 상관. 「승패」 = 홈 승 · 「점수차」 = 실제 홈 마진 · 「커버」 = 실제 홈 마진 − 마감 스프레드(0 에 가까우면 시장이 이미 반영).", "",
         "| 꼭짓점 | 재료 | 승패 상관 | 점수차 상관 | 커버 상관 | 차 15+ 인 쪽 승률 | 차 15+ 인 쪽 스프레드 |", "|---|---|---|---|---|---|---|"]
    for v in VERTS:
        xs = [d[v] for _, d in sc]
        big = [(r, d[v]) for r, d in sc if abs(d[v]) >= 15]
        w = sum(1 for r, x in big if (r["res"] > 0) == (x > 0) and r["res"] != 0); n = sum(1 for r, x in big if r["res"] != 0)
        cw = sum(1 for r, x in big if ((r["res"] - r["mk"]) > 0) == (x > 0) and r["res"] != r["mk"]); cn = sum(1 for r, x in big if r["res"] != r["mk"])
        L.append(f"| {v} | {' · '.join(LAB[k] for k, _ in MATS[v])} | {corr(xs, [1.0 if r['res'] > 0 else 0.0 for r, _ in sc]):+.3f} | {corr(xs, [r['res'] for r, _ in sc]):+.3f} | "
                 f"{corr(xs, [r['res'] - r['mk'] for r, _ in sc]):+.3f} | {w}-{n - w} {100 * w / max(1, n):.1f}% | {cw}-{cn - cw} {100 * cw / max(1, cn):.1f}% |")
    tot = [sum(d.values()) for _, d in sc]
    big = [(r, x) for (r, _), x in zip(sc, tot) if abs(x) >= 60]
    w = sum(1 for r, x in big if (r["res"] > 0) == (x > 0) and r["res"] != 0); n = sum(1 for r, x in big if r["res"] != 0)
    cw = sum(1 for r, x in big if ((r["res"] - r["mk"]) > 0) == (x > 0) and r["res"] != r["mk"]); cn = sum(1 for r, x in big if r["res"] != r["mk"])
    L.append(f"| 여섯 합 | 꼭짓점 점수 차의 합(차 60+ 로 봄) | {corr(tot, [1.0 if r['res'] > 0 else 0.0 for r, _ in sc]):+.3f} | {corr(tot, [r['res'] for r, _ in sc]):+.3f} | "
             f"{corr(tot, [r['res'] - r['mk'] for r, _ in sc]):+.3f} | {w}-{n - w} {100 * w / max(1, n):.1f}% | {cw}-{cn - cw} {100 * cw / max(1, cn):.1f}% |")
    mk = [r["mk"] for r, _ in sc]
    L += ["", f"참고: 마감 스프레드 자체의 승패 상관 {corr(mk, [1.0 if r['res'] > 0 else 0.0 for r, _ in sc]):+.3f} · 점수차 상관 {corr(mk, [r['res'] for r, _ in sc]):+.3f} · 여섯 합과 스프레드의 상관 {corr(tot, mk):+.3f}", "",
          "## 꼭짓점끼리 겹침(상관)", "", "| | " + " | ".join(VERTS) + " |", "|---|" + "---|" * len(VERTS)]
    for v in VERTS:
        L.append(f"| {v} | " + " | ".join("—" if u == v else f"{corr([d[v] for _, d in sc], [d[u] for _, d in sc]):+.2f}" for u in VERTS) + " |")
    # 맞대결·결장 손실 코호트(계획 2번)
    L += ["", "## 선수 맞대결·결장 손실 검정(「그 팀 쪽」 · 문턱 2개+ 시즌 50% 초과 & 전체 53%+ · 47% 이하면 상대 쪽)", "",
          "| 조건 | 경기 | 승자 맞힘 | 스프레드 승-패(-무) | 스프레드 적중 | z | 50% 넘긴 시즌 | 시즌별(스프레드) |", "|---|---|---|---|---|---|---|---|"]
    full = []
    for r in rows:
        sh, sa, fh, fa = scores(base, r["h"]), scores(base, r["a"]), scores(base, r["hf"]), scores(base, r["af"])
        if sh and sa and fh and fa:
            full.append((r, sh, sa, fh, fa))
    passed = []

    def cohort(lab, cond):
        w = l = p = sw = sl = 0; by = defaultdict(lambda: [0, 0])
        for r, sh, sa, fh, fa in full:
            a_, h_ = bool(cond(sa, sh, fa)), bool(cond(sh, sa, fh))
            if a_ == h_:
                continue
            s_ = 1 if h_ else -1
            if r["res"] != 0:
                ok = (r["res"] > 0) == (s_ > 0); sw += ok; sl += (not ok)
            cov = r["res"] - r["mk"]
            if cov == 0:
                p += 1; continue
            ok = (cov > 0) == (s_ > 0); w += ok; l += (not ok); by[r["season"]][0 if ok else 1] += 1
        n = w + l
        if not n:
            L.append(f"| {lab} | 0 | — | — | — | — | — | — |"); return
        pct = 100 * w / n; over = sum(1 for a, b in by.values() if a + b and a / (a + b) > 0.5); tot = sum(1 for a, b in by.values() if a + b)
        L.append(f"| {lab} | {n} | {sw}-{sl} {100 * sw / max(1, sw + sl):.1f}% | {w}-{l}" + (f"-{p}" if p else "") + f" | {pct:.1f}% | {(w - n / 2) / math.sqrt(n / 4):+.2f} | {over}/{tot} | "
                 + " · ".join(f"{str(s)[2:]}:{a}-{b}" for s, (a, b) in sorted(by.items())) + " |")
        if pct >= 53 and over >= 2:
            passed.append(f"{lab}: 스프레드 {w}-{l} {pct:.1f}% · 시즌 {over}/{tot}")
        elif pct <= 47 and tot - over >= 2:
            passed.append(f"{lab} → 상대 쪽: 스프레드 {l}-{w} {100 - pct:.1f}% · 시즌 {tot - over}/{tot}")
    cohort("X1 패스 미스매치((QB+패스 무기)/2 ≥ 70 & 상대 커버리지 ≤ 30)", lambda me, op, mf: (me["QB"] + me["패스 무기"]) / 2 >= 70 and op["커버리지"] <= 30)
    cohort("X2 압박 미스매치(패스러시 ≥ 70 & 상대 패스 보호 ≤ 30)", lambda me, op, mf: me["패스러시"] >= 70 and op["패스 보호"] <= 30)
    cohort("X3 여섯 중 5개+ 앞서는 팀", lambda me, op, mf: sum(1 for v in VERTS if me[v] > op[v]) >= 5)
    for v in ("패스 무기", "패스 보호", "패스러시", "커버리지"):
        cohort(f"결장 손실 15+ 팀 · {v}(전원 가용 가정 − 실제)", lambda me, op, mf, v=v: mf[v] - me[v] >= 15)
    L += ["", "문턱 통과: " + (" / ".join(passed) if passed else "없음")]
    out = os.path.join(N.DATA, f"hex_backtest_{dt.date.today()}.md")
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n"); print("\n".join(L)); print(f"\nwrote {out} · {BASE}")


_LIVE = {}


def week_values(week):
    """그 주 경기별 {경기: {팀: {점수, 재료 값}}} → data/<시즌>-wNN/hex.json 에도 쓴다. 뛰는 선수 = 부상 보고 Out/Doubtful·IR·ESPN 명단 Out 이 아닌 선수."""
    if week in _LIVE:
        return _LIVE[week]
    import adv_players as AP
    base = json.load(io.open(BASE, encoding="utf-8")) if os.path.exists(BASE) else {}
    wd = N.week_dir(week)
    _hp, _ip = os.path.join(wd, "hex.json"), os.path.join(wd, "injuries.csv")
    if os.path.exists(_hp) and os.path.exists(_ip) and os.path.getmtime(_hp) >= os.path.getmtime(_ip):
        try:   # 같은 리프레시 안에서 이미 계산됨(각도 → 다이제스트 순서) — 부상 파일보다 새 hex.json 은 그대로 쓴다
            _LIVE[week] = json.load(io.open(_hp, encoding="utf-8"))
            return _LIVE[week]
        except Exception:
            pass
    S = season_tables(N.SEASON); PREV = prev_tot(season_tables(N.SEASON - 1))
    inj = {r["team"]: r for r in N.rd(os.path.join(wd, "injuries.csv"))}
    out = {}
    for g in N.rd(os.path.join(wd, "games.csv")):
        a, h = g["away"], g["home"]; gk = f"{a}@{h}"; out[gk] = {}
        for t in (a, h):
            x = inj.get(t, {})
            absent = [n.split("(")[0].strip() for key in ("out", "doubtful") for n in N.re.split(r"(?<=\))\s*·\s*", str(x.get(key) or "")) if n.strip()]
            absent += [n.strip() for n in str(x.get("espn_only_out") or "").split(" · ") if n.strip()] + list(AP.reserve_players(t))

            def plays(kind, nm, absent=absent):
                return not any(N._same_person(nm, f) or N._same_person(f, nm) or N._norm_name(nm) == N._norm_name(f) for f in absent)
            mat = materials(S, PREV, t, week, x.get("expected_qb") or "", plays)
            sc = scores(base, mat) if base else None
            full = scores(base, materials(S, PREV, t, week, x.get("expected_qb") or "", lambda kind, nm: True)) if base else None   # 전원 가용 가정(결장으로 깎인 폭 표시용)
            out[gk][t] = {"scores": sc, "full": full, "mat": {k: round(v, 4) for k, v in mat.items()}}
    p = os.path.join(wd, "hex.json")
    json.dump(out, io.open(p + ".tmp", "w", encoding="utf-8"), ensure_ascii=False); os.replace(p + ".tmp", p)
    _LIVE[week] = out
    return out


HIST_NOTE = "역사 2018~25 1,700여 경기: 여섯 합이 크게 앞선 팀 승률 66.8% · 스프레드 49.6% — 누가 이기나는 설명하지만 시장이 이미 반영"


def digest_line(a, h, v):
    """다이제스트 경기 절 「- 🔷 선수 육각형」 — 이번 주 뛰는 선수만으로 본 여섯 꼭짓점(값만 · 확률·★·판단 근거 아님). 발행문 「- 선수 비교:」 가 값으로 쓴다."""
    if not v or not (v.get(a) or {}).get("scores") or not (v.get(h) or {}).get("scores"):
        return "- 🔷 선수 육각형: 계산 불가(자료 부족)"
    sa, sh = v[a]["scores"], v[h]["scores"]
    one = lambda t, s: f"{t} " + " · ".join(f"{n} {s[n]}" for n in VERTS)
    ahead = lambda t, s, o: [n for n in VERTS if s[n] - o[n] >= 15]
    mu = (f"{a} 패스(QB·패스 무기 평균 {round((sa['QB'] + sa['패스 무기']) / 2)}) 대 {h} 커버리지 {sh['커버리지']} · {h} 패스({round((sh['QB'] + sh['패스 무기']) / 2)}) 대 {a} 커버리지 {sa['커버리지']} · "
          f"{a} 패스 보호 {sa['패스 보호']} 대 {h} 패스러시 {sh['패스러시']} · {h} 패스 보호 {sh['패스 보호']} 대 {a} 패스러시 {sa['패스러시']}")
    loss = []
    for t in (a, h):
        f, s = v[t].get("full"), v[t]["scores"]
        if f:
            loss += [f"{t} {n} −{f[n] - s[n]}(전원 가용이면 {f[n]})" for n in VERTS if f[n] - s[n] >= 10]
    return ("- 🔷 선수 육각형(이번 주 뛰는 선수만 · 0~100 · 50 = 리그 평균 · 값만 — " + HIST_NOTE + "): " + one(a, sa) + " / " + one(h, sh)
            + f" · 15점+ 앞서는 꼭짓점: {a} {', '.join(ahead(a, sa, sh)) or '없음'} / {h} {', '.join(ahead(h, sh, sa)) or '없음'}"
            + " · 맞대결: " + mu + " · 결장으로 깎인 꼭짓점: " + (" · ".join(loss) if loss else "없음"))


# ---- 보드 조각(NBA team_hex 와 같은 모양 · 클래스 이름 hexw/hexg/hext — 보드 CSS 가 색 변수 --hx1/--hx2 를 정한다) ----
def _pt(i, val, cx=150, cy=146, r=100):
    th = math.radians(-90 + 60 * i)
    return cx + r * val / 100 * math.cos(th), cy + r * val / 100 * math.sin(th)


def _poly(vals):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in (_pt(i, v) for i, v in enumerate(vals)))


def svg(first, second):
    o = [f'<svg class="hexg" viewBox="0 0 300 292" role="img" aria-label="{html.escape(first[0])}와 {html.escape(second[0])} 육각형 비교 — 값은 옆 표">']
    for lv in (25, 50, 75, 100):
        o.append(f'<polygon points="{_poly([lv] * 6)}" class="hgr{" hgm" if lv == 50 else ""}"/>')
    for i in range(6):
        x, y = _pt(i, 100)
        o.append(f'<line x1="150" y1="146" x2="{x:.1f}" y2="{y:.1f}" class="hgr"/>')
    for team, col, sc in (second, first):
        o.append(f'<polygon points="{_poly([sc[n] for n in VERTS])}" style="fill:var({col});stroke:var({col})" class="hsr"/>')
    for team, col, sc in (second, first):
        for i, n in enumerate(VERTS):
            x, y = _pt(i, sc[n])
            o.append(f'<g><title>{html.escape(team)} {html.escape(n)} {sc[n]}</title><circle cx="{x:.1f}" cy="{y:.1f}" r="11" class="hhit"/><circle cx="{x:.1f}" cy="{y:.1f}" r="4" style="fill:var({col})" class="hdot"/></g>')
    for i, n in enumerate(VERTS):
        x, y = _pt(i, 100)
        lx, ly = 150 + (x - 150) * 1.14, 146 + (y - 146) * 1.14
        anc = "middle" if abs(lx - 150) < 8 else "start" if lx > 150 else "end"
        o.append(f'<text x="{lx:.1f}" y="{ly + 4:.1f}" text-anchor="{anc}" class="hlb">{html.escape(n)}</text>')
    return "".join(o) + "</svg>"


def block(a, h, pick, v):
    """보드 HTML 조각 — v = week_values(week)[「A@H」]. 우리 예측 승자(pick)가 위에 그려진다. 값이 없으면 빈 문자열."""
    if not v or not (v.get(a) or {}).get("scores") or not (v.get(h) or {}).get("scores"):
        return ""
    sa, sh, ma, mh = v[a]["scores"], v[h]["scores"], v[a]["mat"], v[h]["mat"]
    ca, ch = ("--hx1", "--hx2") if pick == a else ("--hx2", "--hx1")
    first, second = ((a, ca, sa), (h, ch, sh)) if pick == a else ((h, ch, sh), (a, ca, sa))
    leg = "".join(f'<span class="hlg"><i style="background:var({c})"></i>{html.escape(t)}{" · 예측 승자" if t == pick else ""}</span>' for t, c in ((first[0], first[1]), (second[0], second[1])))
    rows = []
    for name in VERTS:
        bits = " · ".join(f"{LAB[k]} {FMT[k].format(ma[k]) if k in ma else '—'} / {FMT[k].format(mh[k]) if k in mh else '—'}" for k, _ in MATS[name])
        xa, xh = ("hhi", "") if sa[name] > sh[name] else ("", "hhi") if sh[name] > sa[name] else ("", "")
        rows.append(f'<tr><td>{html.escape(name)}</td><td class="n {xa}">{sa[name]}</td><td class="n {xh}">{sh[name]}</td><td class="hsub">{html.escape(bits)}</td></tr>')
    tbl = (f'<table class="hext"><thead><tr><th>꼭짓점</th><th class="n">{html.escape(a)}</th><th class="n">{html.escape(h)}</th><th>실제 값({html.escape(a)} / {html.escape(h)})</th></tr></thead><tbody>'
           + "".join(rows) + "</tbody></table>")
    return (f'<div class="hexw"><div class="hexc"><div class="hexl">{leg}</div>{svg(first, second)}</div><div class="hexd">{tbl}'
            '<p class="hcap">이번 주에 뛰는 선수만으로 계산(결장·비활성·IR 제외) · 50 = 리그 평균 · 바깥쪽이 좋은 쪽 · 설명용이고 넓이는 승률이 아니다(시장이 이미 반영한 정보)</p></div></div>')


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--backtest", action="store_true"); ap.add_argument("--week", type=int)
    a = ap.parse_args()
    if a.backtest:
        backtest()
    if a.week:
        for gk, v in week_values(a.week).items():
            print(gk, {t: x["scores"] for t, x in v.items()})


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
