"""NFL 픽 추적기(xlsx) — 정본은 data/picks.csv, 이 파일은 보기용으로 매번 다시 만든다(손으로 고치지 말 것).
  python tracker_xlsx.py  → data/NFL_픽_추적기.xlsx (시트: 픽로그 · 적중률 · 주별 · 경기별 · 예측 요약 · 팀별)
경기별·예측 요약·팀별(2026-11-15 Paul 「mlb처럼 팀별로 추적기 · 스프레드도 · 다 소급」) — 원본 = data/2026-wNN/predictions.csv(시장·모델·발행) + model.csv.
승자 예측 = 정식 발행(킥오프 뒤 기록용 제외) · 발행 기록이 없던 주는 시장 승자로 소급(지금 시스템 = 시장 값). 스프레드 픽(소급·기록용 · 돈 아님) = 모델 기대 마진이 스프레드보다 유리하게 보는 쪽."""
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
import csv
import glob
import os
import re
from collections import defaultdict

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(os.path.dirname(HERE), "data")
PICKS = os.path.join(DATA, "picks.csv"); OUT = os.path.join(DATA, "NFL_픽_추적기.xlsx")
COLS = [("주차", "week"), ("경기", "game"), ("시장", "market"), ("쪽", "side"), ("라인", "line"), ("배당", "odds"), ("구분", "status"),
        ("등급", "grade"), ("모델값", "model_value"), ("엣지", "edge"), ("승률(모델)", "p_win"), ("결과", "result"), ("스코어", "score"),
        ("유닛", "units"), ("베팅 시각", "placed_at"), ("메모", "note"), ("id", "id")]


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def rec(xs):
    w = sum(1 for x in xs if x["result"] == "W"); l = sum(1 for x in xs if x["result"] == "L"); p = sum(1 for x in xs if x["result"] == "P")
    u = sum(fnum(x["units"]) or 0 for x in xs)
    return [len(xs), w, l, p, round(100 * w / (w + l), 1) if w + l else None, round(u, 2)]


STAR_CUTS = ((0.75, 4), (0.65, 3), (0.57, 2), (0.0, 1))   # predictions.STAR_CUTS 와 같은 값
G_HDR = ["주차", "경기", "시장 승자", "시장 %", "발행 예측", "발행 %", "★", "기록 시각", "구분", "결과(승자)", "점수", "발행 적중",
         "스프레드(홈)", "모델 마진(홈)", "차(모델−시장)", "스프레드 픽", "실제 마진(홈)", "스프레드 결과", "예측 승자 커버"]
T_HDR = ["팀", "팀 전적", "승자로 예측 W-L", "적중%", "상대를 승자로 예측 W-L", "적중%", "이 팀 경기 예측 합", "적중%",
         "팀 스프레드 성적 W-L(-P)", "커버%", "스프레드 픽 = 이 팀 W-L(-P)", "적중%", "스프레드 픽 = 상대 W-L(-P)", "적중%",
         "승자로 예측했을 때 커버 W-L(-P)", "커버%", "비고"]


