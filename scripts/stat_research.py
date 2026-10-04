"""어떤 NFL 수치가 「실력」이고 어떤 게 「운」인가 — 2017~2025 플레이별 기록으로 직접 잰다(2026-10-04 Paul 「실제 스코어 확률·패스 성공률 같은 걸 리서치해서」).
  python stat_research.py
① 안정성(split-half): 같은 팀-시즌의 홀수 경기 값 vs 짝수 경기 값 상관 — 높을수록 실력(반복됨), 낮을수록 운.
② 예측력: 시즌 앞 8경기 값 → 뒤 경기(9주~)의 드라이브당 득점(공격) / 드라이브당 실점(수비) 상관.
③ 선수: QB(드롭백 300+ 시즌)·리시버(타깃 60+)·러셔(캐리 100+)의 split-half 안정성.
결과는 수치를 다이제스트에 어떻게 쓸지(서술·가중)의 근거가 된다 — 지어낸 기준 없이 이 표만 인용한다."""
import csv, gzip, math, os, pickle, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nfl_pull as N   # noqa: E402

HIST = os.path.join(N.CACHE, "hist")
TEAM = {"OAK": "LV", "SD": "LAC", "STL": "LA", "LAR": "LA"}
SEASONS = range(2017, 2026)


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def tm(t):
    return TEAM.get(t, t)


