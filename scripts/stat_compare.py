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


def cell(vals, t, fmt, high=True, unit="", n=None):
    v = vals.get(t)
    if v is None:
        return "—"
    r = _rank(vals, t, high); n = n or len([x for x in vals.values() if x is not None])
    return f"{fmt.format(v)}{unit} · {r}위({tier(r, n)})"


def build(a, h, RS, PRO, rt, inj, g):
    """→ 다이제스트 줄 목록. RS = stat_research.load() 결과, PRO = _team_profile(), rt = ratings dict."""
    L = ["- 📊 **스탯 비교(말로 — 발행문 「- 스탯 비교:」에 줄 단위로 옮긴다 · 2026 정규시즌 · 32팀 순위 · 상위 1~10 / 중간 11~22 / 하위 23~32 · 수비는 적게 내줄수록 높은 순위 · 점수 0, 시장이 이미 반영)**:", "",
         f"| 항목 | {a} | {h} | 뜻 |", "|---|---|---|---|"]
    S = CB.standings()
    pf = {t: (S[t]["pf"] / (S[t]["w"] + S[t]["l"] + S[t]["t"])) if (S[t]["w"] + S[t]["l"] + S[t]["t"]) else None for t in CB.DIV}
    pa = {t: (S[t]["pa"] / (S[t]["w"] + S[t]["l"] + S[t]["t"])) if (S[t]["w"] + S[t]["l"] + S[t]["t"]) else None for t in CB.DIV}
    L.append(f"| 득점(경기당) | {cell(pf, a, '{:.1f}', True, '점')} | {cell(pf, h, '{:.1f}', True, '점')} | 한 경기에 넣는 점수 |")
    L.append(f"| 실점(경기당) | {cell(pa, a, '{:.1f}', False, '점')} | {cell(pa, h, '{:.1f}', False, '점')} | 한 경기에 내주는 점수(적을수록 좋음) |")
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
        L.append(f"| 공격 효율(드라이브당 득점) | {cell(oppd, a, '{:.2f}')} | {cell(oppd, h, '{:.2f}')} | 공을 잡고 한 번 공격할 때 평균 몇 점 — 실력 지표(r .61) |")
        L.append(f"| 득점 드라이브 비율 | {cell(osc, a, '{:.0f}', True, '%')} | {cell(osc, h, '{:.0f}', True, '%')} | 공격 10번 중 몇 번 점수(TD+FG)를 내나 |")
        L.append(f"| 수비 효율(내준 드라이브당 득점) | {cell(dppd, a, '{:.2f}', False)} | {cell(dppd, h, '{:.2f}', False)} | 상대 공격 한 번에 평균 몇 점을 내주나 |")
        L.append(f"| 상대 득점 드라이브 허용 | {cell(dsc, a, '{:.0f}', False, '%')} | {cell(dsc, h, '{:.0f}', False, '%')} | 상대 공격 10번 중 몇 번 점수를 허용하나 |")
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
            L.append(f"| {lab} | {cell(vals, a, fmt, high)} | {cell(vals, h, fmt, high)} | {mean} |")
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
        qcells = {}
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
                r = _rank({p: qstat(p, "epa") for p in pool}, pid, True)
                summ.append(f"{t} QB {NM[pid][0]} EPA {tier(r, len(pool))}({r}/{len(pool)}위)")
        L.append(f"| QB(예상 선발 · 순위는 드롭백 {QB_MIN_DB}+ QB 중) | {qcells[a]} | {qcells[h]} | 야드/시도·EPA 는 실력(r .47~.48), 정확도 CPOE 는 중간, INT 는 운 |")
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
        L.append(f"| 주요 선수(리시버 2·러셔 1 · 순위는 타깃 {WR_MIN_TGT}+/캐리 {RB_MIN_CAR}+ 선수 중) | {players(a)} | {players(h)} | ⚠️ = 부상 보고 상태 · 캐치율은 실력(r .50), TD 는 운 · [ ] 안 r = 2024~25 홀/짝 주 안정성(실력 ≥.45 / 중간 / 운 <.25 — 운 지표(드롭·태클 깨기·기대 대비 러시 야드)는 근거 금지) |")
        try:
            wk_ = int(str(g.get("game_id", "")).split("_")[1])
        except (IndexError, ValueError):
            wk_ = 0
        L.append(f"| OL 연속성(최근 3경기 공격 스냅 상위 5명) | {AP.ol_continuity(a, inj.get(a), wk_)} | {AP.ol_continuity(h, inj.get(h), wk_)} | 오펜스 라인 주전이 몇 명 빠지나 — 2006~25 OL 2명+ 결장 ATS 45.2%(우연 범위, 시장 반영) |")
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
    L.append(f"| 키커(2024~26 FG 성공률 · 순위는 20킥+ 키커 중) | {kick(a)} | {kick(h)} | FG 하나가 3점 — 실외 강풍·추위면 40야드 밖 성공률이 떨어진다 |")
    L += ["", "  ↳ 한 줄: " + (" · ".join(summ) if summ else "—") + " — 순위는 2026 전체(얇은 표본 주의). 이 표는 시장 라인에 이미 들어간 정보라 예측 확률을 바꾸지 않는다(초등학생 설명 재료).", ""]
    return L