def game_rows():
    """경기별 한 행 — 승자 예측(정식 발행 · 없던 주는 시장 승자 소급) + 스프레드 픽(모델 마진 쪽 · 소급 · 기록용)."""
    G = {}
    for p in sorted(glob.glob(os.path.join(DATA, "*-w*", "predictions.csv"))):
        for x in csv.DictReader(open(p, encoding="utf-8-sig", newline="")):
            G.setdefault(x["game_id"], {"week": int(x["week"]), "game": x["game"]})[x["src"]] = x
    for p in glob.glob(os.path.join(DATA, "*-w*", "model.csv")):   # 모델 예측 행이 빠진 주(4주차 등)의 보충 원천
        for x in csv.DictReader(open(p, encoding="utf-8-sig", newline="")):
            if x.get("game_id") in G:
                G[x["game_id"]]["_model"] = x
    out = []
    for gid, d in G.items():
        a, h = d["game"].split("@")
        mk, md, pb, mc = d.get("시장", {}), d.get("모델", {}), d.get("발행", {}), d.get("_model", {})
        fin = next((x["final"] for x in (mk, md, pb) if x.get("final")), "")
        m = re.match(r"\S+ ([\d.]+)-([\d.]+) \S+", fin)
        act = (float(m.group(2)) - float(m.group(1))) if m else None
        win = "" if act is None or act == 0 else (h if act > 0 else a)
        if pb:
            pw, pp, kind, at = pb.get("pick", ""), fnum(pb.get("p_pick")), ("기록용(킥오프 뒤)" if pb.get("flag") else "정식"), pb.get("made_at", "")
        else:
            pw, pp, kind, at = mk.get("pick", ""), fnum(mk.get("p_pick")), "소급(시장 값)", ""
        hit = "" if not win or not pw or kind.startswith("기록용") else ("W" if pw == win else "L")
        sp = next((v for v in (fnum(mk.get("line_home")), fnum(md.get("line_home")), fnum(mc.get("mkt_spread_home"))) if v is not None), None)
        sa, sh = fnum(md.get("score_away")), fnum(md.get("score_home"))
        mm = (sh - sa) if sa is not None and sh is not None else fnum(mc.get("model_margin_home"))
        cov = (act + sp) if act is not None and sp is not None else None      # + = 홈 커버
        diff, side, sres = "", "", ""
        if sp is not None and mm is not None:
            diff = round(mm + sp, 1)
            if diff:
                side, line = (h, sp) if diff > 0 else (a, -sp)
                sres = "" if cov is None else ("P" if cov == 0 else ("W" if (cov > 0) == (side == h) else "L"))
                side_txt = f"{side} {line:+g}"
        fc = "" if cov is None or pw not in (a, h) else ("P" if cov == 0 else ("W" if (cov > 0) == (pw == h) else "L"))
        out.append({"주차": d["week"], "경기": d["game"], "시장 승자": mk.get("pick", ""), "시장 %": round(100 * fnum(mk.get("p_pick"))) if fnum(mk.get("p_pick")) is not None else "",
                    "발행 예측": pw, "발행 %": round(100 * pp) if pp is not None else "", "★": "★" * next(n for c, n in STAR_CUTS if pp >= c) if pp is not None else "",
                    "기록 시각": at, "구분": kind, "결과(승자)": win, "점수": fin, "발행 적중": hit,
                    "스프레드(홈)": sp if sp is not None else "", "모델 마진(홈)": round(mm, 1) if mm is not None else "", "차(모델−시장)": diff,
                    "스프레드 픽": side_txt if side else "", "실제 마진(홈)": act if act is not None else "", "스프레드 결과": sres, "예측 승자 커버": fc,
                    "_a": a, "_h": h, "_side": side, "_cov": cov})
    out.sort(key=lambda r: (r["주차"], r["경기"]))
    return out


def team_table(rows):
    T = defaultdict(lambda: defaultdict(int))
    for r in rows:
        a, h, win = r["_a"], r["_h"], r["결과(승자)"]
        if not win:
            continue
        for t in (a, h):
            T[t]["w" if win == t else "l"] += 1
        if r["발행 적중"] in ("W", "L") and r["발행 예측"] in (a, h):
            pw = r["발행 예측"]; opp = h if pw == a else a
            T[pw]["for_" + r["발행 적중"]] += 1; T[opp]["ag_" + r["발행 적중"]] += 1
            if r["예측 승자 커버"]:
                T[pw]["fc_" + r["예측 승자 커버"]] += 1
        cov = r["_cov"]
        if cov is not None:
            T[h]["ats_" + ("P" if cov == 0 else "W" if cov > 0 else "L")] += 1; T[a]["ats_" + ("P" if cov == 0 else "W" if cov < 0 else "L")] += 1
        if r["스프레드 결과"]:
            s = r["_side"]; o = h if s == a else a
            T[s]["sp_" + r["스프레드 결과"]] += 1; T[o]["spo_" + r["스프레드 결과"]] += 1

    def pct(w, l):
        return round(100 * w / (w + l), 1) if w + l else None

    def wlp(d, k):
        return f'{d[k + "_W"]}-{d[k + "_L"]}' + (f'-{d[k + "_P"]}' if d[k + "_P"] else "")
    out = []
    for t in sorted(T):
        d = T[t]; n = d["for_W"] + d["for_L"] + d["ag_W"] + d["ag_L"]
        out.append([t, f'{d["w"]}-{d["l"]}', f'{d["for_W"]}-{d["for_L"]}', pct(d["for_W"], d["for_L"]), f'{d["ag_W"]}-{d["ag_L"]}', pct(d["ag_W"], d["ag_L"]),
                    f'{d["for_W"] + d["ag_W"]}-{d["for_L"] + d["ag_L"]}', pct(d["for_W"] + d["ag_W"], d["for_L"] + d["ag_L"]),
                    wlp(d, "ats"), pct(d["ats_W"], d["ats_L"]), wlp(d, "sp"), pct(d["sp_W"], d["sp_L"]), wlp(d, "spo"), pct(d["spo_W"], d["spo_L"]),
                    wlp(d, "fc"), pct(d["fc_W"], d["fc_L"]), "표본 적음" if n < 5 else ""])
    return out


