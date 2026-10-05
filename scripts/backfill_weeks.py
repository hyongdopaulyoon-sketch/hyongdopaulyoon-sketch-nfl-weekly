"""1~3주차 소급 백테스트(2026-10-05 Paul 「1~3주차도 백테스트해서 기록용으로 합치자」 — 수집 세션과 분담).
  python backfill_weeks.py --weeks 1-3
기록용 — 사전 등록된 전향 판정 표본(티저 60다리 · 바람 40픽 · A1/A2 30픽 · 새 정보 30픽)에는 섞지 않는다.
grade 에 「(소급)」 꼬리표, id 끝 B. 같은 규칙(조정 금지 상수)을 그 주 마감 라인에 그대로 적용한다:
  · 라인 = 수집 세션 closing.csv(DK 마감, ESPN pickcenter) — 없으면 nflverse 마감(note 에 원천 표기)
  · 티저 다리 = picks.TEASER_* · A1 = 원정 −7 이상 페이버릿 → 홈 언더독 · A2 = 드라이브 득점 차 0.5+ 언더독 반대(양 팀 3경기+ — 1~3주차는 대부분 해당 없음)
  · 바람 언더 = wind_backfill.csv 의 킥오프 예보 풍속(Open-Meteo 과거 예보) ≥15mph · 실외 — 예보 없으면 기록하지 않는다(실측 바람으로 대신하지 않음)
  · 모델 예측 = 드라이브 모델(그 주 전 2026 경기만) → predictions.csv src=모델 「소급(마감)」
채점은 nflverse 최종 점수로 바로 한다(결과 CSV 가 없는 주차)."""
import argparse, os, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nfl_pull as N      # noqa: E402
import picks as P         # noqa: E402
import predictions as PR  # noqa: E402

SUF = "(소급)"


def lines(week):
    """{A@H: dict(hl, tot, mla, mlh, src, gid, fa, fh, roof, neutral)} — DK 마감 우선."""
    dk = {r["game"]: r for r in N.rd(os.path.join(N.week_dir(week), "closing.csv"))}
    out = {}
    for g in PR._cache_games(week):
        if g.get("game_type") != "REG":
            continue
        gk = f'{g["away_team"]}@{g["home_team"]}'
        c = dk.get(gk)
        if c and N.fnum(c.get("spread_home")) is not None:
            hl, tot, mla, mlh, src = N.fnum(c["spread_home"]), N.fnum(c["total"]), c.get("ml_away"), c.get("ml_home"), "DK 마감"
        else:
            sl = N.fnum(g.get("spread_line"))
            hl, tot, mla, mlh, src = (-sl if sl is not None else None), N.fnum(g.get("total_line")), g.get("away_moneyline"), g.get("home_moneyline"), "nflverse 마감"
        out[gk] = dict(hl=hl, tot=tot, mla=mla, mlh=mlh, src=src, gid=g["game_id"], fa=N.fnum(g.get("away_score")), fh=N.fnum(g.get("home_score")),
                       roof=g.get("roof", ""), neutral=g.get("location") == "Neutral", kick=f'{g.get("gameday")} {g.get("gametime")}')
    return out


def grade_row(r, x):
    """스프레드·총점 쪽 W/L/P + 유닛."""
    if x["fa"] is None or x["fh"] is None:
        return
    wl, score = P._grade_one(r, {"away_score": x["fa"], "home_score": x["fh"]})
    if not wl:
        return
    o = N.fnum(r["odds"]) or -110
    r["result"], r["score"] = wl, score
    r["units"] = "0" if wl == "P" else ("-1" if wl == "L" else f"{(100 / abs(o) if o < 0 else o / 100):.3f}")


