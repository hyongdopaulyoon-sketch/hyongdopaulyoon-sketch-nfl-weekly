"""📊 스탯 비교(말로) — 2026-10-10 Paul 「수치들은 숫자만 나와 있고 이해하기 힘듦 · 스탯 비교가 더 필요함」.
발행문이 그대로 옮길 수 있게 **값 + 32팀 순위 + 상위/중간/하위 낱말 + 한 줄 뜻**을 다이제스트가 만든다(발행 세션 재계산 금지).
전부 서술 전용 — 시장이 이미 반영한 정보(N0·N12). 「유리/불리/우위」 낱말은 쓰지 않고 순위 구간(상위 1~10 · 중간 11~22 · 하위 23~32)만 쓴다."""
import os
from collections import defaultdict

import nfl_pull as N
import context_blocks as CB
import adv_players as AP

QB_MIN_DB = 60      # QB 순위 대상 최소 드롭백(이 밑이면 순위 대신 「표본 적음」)
WR_MIN_TGT = 15
RB_MIN_CAR = 25


def tier(rank, n=32):
    if rank is None:
        return "—"
    return "상위" if rank <= n * 10 // 32 else "중간" if rank <= n * 22 // 32 else "하위"


def _rank(vals, t, high=True):
    xs = sorted((v for v in vals.values() if v is not None), reverse=high)
    return (xs.index(vals[t]) + 1) if t in vals and vals[t] is not None else None


GAP_CUTS = ((4, "차이 없음"), (9, "근접"), (15, "경미"), (10 ** 9, "중대"))   # 2026-10-16 Paul 「서술 전용 등급 열」 — 32팀 순위 차 기준, 확률·별점 영향 0


def gap_label(ra, rh, a, h, n=32):
    """순위 차 → 「경미 · SEA 쪽」. n 이 32 가 아니면(QB 풀 등) 구간을 n/32 로 비례."""
    if ra is None or rh is None:
        return "—"
    d = abs(ra - rh) * 32 / max(n, 1)
    lab = next(name for cut, name in GAP_CUTS if d <= cut)
    return lab if lab == "차이 없음" else f"{lab} · {a if ra < rh else h} 쪽"


_GR = None


def _gap_rates():
    """data/gap_rates.json — scripts/gap_rates.py 가 만든 등급별 실측(2024~25 as-of · 순위 높은 팀 ML 승률 vs 시장 기대). 없으면 {}."""
    global _GR
    if _GR is None:
        try:
            import json
            _GR = json.load(open(os.path.join(N.DATA, "gap_rates.json"), encoding="utf-8"))
        except Exception:
            _GR = {}
    return _GR


def gap(vals, a, h, high=True, item=None):
    n = len([x for x in vals.values() if x is not None])
    lab = gap_label(_rank(vals, a, high), _rank(vals, h, high), a, h, n)
    if item and lab not in ("—", "차이 없음"):
        r = _gap_rates().get(item, {}).get(lab.split(" · ")[0])
        if r:   # 2026-10-17 Paul 「서술 옆에 퍼센트」 — 그 등급일 때 순위 높은 팀이 실제 이긴 비율 · 시장이 준 확률(서술 전용)
            lab += f"({r['win']}% · 시장 {r['mkt']}%)"
    return lab


def cell(vals, t, fmt, high=True, unit="", n=None):
    v = vals.get(t)
    if v is None:
        return "—"
    r = _rank(vals, t, high); n = n or len([x for x in vals.values() if x is not None])
    return f"{fmt.format(v)}{unit} · {r}위({tier(r, n)})"


def _def_rows(week):
    """advstats_week_def_<SEASON>.csv → {team: {pid: 누적 dict}} (week 미만 · 정규시즌) + 팀 합계."""
    import csv
    p = os.path.join(N.CACHE, f"advstats_week_def_{N.SEASON}.csv")
    out = defaultdict(lambda: defaultdict(lambda: defaultdict(float))); team = defaultdict(lambda: defaultdict(float)); games = defaultdict(set)
    if not os.path.exists(p):
        return out, team, games
    for r in csv.DictReader(open(p, encoding="utf-8-sig")):
        if r.get("game_type") != "REG" or int(r.get("week") or 0) >= week:
            continue
        t = N.ESPN2NV.get(r["team"], r["team"]); x = out[t][r["pfr_player_name"]]
        x["g"] += 1; games[t].add(r["game_id"])
        for c in ("def_pressures", "def_sacks", "def_times_hitqb", "def_targets", "def_completions_allowed", "def_yards_allowed", "def_tackles_combined", "def_missed_tackles", "def_ints"):
            v = N.fnum(r.get(c)) or 0; x[c] += v; team[t][c] += v
    return out, team, games