def pred_sheets(wb, head, fill):
    rows = game_rows()
    g = wb.create_sheet("경기별"); g.append(G_HDR)
    for c in g[1]:
        c.font = head; c.fill = fill
    for r in rows:
        g.append([r[k] for k in G_HDR])
    for i, k in enumerate(G_HDR, 1):
        g.column_dimensions[get_column_letter(i)].width = {"경기": 11, "기록 시각": 13, "구분": 16, "점수": 16, "스프레드 픽": 12}.get(k, 9)
    g.freeze_panes = "C2"
    for col in ("발행 적중", "스프레드 결과", "예측 승자 커버"):
        ci = G_HDR.index(col)
        for row in g.iter_rows(min_row=2):
            v = row[ci].value
            if v in ("W", "L"):
                row[ci].fill = PatternFill("solid", fgColor="C6EFCE" if v == "W" else "FFC7CE")

    def wlp(rs, k):
        w, l, p = (sum(1 for r in rs if r[k] == x) for x in ("W", "L", "P"))
        return [len(rs), f"{w}-{l}" + (f"-{p}" if p else ""), round(100 * w / (w + l), 1) if w + l else None]
    s = wb.create_sheet("예측 요약"); s.append(["구분", "경기", "W-L(-P)", "적중률%", "비고"])
    for c in s[1]:
        c.font = head; c.fill = fill
    done = [r for r in rows if r["발행 적중"] in ("W", "L")]
    s.append(["승자 예측 전체(정식 + 소급)"] + wlp(done, "발행 적중") + ["정식 발행(킥오프 뒤 기록용 제외) + 발행 기록 없던 주는 시장 승자 소급"])
    s.append(["  정식 발행만"] + wlp([r for r in done if r["구분"] == "정식"], "발행 적중") + [""])
    s.append(["  소급(시장 값)"] + wlp([r for r in done if r["구분"].startswith("소급")], "발행 적중") + ["지금 시스템(발행 = 시장 값)을 적용했다면"])
    for n in (4, 3, 2, 1):
        s.append([f"  {'★' * n}"] + wlp([r for r in done if r["★"] == "★" * n], "발행 적중") + [""])
    s.append([])
    spr = [r for r in rows if r["스프레드 결과"]]
    s.append(["스프레드 픽 전체(소급 · 기록용)"] + wlp(spr, "스프레드 결과") + ["모델 기대 마진이 스프레드보다 유리하게 보는 쪽 · 손익분기 52.4% · 돈 아님"])
    for lab, lo, hi in (("차 1점 미만", 0, 1), ("차 1~2점", 1, 2), ("차 2~3.5점", 2, 3.5), ("차 3.5~5점", 3.5, 5), ("차 5점+", 5, 99)):
        s.append([f"  {lab}"] + wlp([r for r in spr if lo <= abs(r["차(모델−시장)"]) < hi], "스프레드 결과") + [""])
    s.append(["예측 승자가 스프레드도 넘김"] + wlp([r for r in done if r["예측 승자 커버"]], "예측 승자 커버") + ["승자 예측 쪽 스프레드 성적(값만)"])
    s.column_dimensions["A"].width = 30; s.column_dimensions["C"].width = 12; s.column_dimensions["E"].width = 70
    t = wb.create_sheet("팀별"); t.append(T_HDR)
    for c in t[1]:
        c.font = head; c.fill = fill; c.alignment = Alignment(horizontal="center", wrap_text=True)
    for row in team_table(rows):
        t.append(row)
    t.append([]); t.append(["읽는 법", "승자 예측 = 정식 발행 + 소급(시장 값) · 스프레드 = DK 마감(소급 주)·기록 시점 홈 라인 · 스프레드 픽 = 모델 마진 쪽(소급 · 기록용 · 돈 아님) · 1주차는 모델 기록이 없어 스프레드 픽 없음 · 5경기 미만 표본 적음"])
    t.freeze_panes = "B2"; t.row_dimensions[1].height = 44
    for i in range(1, len(T_HDR) + 1):
        t.column_dimensions[get_column_letter(i)].width = 7 if i == 1 else 12
    return rows