def paper(week, L):
    import stat_research as SR
    try:
        T, _P, _n = SR.load(N.SEASON, cache=False)
    except Exception:
        T = {}
    off, de = defaultdict(list), defaultdict(list)
    for (g, wk, pt, dt), x in T.items():
        if wk < week:
            off[pt].append(x); de[dt].append(x)

    def ppd(xs):
        d = sum(x.get("dr", 0) for x in xs)
        return sum(x.get("dr_pts", 0) for x in xs) / d if d else None
    wind = {r["game"]: r for r in N.rd(os.path.join(N.week_dir(week), "wind_backfill.csv"))}
    new = []
    for gk, x in L.items():
        a, h = gk.split("@"); hl, tot = x["hl"], x["tot"]
        if hl is None or tot is None:
            continue
        base = {k: "" for k in P.HDR} | {"season": N.SEASON, "week": week, "game": gk, "status": "suggested"}
        if tot <= P.TEASER_TOT:
            for team, ln in ((h, hl), (a, -hl)):
                if P.TEASER_FAV[0] <= ln <= P.TEASER_FAV[1] or P.TEASER_DOG[0] <= ln <= P.TEASER_DOG[1]:
                    new.append(base | {"id": f'{x["gid"]}:spread:TB', "market": "spread", "side": f"{team} {ln + 6:+g}", "line": f"{ln + 6:+g}",
                                       "odds": P.TEASER_LEG_ODDS, "grade": P.TEASER_GRADE.replace("(관찰)", SUF),
                                       "note": f"소급 · 원 라인 {ln:+g} · 총점 {tot:g} · {x['src']} · 2팀 −120 티저 다리 환산 −283"})
        if hl >= 7:
            new.append(base | {"id": f'{x["gid"]}:spread:A1B', "market": "spread", "side": f"{h} {hl:+g}", "line": f"{hl:+g}", "odds": "-110",
                               "grade": "각도 관찰 A1" + SUF, "note": f"소급 · 원정 {a} {-hl:+g} 페이버릿 · {x['src']}"})
        if len(off[a]) >= 3 and len(off[h]) >= 3:
            na = (ppd(off[a]) or 0) - (ppd(de[a]) or 0); nh = (ppd(off[h]) or 0) - (ppd(de[h]) or 0)
            for dog, fav, dline, diff in ((h, a, hl, nh - na), (a, h, -hl, na - nh)):
                if dline > 0 and diff >= 0.5:
                    new.append(base | {"id": f'{x["gid"]}:spread:A2B', "market": "spread", "side": f"{fav} {-dline:+g}", "line": f"{-dline:+g}",
                                       "odds": "-110", "grade": "각도 관찰 A2" + SUF, "note": f"소급 · 언더독 {dog} 드라이브 득점 차 {diff:+.2f} → 반대 {fav} · {x['src']}"})
        w = wind.get(gk)
        fw = N.fnum(w.get("forecast_wind_mph")) if w else None
        if fw is not None and fw >= P.WIND_MPH and not x["neutral"] and x["roof"] in ("outdoors", "open"):
            new.append(base | {"id": f'{x["gid"]}:total:WB', "market": "total", "side": f"Under {tot:g}", "line": f"{tot:g}", "odds": "-110",
                               "grade": P.WIND_GRADE.replace("(관찰)", SUF), "note": f"소급 · 킥오프 예보 {fw:.0f}mph({w.get('source', '')}) · {x['src']}"})
    for r in new:
        grade_row(r, L[r["game"]])
    return new


def model_preds(week, L):
    """드라이브 모델 소급 예측(그 주 전 경기만) — predictions.csv src=모델."""
    import stat_research as SR
    dm, lg = PR._drive_model(week)
    rows = N.rd(PR.path(week)); keep = {(r["game"], r["src"]): r for r in rows}; n = 0
    for gk, x in L.items():
        a, h = gk.split("@")
        if (gk, "모델") in keep or a not in dm or h not in dm:
            continue
        hfa = 0 if x["neutral"] else N.HFA / 2
        ea = SR.DRIVES_PG * (dm[a][0] + dm[h][1] - lg) - hfa
        eh = SR.DRIVES_PG * (dm[h][0] + dm[a][1] - lg) + hfa
        pm = N.norm_cdf((eh - ea) / N.SD_MARGIN)
        keep[(gk, "모델")] = {k: "" for k in PR.HDR} | dict(game_id=x["gid"], week=week, game=gk, made_at="소급(마감)", src="모델",
                                                           pick=h if eh >= ea else a, p_pick=f"{max(pm, 1 - pm):.3f}", score_away=f"{ea:.1f}",
                                                           score_home=f"{eh:.1f}", line_home="" if x["hl"] is None else f'{x["hl"]:g}',
                                                           total_line="" if x["tot"] is None else f'{x["tot"]:g}')
        n += 1
    N.wcsv(PR.path(week), PR.HDR, [[r.get(k, "") for k in PR.HDR] for r in keep.values()])
    PR.grade(week)
    return n


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--weeks", required=True)
    lo, _, hi = ap.parse_args().weeks.partition("-")
    allrows = P.rd(P.PICKS)
    keep = {r["id"]: r for r in allrows}
    for wk in range(int(lo), int(hi or lo) + 1):
        L = lines(wk)
        srcs = defaultdict(int)
        for x in L.values():
            srcs[x["src"]] += 1
        for rid in [k for k, v in keep.items() if int(v["week"]) == wk and v["grade"].endswith(SUF)]:
            del keep[rid]                       # 소급 행은 다시 계산(전향 행은 건드리지 않는다)
        new = paper(wk, L)
        for r in new:
            keep[r["id"]] = r
        nm = model_preds(wk, L)
        by = defaultdict(list)
        for r in new:
            by[r["grade"]].append(r["result"])
        print(f"week {wk}: 경기 {len(L)}(라인 {dict(srcs)}) · 모델 예측 {nm} · "
              + (" · ".join(f'{g} {v.count("W")}-{v.count("L")}' + (f'-{v.count("P")}' if v.count("P") else "") for g, v in by.items()) or "페이퍼 해당 없음"))
    P.save(list(keep.values()))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