def load(season, cache=True):
    """팀-경기 단위 공격 합계 + 선수-경기 단위 합계 + 선수 이름(pickle 캐시 — 진행 중 시즌은 cache=False)."""
    pk = os.path.join(HIST, f"research_{season}.pkl")
    if cache and os.path.exists(pk):
        return pickle.load(open(pk, "rb"))
    src = os.path.join(HIST, f"play_by_play_{season}.csv.gz")
    if not os.path.exists(src):
        src = os.path.join(N.CACHE, f"play_by_play_{season}.csv.gz")
    T = defaultdict(lambda: defaultdict(float))     # (game_id, week, posteam, defteam) → 합계
    P = defaultdict(lambda: defaultdict(float))     # (kind, player_id, game_id) → 합계
    drives = {}                                      # (game_id, posteam, fixed_drive) → (결과, 레드존 도달)
    names = {}                                       # player_id → (이름, 팀)
    with gzip.open(src, "rt", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("season_type", "REG") != "REG" or not r.get("posteam") or not r.get("defteam"):
                continue
            k = (r["game_id"], int(r["week"]), tm(r["posteam"]), tm(r["defteam"]))
            dk = (r["game_id"], k[2], r.get("fixed_drive"))
            if r.get("fixed_drive"):
                res, rz = drives.get(dk, (r.get("fixed_drive_result") or "", False))
                drives[dk] = (r.get("fixed_drive_result") or res, rz or (f(r.get("yardline_100")) or 100) <= 20)
            if r.get("play_type") not in ("pass", "run"):
                continue
            e = f(r.get("epa"))
            if e is None:
                continue
            x = T[k]
            db = f(r.get("qb_dropback")) == 1
            yd = f(r.get("yards_gained")) or 0
            x["n"] += 1; x["epa"] += e; x["suc"] += f(r.get("success")) or 0; x["yds"] += yd
            if db:
                x["db"] += 1; x["pepa"] += e; x["sack"] += f(r.get("sack")) == 1
                if f(r.get("pass_attempt")) == 1 and f(r.get("sack")) != 1:
                    x["att"] += 1; x["cmp"] += f(r.get("complete_pass")) == 1; x["pyds"] += yd
                    c = f(r.get("cpoe"))
                    if c is not None:
                        x["cpoe"] += c; x["cpoe_n"] += 1
                x["xpl"] += yd >= 20
            else:
                x["rn"] += 1; x["repa"] += e; x["ryds"] += yd; x["xpl"] += yd >= 10
            x["to"] += (f(r.get("interception")) == 1) + (f(r.get("fumble_lost")) == 1)
            if r.get("down") == "3":
                x["d3"] += 1; x["d3c"] += f(r.get("first_down")) == 1 or f(r.get("touchdown")) == 1
            # 선수
            for _idk, _nmk in (("passer_player_id", "passer_player_name"), ("receiver_player_id", "receiver_player_name"), ("rusher_player_id", "rusher_player_name")):
                if r.get(_idk):
                    names[r[_idk]] = (r.get(_nmk) or "", k[2])
            if db and r.get("passer_player_id") and f(r.get("pass_attempt")) == 1:
                q = P[("qb", r["passer_player_id"], r["game_id"])]
                q["db"] += 1; q["epa"] += e
                if f(r.get("sack")) != 1:
                    q["att"] += 1; q["cmp"] += f(r.get("complete_pass")) == 1; q["yds"] += yd
                    q["td"] += f(r.get("pass_touchdown")) == 1; q["int"] += f(r.get("interception")) == 1
                    c = f(r.get("cpoe"))
                    if c is not None:
                        q["cpoe"] += c; q["cpoe_n"] += 1
                else:
                    q["sack"] += 1
            if db and r.get("receiver_player_id"):
                w = P[("rec", r["receiver_player_id"], r["game_id"])]
                w["tgt"] += 1; w["cmp"] += f(r.get("complete_pass")) == 1; w["yds"] += yd; w["epa"] += e; w["td"] += f(r.get("pass_touchdown")) == 1
            if (not db) and r.get("rusher_player_id"):
                u = P[("rush", r["rusher_player_id"], r["game_id"])]
                u["car"] += 1; u["yds"] += yd; u["epa"] += e; u["suc"] += f(r.get("success")) or 0; u["td"] += f(r.get("rush_touchdown")) == 1
    # 드라이브 → 팀-경기
    by_gt = defaultdict(list)
    for (g, team, _d), v in drives.items():
        by_gt[(g, team)].append(v)
    for k, x in T.items():
        dv = by_gt.get((k[0], k[2]), [])
        x["dr"] = len(dv)
        x["dr_td"] = sum(1 for res, _ in dv if res == "Touchdown")
        x["dr_fg"] = sum(1 for res, _ in dv if res == "Field goal")
        x["dr_pts"] = 7 * x["dr_td"] + 3 * x["dr_fg"]
        x["rz"] = sum(1 for _, rz in dv if rz)
        x["rz_td"] = sum(1 for res, rz in dv if rz and res == "Touchdown")
    out = ({k: dict(v) for k, v in T.items()}, {k: dict(v) for k, v in P.items()}, names)
    if cache:
        pickle.dump(out, open(pk + ".tmp", "wb")); os.replace(pk + ".tmp", pk)
    return out


# 팀 수치 정의: (이름, 분자 키, 분모 키, 배수)
TEAM_STATS = [
    ("드라이브당 득점", "dr_pts", "dr", 1), ("드라이브 TD 확률", "dr_td", "dr", 100), ("드라이브 득점(TD+FG) 확률", None, "dr", 100),
    ("레드존 TD 전환율", "rz_td", "rz", 100), ("EPA/플레이", "epa", "n", 1), ("성공률", "suc", "n", 100),
    ("패스 EPA/드롭백", "pepa", "db", 1), ("러시 EPA/캐리", "repa", "rn", 1), ("패스 성공률(완성%)", "cmp", "att", 100),
    ("CPOE", "cpoe", "cpoe_n", 1), ("패스 야드/시도", "pyds", "att", 1), ("러시 야드/캐리", "ryds", "rn", 1),
    ("색 비율", "sack", "db", 100), ("폭발 플레이 비율", "xpl", "n", 100), ("턴오버/플레이", "to", "n", 100), ("3rd down 전환", "d3c", "d3", 100),
]


def val(rows, num, den, mult):
    if num is None:
        a = sum(r.get("dr_td", 0) + r.get("dr_fg", 0) for r in rows)
    else:
        a = sum(r.get(num, 0) for r in rows)
    b = sum(r.get(den, 0) for r in rows)
    return mult * a / b if b else None


def corr(xs, ys):
    pts = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pts)
    if n < 10:
        return None, n
    mx = sum(p[0] for p in pts) / n; my = sum(p[1] for p in pts) / n
    sx = math.sqrt(sum((p[0] - mx) ** 2 for p in pts)); sy = math.sqrt(sum((p[1] - my) ** 2 for p in pts))
    return (sum((p[0] - mx) * (p[1] - my) for p in pts) / (sx * sy) if sx and sy else None), n


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    teamgames = defaultdict(list)    # (season, team, side) → [(week, row)]
    players = defaultdict(list)      # (kind, pid, season) → [(week, row)]
    for s in SEASONS:
        T, Pl, _nm = load(s)
        wk_of = {}
        for (g, wk, pt, dt), x in T.items():
            teamgames[(s, pt, "off")].append((wk, x)); teamgames[(s, dt, "def")].append((wk, x)); wk_of[g] = wk
        for (kind, pid, g), x in Pl.items():
            players[(kind, pid, s)].append((wk_of.get(g, 0), x))
    print(f"■ 표본: 2017~2025 정규시즌 · 팀-시즌 {sum(1 for k in teamgames if k[2] == 'off')}")
    print("\n① 팀 수치 — 안정성(홀/짝 경기 상관) · 예측력(앞 8경기 → 뒤 경기 드라이브당 득점·실점)")
    print("수치 | 공격 안정성 | 공격 예측력 | 수비 안정성 | 수비 예측력")
    for name, num, den, mult in TEAM_STATS:
        cells = []
        for side in ("off", "def"):
            odd, even, first, later = [], [], [], []
            for (s, t, sd), lst in teamgames.items():
                if sd != side or len(lst) < 12:
                    continue
                lst = sorted(lst, key=lambda v: v[0])
                rows = [x for _, x in lst]
                odd.append(val(rows[0::2], num, den, mult)); even.append(val(rows[1::2], num, den, mult))
                first.append(val(rows[:8], num, den, mult)); later.append(val(rows[8:], "dr_pts", "dr", 1))
            r1, _n = corr(odd, even); r2, _ = corr(first, later)
            cells += [f"{r1:+.2f}" if r1 is not None else "—", f"{r2:+.2f}" if r2 is not None else "—"]
        print(f"{name} | " + " | ".join(cells))
    print("\n② 선수 수치 — 안정성(홀/짝 경기 상관) · 기준: QB 시즌 드롭백 300+ · 리시버 타깃 60+ · 러셔 캐리 100+")
    PSTATS = [("qb", "완성%(패스 성공률)", "cmp", "att", 100, ("db", 300)), ("qb", "CPOE", "cpoe", "cpoe_n", 1, ("db", 300)),
              ("qb", "야드/시도", "yds", "att", 1, ("db", 300)), ("qb", "EPA/드롭백", "epa", "db", 1, ("db", 300)),
              ("qb", "TD%", "td", "att", 100, ("db", 300)), ("qb", "INT%", "int", "att", 100, ("db", 300)), ("qb", "색%", "sack", "db", 100, ("db", 300)),
              ("rec", "캐치율", "cmp", "tgt", 100, ("tgt", 60)), ("rec", "야드/타깃", "yds", "tgt", 1, ("tgt", 60)), ("rec", "EPA/타깃", "epa", "tgt", 1, ("tgt", 60)),
              ("rec", "TD/타깃", "td", "tgt", 100, ("tgt", 60)),
              ("rush", "야드/캐리", "yds", "car", 1, ("car", 100)), ("rush", "성공률", "suc", "car", 100, ("car", 100)), ("rush", "EPA/캐리", "epa", "car", 1, ("car", 100))]
    print("포지션 | 수치 | 안정성 | 선수-시즌 수")
    for kind, name, num, den, mult, (mk, mn) in PSTATS:
        odd, even = [], []
        for (k, pid, s), lst in players.items():
            if k != kind:
                continue
            rows = [x for _, x in sorted(lst, key=lambda v: v[0])]
            if sum(x.get(mk, 0) for x in rows) < mn:
                continue
            odd.append(val(rows[0::2], num, den, mult)); even.append(val(rows[1::2], num, den, mult))
        r, n = corr(odd, even)
        print(f"{kind} | {name} | {r:+.2f} | {n}" if r is not None else f"{kind} | {name} | — | {n}")

    drive_model_check()