def defense_tables(a, h, RS, inj, g, week):
    """🛡️ 수비 선수 표(2026-10-18 Paul 「수비 비교는 안 해도 되나 선수들 스탯」) — PFR 주간 수비 기록 시즌 누적(그 주 전까지). 서술 전용·점수 0.
    팀별 패스러시 2(압박 순) · 커버리지 2(타깃 순) + 팀 줄(압박률·놓친 태클% 32팀 순위). 2018~25 재검: 압박률·색률·커버리지·놓친 태클 전부 시장이 반영(색률 상위 팀은 오히려 과대평가 → A10)."""
    rows, team, games = _def_rows(week)
    L = [f"- 🛡️ **수비 선수 표(PFR 주간 기록 시즌 누적 · {week}주차 전까지 · 패스러시 2 = 압박 순, 커버리지 2 = 타깃 순 · 팀 줄은 32팀 순위 · 발행문 「- 수비 표:」 아래 두 표 그대로 · 값만, 점수 0 — 압박·색·커버리지는 시장이 이미 반영)**:", ""]
    if not rows:
        return L + ["(advstats 수비 기록 없음 — 수비 표 생략)", ""]
    # 팀 압박률 = 압박 / 상대 드롭백(연구 T 의 defteam db), 놓친 태클% = 놓침/(태클+놓침)
    db_def = defaultdict(float)
    if RS:
        T, _P, _NM = RS
        for (gid, wk, pt, dt), x in T.items():
            if wk < week:
                db_def[dt] += x.get("db", 0)
    prr = {t: (team[t]["def_pressures"] / db_def[t]) if db_def.get(t) else None for t in team}
    mtr = {t: (team[t]["def_missed_tackles"] / (team[t]["def_tackles_combined"] + team[t]["def_missed_tackles"])) if (team[t]["def_tackles_combined"] + team[t]["def_missed_tackles"]) else None for t in team}
    skr = {t: (team[t]["def_sacks"] / db_def[t]) if db_def.get(t) else None for t in team}
    for t in (a, h):
        L.append(f"| {t} 수비 | 역할 | 경기 | 압박 | 색 | QB 히트 | 타깃→허용 | 야드/타깃 | 놓친 태클 | 상태 |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        pl = rows.get(t, {})
        rush = sorted(pl.items(), key=lambda kv: -kv[1]["def_pressures"])[:2]
        cov = sorted(pl.items(), key=lambda kv: -kv[1]["def_targets"])[:2]
        seen = set()
        for role, items in (("패스러시", rush), ("커버리지", cov)):
            for nm, x in items:
                if nm in seen:
                    continue
                seen.add(nm); st = CB.N._status_of(nm, inj.get(t, {}))
                tg = int(x["def_targets"]); cmp_ = int(x["def_completions_allowed"]); ypt = (x["def_yards_allowed"] / tg) if tg else None
                tk = x["def_tackles_combined"] + x["def_missed_tackles"]
                L.append(f"| {nm} | {role} | {int(x['g'])} | {int(x['def_pressures'])} | {x['def_sacks']:g} | {int(x['def_times_hitqb'])} | {tg}→{cmp_} | {f'{ypt:.1f}' if ypt is not None else '—'} | {int(x['def_missed_tackles'])}/{int(tk)} | {st or '—'} |")
        if not pl:
            L.append("| (기록 없음) | | | | | | | | | |")
        rp, rm, rs = _rank(prr, t), _rank(mtr, t, False), _rank(skr, t)
        nn = len([v for v in prr.values() if v is not None])
        L.append(f"| {t} 팀 | 합계 | {len(games.get(t, ()))} | 압박률 {100 * prr[t]:.1f}%({rp}위·{tier(rp, nn)}) | 색률 {100 * skr[t]:.1f}%({rs}위) | — | — | — | 놓친 태클 {100 * mtr[t]:.1f}%({rm}위·{tier(rm, nn)} — 적을수록 좋음) | — |" if prr.get(t) is not None and mtr.get(t) is not None else f"| {t} 팀 | 합계 | — | — | — | — | — | — | — | — |")
        L.append("")
    L.append("  ↳ 읽는 법: 압박·색은 상대 OL·QB 색 허용률(선수 표)과 맞춰 보고, 커버리지 「타깃→허용」은 많이 노려진 CB 를 뜻한다(허용 수가 많다고 나쁜 것은 아님 — 야드/타깃이 기준). 놓친 태클은 상대 RB 야드/캐리와 함께. 전부 서술 재료 — 2018~25 백테스트에서 시장을 못 이겼고, 색률 상위 8 수비는 오히려 시장이 과대평가(A10 관찰).")
    L.append("")
    return L


def player_tables(a, h, RS, inj, g):
    """🧑‍🤝‍🧑 팀별 선수 표(2026-10-12 Paul) — QB(예상 선발) · 러셔 2(캐리 순) · 리시버 4(타깃 순) · 키커. 값 + 리그 자격자 중 순위 + 부상 상태. 발행문이 두 표를 그대로 옮긴다."""
    L = [f"- 🧑‍🤝‍🧑 **선수 표(2026 정규시즌 전체 · 순위는 리그 자격자(QB 드롭백 {QB_MIN_DB}+ · 리시버 타깃 {WR_MIN_TGT}+ · 러셔 캐리 {RB_MIN_CAR}+) 중 · 상태 = 이번 주 부상 보고 · 발행문 「- 선수 표:」 아래 두 표 그대로 · 값만, 점수 0)**:", ""]
    if not RS:
        return L + ["(pbp 없음 — 선수 표 생략)", ""]
    T, P, NM = RS
    qb = defaultdict(lambda: defaultdict(float)); rec = defaultdict(lambda: defaultdict(float)); rus = defaultdict(lambda: defaultdict(float)); gcount = defaultdict(set)
    for (k, pid, gid), x in P.items():
        tgt = {"qb": qb, "rec": rec, "rush": rus}[k]
        for kk, vv in x.items():
            tgt[pid][kk] += vv
        gcount[pid].add(gid)
    qpool = {p: (x["epa"] / x["db"]) for p, x in qb.items() if x.get("db", 0) >= QB_MIN_DB}
    rpool = {p: x["yds"] / x["tgt"] for p, x in rec.items() if x.get("tgt", 0) >= WR_MIN_TGT}
    upool = {p: x["yds"] / x["car"] for p, x in rus.items() if x.get("car", 0) >= RB_MIN_CAR}

    def rk(pool, p):
        return f"{_rank(pool, p)}/{len(pool)}위·{tier(_rank(pool, p), len(pool))}" if p in pool else "표본 적음"
    DK = CB._depth_kicker(); KS = CB.kicker_stats()
    for t in (a, h):
        inj_t = inj.get(t) or {}
        L += [f"| {t} 선수 | 역할 | 경기 | 표본 | 야드 | TD | 효율 | EPA/플레이 | 리그 순위 | 상태 |", "|---|---|---|---|---|---|---|---|---|---|"]
        exp = inj_t.get("expected_qb") or ""
        qbs = sorted((p for p in qb if NM.get(p, ("", ""))[1] == t and qb[p].get("db", 0) >= 10), key=lambda p: -qb[p]["db"])[:2]
        for p in qbs:
            x = qb[p]; att = x.get("att", 0) or 1; db = x.get("db", 0) or 1
            tag = " (예상 선발)" if exp and N._same_person(NM[p][0], exp) else ""
            st = CB.N._status_of(NM[p][0], inj_t)
            L.append(f"| {NM[p][0]}{tag} | QB | {len(gcount[p])} | 드롭백 {int(db)} · 시도 {int(att)} | {int(x.get('yds', 0))} | 패스 {int(x.get('td', 0))} · INT {int(x.get('int', 0))}[운] | 완성 {100 * x.get('cmp', 0) / att:.0f}% · 야드/시도 {x.get('yds', 0) / att:.1f} · 색 {100 * x.get('sack', 0) / db:.1f}% | {x.get('epa', 0) / db:+.2f} | EPA {rk(qpool, p)} | {st or '—'} |")
        if exp and not any(N._same_person(NM[p][0], exp) for p in qbs):
            L.append(f"| {exp} (예상 선발) | QB | 0 | 2026 기록 없음 | — | — | — | — | 표본 적음 | {CB.N._status_of(exp, inj_t) or '—'} |")
        for p in sorted((p for p in rus if NM.get(p, ("", ""))[1] == t), key=lambda p: -rus[p].get("car", 0))[:2]:
            x = rus[p]; c = x.get("car", 0) or 1; st = CB.N._status_of(NM[p][0], inj_t)
            L.append(f"| {NM[p][0]} | 러셔 | {len(gcount[p])} | 캐리 {int(c)} | {int(x.get('yds', 0))} | {int(x.get('td', 0))}[운] | 야드/캐리 {x.get('yds', 0) / c:.1f} · 성공률 {100 * x.get('suc', 0) / c:.0f}% | {x.get('epa', 0) / c:+.2f} | 야드/캐리 {rk(upool, p)} | {st or '—'} |")
        for p in sorted((p for p in rec if NM.get(p, ("", ""))[1] == t), key=lambda p: -rec[p].get("tgt", 0))[:4]:
            x = rec[p]; tg = x.get("tgt", 0) or 1; st = CB.N._status_of(NM[p][0], inj_t)
            L.append(f"| {NM[p][0]} | 리시버 | {len(gcount[p])} | 타깃 {int(tg)} · 캐치 {int(x.get('cmp', 0))} | {int(x.get('yds', 0))} | {int(x.get('td', 0))}[운] | 캐치율 {100 * x.get('cmp', 0) / tg:.0f}% · 야드/타깃 {x.get('yds', 0) / tg:.1f} | {x.get('epa', 0) / tg:+.2f} | 야드/타깃 {rk(rpool, p)} | {st or '—'} |")
        nm = DK.get(t, "")
        mine = [r for r in KS if nm and N._same_person(r["kicker"], nm)]
        if mine:
            fa = sum(int(r[f"fg{i}_att"]) for r in mine for i in range(3)); fm = sum(int(r[f"fg{i}_made"]) for r in mine for i in range(3))
            la, lm = sum(int(r["fg2_att"]) for r in mine), sum(int(r["fg2_made"]) for r in mine)
            L.append(f"| {nm} | 키커 | — | FG {fm}/{fa}(2024~26) | — | — | FG {100 * fm / fa:.0f}% · 50+ {lm}/{la} | — | — | {CB.N._status_of(nm, inj_t) or '—'} |")
        L.append("")
    L.append("  ↳ [운] = TD·INT 는 해마다 안 이어지는 운 지표(근거 금지). 효율·EPA 는 실력 쪽. 표본이 「표본 적음」이면 순위 대신 값만 참고. 결장(Out/Doubtful)인 선수는 이미 라인에 반영 — 판 시각 뒤 확정만 새 정보.")
    L.append("")
    return L


def conclusion_line(a, h, sec, inj, m, g):
    """📌 결론 재료(자동 — 2026-10-14 Paul 「MLB 처럼」 · MLB A9 방식). sec = 이 경기 절에 이미 쌓인 줄들(🔮·📊·🧑‍🤝‍🧑·라인 이동).
    발행 세션은 팀 비교·선수 비교·변수·정리를 이 재료로 푼다 — 재계산·지어내기 방지."""
    import re
    txt = "\n".join(sec)
    out = []
    mp = re.search(r"이길 팀 \*\*([A-Z]{2,3}) (\d+)% (★+)\*\*.*?예상 점수 \*\*([A-Z]{2,3}) ([\d.]+) – ([A-Z]{2,3}) ([\d.]+)\*\*", txt)
    if mp:
        out.append(f"이길 팀 {mp.group(1)} {mp.group(2)}% {mp.group(3)}(10판: 예상 점수·방향·스프레드/총점 판단은 쓰지 않는다 — ML 전용)")
    # 스탯 격차 상위 3 — 📊 표 행에서 32팀 순위 차
    gaps = []
    for ln in sec:
        mm = re.match(r"\| ([^|]+?) \| ([^|]*?(\d+)위[^|]*) \| ([^|]*?(\d+)위[^|]*) \|", ln)
        if mm and not mm.group(1).startswith(("QB", "주요 선수", "OL", "키커", "항목")):
            lab = mm.group(1).strip(); ra, rh = int(mm.group(3)), int(mm.group(5))
            ca, ch = mm.group(2).strip(), mm.group(4).strip()
            gaps.append((abs(ra - rh), f"{lab}: {a} {ca} vs {h} {ch} — {gap_label(ra, rh, a, h)}"))
    gaps.sort(key=lambda x: -x[0])
    if gaps:
        out.append("스탯 격차 상위 3(32팀 순위 차 순): " + " / ".join(x[1] for x in gaps[:3]))
    # 선수 핵심 — 🧑‍🤝‍🧑 표
    pl = {}
    cur = None
    for ln in sec:
        hm = re.match(r"\| ([A-Z]{2,3}) 선수 \|", ln)
        if hm:
            cur = hm.group(1); pl[cur] = {"qb": None, "rec": None, "rush": None}; continue
        if cur and ln.startswith("|") and not ln.startswith("|---"):
            c = [x.strip() for x in ln.strip().strip("|").split("|")]
            if len(c) < 10:
                continue
            nm, role, st = c[0], c[1], c[9]
            tag = f"{nm}" + (f"({st})" if st and st != "—" else "")
            if role == "QB" and pl[cur]["qb"] is None:
                pl[cur]["qb"] = f"{tag} {c[8]}"
            elif role == "리시버" and pl[cur]["rec"] is None:
                pl[cur]["rec"] = f"{tag} {c[3].split('·')[0].strip()} · {c[8]}"
            elif role == "러셔" and pl[cur]["rush"] is None:
                pl[cur]["rush"] = f"{tag} {c[3]} · {c[8]}"
    if pl.get(a) and pl.get(h):
        out.append("선수 핵심: QB " + f"{a} {pl[a]['qb'] or '—'} vs {h} {pl[h]['qb'] or '—'}"
                   + f" · 타깃 1위 {a} {pl[a]['rec'] or '—'} vs {h} {pl[h]['rec'] or '—'}"
                   + f" · 캐리 1위 {a} {pl[a]['rush'] or '—'} vs {h} {pl[h]['rush'] or '—'}")
    # ★주전 결장·새 정보 후보
    ia, ih = inj.get(a) or {}, inj.get(h) or {}
    _ina = re.search(r"- 🏥 결장 명단\(ESPN 공식 비활성 · 발표 (\S+) PT[^)]*\): .*?★주전 결장 ([A-Z]{2,3}) (\d+) / ([A-Z]{2,3}) (\d+)", txt)
    out.append(f"★주전 Out/Doubtful {a} {ia.get('n_starters_missing') or 0}명 / {h} {ih.get('n_starters_missing') or 0}명"
               + (f" · 공식 비활성(ESPN {_ina.group(1)} PT 발표): ★주전 {_ina.group(2)} {_ina.group(3)} / {_ina.group(4)} {_ina.group(5)} — 🏥 줄 그대로" if _ina else
                  (" · ⚠️ 최종 지정 미발표(연습 보고) — 웹 확인 필수" if ia.get("final_pending") or ih.get("final_pending") else " · 공식 비활성 미발표(🏥 줄)")))
    cand = []
    for t, x in ((a, ia), (h, ih)):
        for key in ("questionable", "doubtful"):
            # 항목 = 「이름(포지션 · ★스냅 nn%)」 — 괄호 안에도 「 · 」가 있어 「) · 」 경계로 나눈다(2026-10-15 「DEN ★스냅 76%)(Q)」 오기 수정)
            for nm in [y.strip() for y in re.split(r"\)\s*·\s*", str(x.get(key) or "")) if "★" in y]:
                cand.append(f"{t} {nm.split('(')[0].strip()}({key[0].upper()})")
    out.append("새 정보 후보(판 시각 뒤 결장 확정되면 새 정보 — ★주전 Q/Doubtful): " + (", ".join(cand[:6]) if cand else "없음"))
    _ag = next((ln for ln in sec if ln.startswith("- 🔎 관찰 각도")), "")
    if _ag:
        _body = _ag.split("): ", 1)[1].split(" ← ")[0] if "): " in _ag else ""
        out.append("관찰 각도(페이퍼): " + (" / ".join(x.split(" — ")[0] for x in _body.split(" / ")) if _body and "해당 없음" not in _ag else "없음"))
    lm = next((ln for ln in sec if ln.startswith("- 라인 이동:")), "")
    if lm:
        out.append(lm[2:].split(" (")[0])
    obs = [x for x in (m.get("spread_grade", ""), m.get("total_grade", "")) if "관찰" in str(x)]
    if obs:
        out.append("로컬 페이퍼 관찰 있음(돈 아님): " + " · ".join(obs))
    return ["- 📌 **결론 재료(자동 — 10판 ML 전용 · MLB A9 방식 · 발행 세션은 팀 비교·선수 비교·변수·정리를 이 재료로 푼다, 값 재계산 금지)**: " + " · ".join(out), ""]


def build(a, h, RS, PRO, rt, inj, g):
    """→ 다이제스트 줄 목록. RS = stat_research.load() 결과, PRO = _team_profile(), rt = ratings dict."""
    L = ["- 📊 **스탯 비교(말로 — 발행문 「- 스탯 비교:」에 줄 단위로 옮긴다 · 2026 정규시즌 · 32팀 순위 · 상위 1~10 / 중간 11~22 / 하위 23~32 · 수비는 적게 내줄수록 높은 순위 · 점수 0, 시장이 이미 반영 · 격차 열 = 순위 차 0~4 차이 없음 / 5~9 근접 / 10~15 경미 / 16+ 중대 · 괄호 = 2024~25 그 등급일 때 순위 높은 팀이 실제 이긴 비율와 시장이 준 확률(둘이 비슷 = 시장이 이미 반영) — 서술 전용, 확률·별점 영향 0)**:", "",
         f"| 항목 | {a} | {h} | 뜻 | 격차(서술 전용 · 실측 승률/시장) |", "|---|---|---|---|---|"]
    S = CB.standings()
    pf = {t: (S[t]["pf"] / (S[t]["w"] + S[t]["l"] + S[t]["t"])) if (S[t]["w"] + S[t]["l"] + S[t]["t"]) else None for t in CB.DIV}
    pa = {t: (S[t]["pa"] / (S[t]["w"] + S[t]["l"] + S[t]["t"])) if (S[t]["w"] + S[t]["l"] + S[t]["t"]) else None for t in CB.DIV}
    L.append(f"| 득점(경기당) | {cell(pf, a, '{:.1f}', True, '점')} | {cell(pf, h, '{:.1f}', True, '점')} | 한 경기에 넣는 점수 | {gap(pf, a, h, True, '득점(경기당)')} |")
    L.append(f"| 실점(경기당) | {cell(pa, a, '{:.1f}', False, '점')} | {cell(pa, h, '{:.1f}', False, '점')} | 한 경기에 내주는 점수(적을수록 좋음) | {gap(pa, a, h, False, '실점(경기당)')} |")
    summ = []
    if RS:
        T, P, NM = RS
        off, de = defaultdict(list), defaultdict(list)
        for (gid, wk, pt, dt), x in T.items():
            off[pt].append(x); de[dt].append(x)

        def ppd(rows):
            d = sum(r.get("dr", 0) for r in rows)
            return sum(r.get("dr_pts", 0) for r in rows) / d if d else None

        def scp(rows):
            d = sum(r.get("dr", 0) for r in rows)
            return 100 * sum(r.get("dr_td", 0) + r.get("dr_fg", 0) for r in rows) / d if d else None
        oppd = {t: ppd(off[t]) for t in CB.DIV}; dppd = {t: ppd(de[t]) for t in CB.DIV}
        osc = {t: scp(off[t]) for t in CB.DIV}; dsc = {t: scp(de[t]) for t in CB.DIV}
        L.append(f"| 공격 효율(드라이브당 득점) | {cell(oppd, a, '{:.2f}')} | {cell(oppd, h, '{:.2f}')} | 공을 잡고 한 번 공격할 때 평균 몇 점 — 실력 지표(r .61) | {gap(oppd, a, h, True, '공격 효율(드라이브당 득점)')} |")
        L.append(f"| 득점 드라이브 비율 | {cell(osc, a, '{:.0f}', True, '%')} | {cell(osc, h, '{:.0f}', True, '%')} | 공격 10번 중 몇 번 점수(TD+FG)를 내나 | {gap(osc, a, h, True, '득점 드라이브 비율')} |")
        L.append(f"| 수비 효율(내준 드라이브당 득점) | {cell(dppd, a, '{:.2f}', False)} | {cell(dppd, h, '{:.2f}', False)} | 상대 공격 한 번에 평균 몇 점을 내주나 | {gap(dppd, a, h, False, '수비 효율(내준 드라이브당 득점)')} |")
        L.append(f"| 상대 득점 드라이브 허용 | {cell(dsc, a, '{:.0f}', False, '%')} | {cell(dsc, h, '{:.0f}', False, '%')} | 상대 공격 10번 중 몇 번 점수를 허용하나 | {gap(dsc, a, h, False, '상대 득점 드라이브 허용')} |")
        for t, lab in ((a, a), (h, h)):
            ro, rd_ = _rank(oppd, t), _rank(dppd, t, False)
            if ro and rd_:
                summ.append(f"{lab} 공격 {tier(ro)}({ro}위) · 수비 {tier(rd_)}({rd_}위)")
    if PRO:
        def pv(key):
            return {t: PRO[t].get(key) for t in PRO}
        rows = (("패스 공격(드롭백당 EPA)", "o_pepa", True, "{:+.3f}", "패스 한 번이 점수 기대치를 얼마나 올리나(+면 평균 이상)"),
                ("러시 공격(러시당 EPA)", "o_repa", True, "{:+.3f}", "달리기 한 번의 점수 기대치"),
                ("패스 수비(허용 EPA)", "d_pepa", False, "{:+.3f}", "상대 패스에 내주는 기대치(낮을수록 좋음)"),
                ("러시 수비(허용 EPA)", "d_repa", False, "{:+.3f}", "상대 달리기에 내주는 기대치(낮을수록 좋음)"),
                ("3rd down 전환(공격)", "o_3rd", True, "{:.0%}", "3번째 시도에서 공격권을 지키는 비율"),
                ("3rd down 허용(수비)", "d_3rd", False, "{:.0%}", "상대 3번째 시도를 막지 못하는 비율(낮을수록 좋음)"),
                ("턴오버(경기당 잃음)", "o_to", False, "{:.1f}", "인터셉트·펌블로 공을 뺏기는 횟수(적을수록 좋음 · 운 지표 r .14)"),
                ("색 허용률(공격)", "o_sack", False, "{:.1%}", "QB 가 던지기 전에 잡히는 비율(낮을수록 보호가 좋음)"))
        for lab, key, high, fmt, mean in rows:
            vals = pv(key)
            L.append(f"| {lab} | {cell(vals, a, fmt, high)} | {cell(vals, h, fmt, high)} | {mean} | {gap(vals, a, h, high, lab)} |")
    # QB — 예상 선발, 드롭백 60+ QB 중 순위
    if RS:
        T, P, NM = RS
        qb = defaultdict(lambda: defaultdict(float))
        for (k, pid, gid), x in P.items():
            if k == "qb":
                for kk, vv in x.items():
                    qb[pid][kk] += vv
        pool = {pid: x for pid, x in qb.items() if x.get("db", 0) >= QB_MIN_DB}

        def qstat(pid, key):
            x = qb[pid]; att = x.get("att", 0) or 1; db = x.get("db", 0) or 1
            return {"ypa": x.get("yds", 0) / att, "cpoe": (x["cpoe"] / x["cpoe_n"]) if x.get("cpoe_n") else None,
                    "epa": x.get("epa", 0) / db, "sack": 100 * x.get("sack", 0) / db, "cmp": 100 * x.get("cmp", 0) / att,
                    "td": 100 * x.get("td", 0) / att, "int": 100 * x.get("int", 0) / att}[key]
        qcells = {}; qrank = {}
        for t in (a, h):
            exp = (inj.get(t) or {}).get("expected_qb") or ""
            pid = next((p for p in qb if exp and N._same_person(NM[p][0], exp) and NM[p][1] == t), None)
            if pid is None:
                qcells[t] = f"{exp or '?'} — 2026 기록 없음(표본 적음)"; continue
            n = len(pool)
            parts = []
            for key, lab, high, fmt in (("ypa", "야드/시도", True, "{:.1f}"), ("cpoe", "정확도 CPOE", True, "{:+.1f}"), ("epa", "EPA/드롭백", True, "{:+.2f}"), ("sack", "색%", False, "{:.1f}")):
                v = qstat(pid, key)
                if v is None:
                    continue
                if pid in pool:
                    vals = {p: qstat(p, key) for p in pool}
                    r = _rank(vals, pid, high)
                    parts.append(f"{lab} {fmt.format(v)}({r}/{n}위·{tier(r, n)})")
                else:
                    parts.append(f"{lab} {fmt.format(v)}(표본 적음)")
            db = int(qb[pid].get("db", 0))
            qcells[t] = f"{NM[pid][0]} · 드롭백 {db}" + (" ※ 얇음" if db < N.THIN_QB_DB else "") + " · " + " · ".join(parts)
            if pid in pool:
                r = _rank({p: qstat(p, "epa") for p in pool}, pid, True); qrank[t] = r
                summ.append(f"{t} QB {NM[pid][0]} EPA {tier(r, len(pool))}({r}/{len(pool)}위)")
        L.append(f"| QB(예상 선발 · 순위는 드롭백 {QB_MIN_DB}+ QB 중) | {qcells[a]} | {qcells[h]} | 야드/시도·EPA 는 실력(r .47~.48), 정확도 CPOE 는 중간, INT 는 운 | {gap_label(qrank.get(a), qrank.get(h), a, h, len(pool)) + (' (EPA 순위)' if a in qrank and h in qrank else '')} |")
        # 주요 선수 — 리시버 2·러셔 1, 리그 전체 자격자 중 순위
        rec = defaultdict(lambda: defaultdict(float)); rus = defaultdict(lambda: defaultdict(float))
        for (k, pid, gid), x in P.items():
            if k == "rec":
                for kk, vv in x.items(): rec[pid][kk] += vv
            elif k == "rush":
                for kk, vv in x.items(): rus[pid][kk] += vv
        rpool = {p: x["yds"] / x["tgt"] for p, x in rec.items() if x.get("tgt", 0) >= WR_MIN_TGT}
        upool = {p: x["yds"] / x["car"] for p, x in rus.items() if x.get("car", 0) >= RB_MIN_CAR}

        def players(t):
            out = []
            tops = sorted((p for p in rec if NM.get(p, ("", ""))[1] == t), key=lambda p: -rec[p].get("tgt", 0))[:2]
            for p in tops:
                x = rec[p]; tg = x.get("tgt", 0) or 1; st = CB.N._status_of(NM[p][0], inj.get(t, {}))
                ypt = x.get("yds", 0) / tg
                rk = f"{_rank(rpool, p)}/{len(rpool)}위·{tier(_rank(rpool, p), len(rpool))}" if p in rpool else "표본 적음"
                ex = AP.receiver_extra(NM[p][0])
                out.append(f"{NM[p][0]}{'⚠️' + st if st else ''} 타깃 {int(tg)} · 야드/타깃 {ypt:.1f}({rk}) · 캐치율 {100 * x.get('cmp', 0) / tg:.0f}%" + (f" · {ex}" if ex else ""))
            top = max((p for p in rus if NM.get(p, ("", ""))[1] == t), key=lambda p: rus[p].get("car", 0), default=None)
            if top:
                x = rus[top]; c = x.get("car", 0) or 1; st = CB.N._status_of(NM[top][0], inj.get(t, {}))
                rk = f"{_rank(upool, top)}/{len(upool)}위·{tier(_rank(upool, top), len(upool))}" if top in upool else "표본 적음"
                ex = AP.rusher_extra(NM[top][0])
                out.append(f"{NM[top][0]}{'⚠️' + st if st else ''} 캐리 {int(c)} · 야드/캐리 {x.get('yds', 0) / c:.1f}({rk}) · 성공률 {100 * x.get('suc', 0) / c:.0f}%" + (f" · {ex}" if ex else ""))
            return " / ".join(out) or "—"
        L.append(f"| 주요 선수(리시버 2·러셔 1 · 순위는 타깃 {WR_MIN_TGT}+/캐리 {RB_MIN_CAR}+ 선수 중) | {players(a)} | {players(h)} | ⚠️ = 부상 보고 상태 · 캐치율은 실력(r .50), TD 는 운 · [ ] 안 r = 2024~25 홀/짝 주 안정성(실력 ≥.45 / 중간 / 운 <.25 — 운 지표(드롭·태클 깨기·기대 대비 러시 야드)는 근거 금지) | — |")
        try:
            wk_ = int(str(g.get("game_id", "")).split("_")[1])
        except (IndexError, ValueError):
            wk_ = 0
        L.append(f"| OL 연속성(최근 3경기 공격 스냅 상위 5명) | {AP.ol_continuity(a, inj.get(a), wk_)} | {AP.ol_continuity(h, inj.get(h), wk_)} | 오펜스 라인 주전이 몇 명 빠지나 — 2006~25 OL 2명+ 결장 ATS 45.2%(우연 범위, 시장 반영) | — |")
    # 키커
    DK = CB._depth_kicker(); KS = CB.kicker_stats()
    kpct = {}
    for r in KS:
        att = sum(int(r[f"fg{i}_att"]) for i in range(3)); md = sum(int(r[f"fg{i}_made"]) for i in range(3))
        k = kpct.setdefault(r["kicker"], [0, 0]); k[0] += md; k[1] += att
    kpool = {k: v[0] / v[1] for k, v in kpct.items() if v[1] >= 20}

    def kick(t):
        nm = DK.get(t, "")
        mine = [r for r in KS if nm and N._same_person(r["kicker"], nm)]
        if not mine:
            return f"{nm or '?'} — 기록 없음"
        key = mine[0]["kicker"]; md, att = kpct[key]
        l50a = sum(int(r["fg2_att"]) for r in mine); l50m = sum(int(r["fg2_made"]) for r in mine)
        rk = f"{_rank(kpool, key)}/{len(kpool)}위·{tier(_rank(kpool, key), len(kpool))}" if key in kpool else "표본 적음"
        return f"{nm} FG {100 * md / att:.0f}%({md}/{att} · {rk}) · 50야드+ {100 * l50m / l50a if l50a else 0:.0f}%({l50m}/{l50a})"
    L.append(f"| 키커(2024~26 FG 성공률 · 순위는 20킥+ 키커 중) | {kick(a)} | {kick(h)} | FG 하나가 3점 — 실외 강풍·추위면 40야드 밖 성공률이 떨어진다 | — |")
    L += ["", "  ↳ 한 줄: " + (" · ".join(summ) if summ else "—") + " — 순위는 2026 전체(얇은 표본 주의). 이 표는 시장 라인에 이미 들어간 정보라 예측 확률을 바꾸지 않는다(초등학생 설명 재료).", ""]
    return L