def main():
    rows = list(csv.DictReader(open(PICKS, encoding="utf-8-sig", newline=""))) if os.path.exists(PICKS) else []
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "픽로그"
    head = Font(bold=True); fill = PatternFill("solid", fgColor="DDEBF7")
    ws.append([c for c, _ in COLS])
    for c in ws[1]:
        c.font = head; c.fill = fill
    for r in sorted(rows, key=lambda r: (int(r["week"]), r["game"], r["market"])):
        vals = []
        for _, k in COLS:
            v = r.get(k, "")
            if k in ("week",):
                v = int(v)
            elif k in ("line", "model_value", "edge", "p_win", "units") and fnum(v) is not None:
                v = fnum(v)
            vals.append(v)
        ws.append(vals)
    for i, (c, k) in enumerate(COLS, 1):
        ws.column_dimensions[get_column_letter(i)].width = {"game": 11, "side": 12, "grade": 16, "status": 10, "score": 16, "note": 60, "id": 26, "placed_at": 17}.get(k, 9)
    ws.freeze_panes = "A2"
    # 적중률
    s2 = wb.create_sheet("적중률")
    s2.append(["구분", "픽", "승", "패", "푸시", "적중률%", "유닛", "설명"])
    done = [r for r in rows if r["result"] in ("W", "L", "P")]
    placed = [r for r in done if r["status"] == "placed"]
    pub = [r for r in done if r["grade"].startswith("관심(발행)")]
    lean_ = [r for r in done if r["grade"].startswith("방향(발행)")]
    model = [r for r in done if r["status"] != "placed" and r["grade"].startswith(("관찰", "참고"))]
    s2.append(["실베팅(placed)"] + rec(placed) + ["Paul 이 실제로 건 것 — 손익분기 52.4%"])
    s2.append(["발행 판단(페이퍼)"] + rec(pub) + ["발행 세션 관심·소액 관심(9/29~)"])
    _ld = rec(lean_); _ld[4] = None                        # 2026-10-05: 방향은 동전(돈 아님) — 유닛 칸 비움, 적중률만
    s2.append(["발행 방향(예측 쪽)"] + _ld + ["발행 세션 방향 줄 — 예측 점수에서 나온 쪽(10/1~). 2018~25 어떤 별점에서도 스프레드 ≈49% = 동전 · 유닛 미표시"])
    s2.append(["모델 관찰·참고(페이퍼)"] + rec(model) + ["EPA 모델 방향 — 백테스트 45%, 검증용"])
    tz = [r for r in done if r["grade"] == "티저 다리(관찰)"]
    pr = [fnum(r["odds"]) for r in tz if "표시가" in r["note"] and fnum(r["odds"])]
    avg_c = (sum((-o / (100 - o) if o < 0 else 100 / (o + 100)) for o in pr) / len(pr) * 100) if pr else None
    s2.append(["티저 다리(관찰·페이퍼 — 10/10 폐지, 기록만)"] + rec(tz) + [f"웡 티저 다리(10/1~10/10 · Paul 「티저는 별로」로 적립 중단) — 손익분기 73.9%(−120 2팀 환산)"
                                                + (f" · 평균 표시가 {avg_c:.1f}c(n {len(pr)})" if pr else "")])
    wn = [r for r in done if r["grade"] == "바람 언더(관찰)"]
    s2.append(["바람 언더(관찰·페이퍼)"] + rec(wn) + ["실외 · 킥오프 예보 지속 15mph+ 언더(10/1~) — 손익분기 52.4% · 40픽 또는 시즌 종료 때 보고 · <52.4% 폐기"])
    for _g in sorted({r["grade"] for r in done if r["grade"].endswith("(소급)")}):
        s2.append([_g + "·1~3주 백테스트"] + rec([r for r in done if r["grade"] == _g]) + ["2026-10-05 소급(backfill_weeks.py) — 같은 규칙을 마감 라인에 적용, 전향 판정 표본과 별개"])
    _nx = [r for r in done if r["grade"] == "새 정보(관찰)"]
    s2.append(["라인 뒤 새 정보(관찰·페이퍼)"] + rec(_nx) + ["발행 「- 새 정보:」 줄(10/5~ 사전 등록 55b93ea) — 30픽: 평균 CLV>0 & ≥52.4% 상정 · <50% 또는 CLV≤−0.5 폐기"])
    for _g in ("각도 관찰 A1(원정 큰 페이버릿 반대)", "각도 관찰 A2(드라이브 우위 언더독 반대)", "각도 관찰 A3(결장 팀 반대 3점+ 이동 → 결장 팀)"):
        _xs = [r for r in done if r["grade"] == _g]
        s2.append([_g + "·페이퍼"] + rec(_xs) + ["2023~25 탐색 약한 꼴(10/4~) — 30픽/시즌 끝 보고 · <50% 폐기 · ≥55% & CLV ≥0 이면 상정"])
    # CLV(2026-10-01): 픽 라인 vs 마감 라인(점, + = 우리가 더 좋은 숫자) — 승패보다 빨리 실력이 보인다. 모델 페이퍼는 리프레시마다 쪽이 갱신돼 ≈0 이 정상
    for lab, xs in (("평균 CLV · 실베팅", [r for r in rows if r["status"] == "placed"]), ("평균 CLV · 발행 판단", [r for r in rows if r["grade"].startswith("관심(발행)")]),
                    ("평균 CLV · 발행 방향", [r for r in rows if r["grade"].startswith("방향(발행)")]),
                    ("평균 CLV · 바람 언더", [r for r in rows if r["grade"] == "바람 언더(관찰)"]),
                    ("평균 CLV · 라인 뒤 새 정보", [r for r in rows if r["grade"] == "새 정보(관찰)"])):
        cv = [fnum(r.get("clv")) for r in xs if fnum(r.get("clv")) is not None]
        s2.append([lab, len(cv), sum(1 for v in cv if v > 0), sum(1 for v in cv if v < 0), sum(1 for v in cv if v == 0),
                   None, round(sum(cv) / len(cv), 2) if cv else None, "픽/우리 쪽 이동/반대/같음 · 「유닛」 칸 = 평균 CLV(점)"])
    s2.append([])
    s2.append(["실베팅 · 시장별"]); [s2.append([f"  {k}"] + rec([r for r in placed if r["market"] == k]) + [""]) for k in ("spread", "total")]
    s2.append(["실베팅 · 등급별"]); [s2.append([f"  {k}"] + rec([r for r in placed if r["grade"] == k]) + [""]) for k in sorted({r["grade"] for r in placed})]
    s2.append([]); s2.append(["모델 엣지 구간(전체 페이퍼 — 모델 검증)"])
    by = defaultdict(list)
    for r in done:
        e = abs(fnum(r["edge"]) or 0); by["≥5" if e >= 5 else "3.5~5" if e >= 3.5 else "2~3.5" if e >= 2 else "<2"].append(r)
    for k in ("<2", "2~3.5", "3.5~5", "≥5"):
        s2.append([f"  |엣지| {k}"] + rec(by.get(k, [])) + [""])
    for c in s2[1]:
        c.font = head; c.fill = fill
    s2.column_dimensions["A"].width = 30; s2.column_dimensions["H"].width = 40
    # 주별
    s3 = wb.create_sheet("주별")
    s3.append(["주차", "실베팅 픽", "승", "패", "푸시", "적중률%", "유닛", "발행 판단 픽", "승", "패", "푸시", "적중률%", "유닛"])
    for wk in sorted({int(r["week"]) for r in done}):
        s3.append([wk] + rec([r for r in placed if int(r["week"]) == wk]) + rec([r for r in pub if int(r["week"]) == wk]))
    for c in s3[1]:
        c.font = head; c.fill = fill
    try:
        _g = pred_sheets(wb, head, fill)
        print(f"  경기별 {len(_g)}행 · 팀별 시트")
    except Exception as e:   # 보기용 시트 — 실패해도 픽로그는 쓴다
        print(f"  경기별·팀별 시트 실패({type(e).__name__}: {e})")
    wb.save(OUT); print(f"wrote {os.path.relpath(OUT, os.path.dirname(HERE))} — 픽로그 {len(rows)}행 · 채점 {len(done)} · 실베팅 {len(placed)}")


if __name__ == "__main__":
    main()