R_OFF, R_DEF, HALF_DRIVES, DRIVES_PG = 0.61, 0.36, 94.0, 11.0     # ①에서 잰 드라이브당 득점 안정성 · 반 시즌 드라이브 수 · 경기당 드라이브
K_OFF = HALF_DRIVES * (1 - R_OFF) / R_OFF                          # 수축 강도(드라이브) — 안정성 r = n/(n+k) 에서
K_DEF = HALF_DRIVES * (1 - R_DEF) / R_DEF


def shrunk_ppd(rows, lg, k):
    pts = sum(r.get("dr_pts", 0) for r in rows); dr = sum(r.get("dr", 0) for r in rows)
    return (pts + k * lg) / (dr + k)


def drive_model_check():
    """③ 드라이브 기반 예상 득점(시즌 그 주 전까지, 수축) vs 시장 내재 점수 — 2018~2025 5주차~."""
    games = [g for g in N.rd(os.path.join(N.CACHE, "games.csv")) if g["game_type"] == "REG" and 2018 <= int(g["season"]) <= 2025
             and f(g.get("result")) is not None and f(g.get("spread_line")) is not None and f(g.get("total_line")) is not None and int(g["week"]) >= 5]
    err = defaultdict(float); n = 0
    for s in range(2018, 2026):
        T, _P, _n = load(s)
        lg_rows = list(T.values())
        lg = sum(r.get("dr_pts", 0) for r in lg_rows) / max(sum(r.get("dr", 0) for r in lg_rows), 1)
        off, de = defaultdict(list), defaultdict(list)
        for (g, wk, pt, dt), x in T.items():
            off[pt].append((wk, x)); de[dt].append((wk, x))
        for g in games:
            if int(g["season"]) != s:
                continue
            wk = int(g["week"]); h, a = tm(g["home_team"]), tm(g["away_team"])
            oh = shrunk_ppd([x for w, x in off[h] if w < wk], lg, K_OFF); oa = shrunk_ppd([x for w, x in off[a] if w < wk], lg, K_OFF)
            dh = shrunk_ppd([x for w, x in de[h] if w < wk], lg, K_DEF); da = shrunk_ppd([x for w, x in de[a] if w < wk], lg, K_DEF)
            ph = DRIVES_PG * (oh + da - lg) + N.HFA / 2; pa = DRIVES_PG * (oa + dh - lg) - N.HFA / 2
            res, tot, sp, tl = f(g["result"]), f(g["total"]), f(g["spread_line"]), f(g["total_line"])
            err["m_model"] += abs((ph - pa) - res); err["m_mkt"] += abs(sp - res)
            err["t_model"] += abs((ph + pa) - tot); err["t_mkt"] += abs(tl - tot); n += 1
    print()
    print(f"③ 드라이브 기반 예상 득점(수축 k 공격 {K_OFF:.0f}·수비 {K_DEF:.0f} 드라이브) vs 시장 — 2018~2025 5주차~ {n}경기")
    print(f"  점수 차 평균 오차: 모델 {err['m_model'] / n:.2f} · 시장 {err['m_mkt'] / n:.2f}  |  총점 평균 오차: 모델 {err['t_model'] / n:.2f} · 시장 {err['t_mkt'] / n:.2f}")


if __name__ == "__main__":
    main()
