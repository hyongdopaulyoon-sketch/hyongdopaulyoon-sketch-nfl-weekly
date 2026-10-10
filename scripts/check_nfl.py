"""발행문 검사 + 판단 기록 (2026-09-29 발행 세션 도입).
  python check_nfl.py --week 4 --file 발행문.md [--record]
검사: ① 경기 머리(🏈 AWAY@HOME) 커버리지 ② 시장 줄 스프레드·총점이 model.csv 와 같은가 ③ 판단 줄 형식·관심 ≤3·한 경기 한 시장
④ 뉴스 확인 줄 존재 ⑤ 금지 낱말(캐시아웃·헤지 권유) ⑥ 방향 줄(2026-10-01 — 패스여도 스프레드·총점 쪽을 반드시 적는다) 형식·라인 = 시장·판단 쪽 = 방향 쪽.
--record 면 관심·소액 관심은 「관심(발행)」(id …:J), 방향은 「방향(발행)」(id …:D) 페이퍼로 적는다 — 모델 페이퍼 행(id …:spread|total)은 그대로 둔다.
2026-10-05(개선안 2·4·5 · MLB 보드 세션 상의): ⑦ 「- 새 정보:」 줄(라인 뒤 새 정보 관찰 — 사전 등록 55b93ea, --record 면 id …:N 「새 정보(관찰)」)
⑧ 예측 조정 상한 — 시장 승률 ±5%p 초과는 근거에 QB·새 정보·확정이 있을 때만 · 쉬운 라벨(시장보다 높게 봄/비슷/낮게 봄) ⑨ 「- 결론: ①②③」 세 문장
⑩ 개수 요약(「유리 3 · 불리 1」) 금지 ⑪ 귀속 대조 — 매치업 줄 팀 수치 = ratings.csv · 「팀 포지션 선수」 = 다이제스트 그 팀 부상 줄 · (★NN%) = 다이제스트 스냅.
2026-10-10(Paul 「맞대결·키커·QB·선수·팀 비교 무조건」 + 「티저 버리고 ML 집중」): ⑫ 필수 줄 「- 맞대결:」「- 팀 비교:」「- QB 비교:」「- 선수 비교:」「- 키커:」「- 심판:」(값은 다이제스트 🤝🏟️🦵🧑‍⚖️ 표 그대로 — 판 밖 숫자 경고 대상)
⑬ 판단·굳이 하나만에 ML 허용(「- 판단: 관심 · ML · DAL ML -520」 — 팀은 예측 승자와 같아야 함; --record 면 market ml · side 「DAL ML」 · odds 는 적힌 배당, 없으면 games.csv DK ML) ⑭ 티저 낱말이 발행문에 있으면 문제."""
from datetime import datetime
import argparse
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); DATA = os.path.join(ROOT, "data")
SEASON = 2026
sys.path.insert(0, HERE)


def rd(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig", newline=""))) if os.path.exists(p) else []


def fnum(x):
    try:
        return float(str(x).replace("−", "-").strip())
    except (TypeError, ValueError):
        return None


def sections(txt):
    out = {}
    for m in re.finditer(r"(?ms)^🏈\s*([A-Z]{2,3})@([A-Z]{2,3})\b[^\n]*\n(.*?)(?=^🏈|^🏁|\Z)", txt):
        out[f"{m.group(1)}@{m.group(2)}"] = m.group(3)
    return out


CAP = 0.05          # 발행 예측 조정 상한(시장 승률 대비)
LABEL_BAND = 0.03   # |발행 − 시장| < 3%p = 「비슷」(10/5 보강 — 북 사이 무비그 차이만 1~2%p)
POS = r"(?:QB|RB|FB|WR|TE|OL|OT|OG|G|C|T|DL|DE|DT|NT|EDGE|LB|ILB|OLB|CB|DB|S|FS|SS|K|P|LS)"


def pick_snapshot(wd, txt, override=None):
    """귀속 대조 기준판 — 발행문이 본 판(MLB 9/21 「라운드별 기준판 대조」 교훈: 현재판과 대조하면 경기 뒤 갱신된 값으로 오탐).
    우선순위: --digest 지정 > 발행문의 「다이제스트 MM-DD HH:MM」 > 「판 HH:MM」 이하 최신 스냅샷(오늘) > DIGEST.md."""
    if override:
        return override
    snaps = sorted(f for f in os.listdir(wd) if re.fullmatch(r"DIGEST-\d{4}-\d{4}\.md", f)) if os.path.isdir(wd) else []
    m = re.search(r"다이제스트\s*(\d{2})[-/](\d{2})\s+(\d{1,2}):(\d{2})", txt)
    if m:
        key = f"DIGEST-{m.group(1)}{m.group(2)}-{int(m.group(3)):02d}{m.group(4)}.md"
        if key in snaps:
            return os.path.join(wd, key)
    m = re.search(r"판\s+(\d{1,2}):(\d{2})", txt)
    if m and snaps:
        day = datetime.now().strftime("%m%d"); cut = f"DIGEST-{day}-{int(m.group(1)):02d}{m.group(2)}.md"
        ok = [f for f in snaps if f.startswith(f"DIGEST-{day}-") and f <= cut]
        if ok:
            return os.path.join(wd, ok[-1])
    return os.path.join(wd, "DIGEST.md")


def digest_sections(p):
    txt = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    return {m.group(1): m.group(2) for m in re.finditer(r"(?ms)^## ([A-Z]{2,3}@[A-Z]{2,3})  [^\n]*\n(.*?)(?=^## |\Z)", txt)}


def attribution(k, body, dsec):
    """⑪ 귀속 대조 → (문제, 경고). MLB 9/10 환각 전수 검수: 틀리는 건 숫자가 아니라 「누구 것」."""
    bad, warn = [], []
    a_, h_ = k.split("@")
    ratings = {}
    for r in re.finditer(r"(?m)^- 레이팅: ([A-Z]{2,3}) 공격 ([+-]?[\d.]+)\([^)]*\) · 수비 ([+-]?[\d.]+)\([^)]*\) · 순마진 ([+-]?[\d.]+)", dsec):
        ratings[r.group(1)] = {"off": r.group(2), "def": r.group(3), "net_pts_per_game": r.group(4)}
    for m in re.finditer(r"([A-Z]{2,3}) 공격 ([+-]?[\d.]+) · 수비 ([+-]?[\d.]+) · 순마진 ([+-]?[\d.]+)(?: · PF/PA ([\d.]+)/([\d.]+))?", body):
        t = m.group(1)
        if t not in (a_, h_):
            bad.append(f"{k}: 매치업 줄 팀 {t} 이 이 경기 팀이 아님"); continue
        vals = (fnum(m.group(2)), fnum(m.group(3)), fnum(m.group(4)))

        def same(r):
            return r and abs(vals[0] - fnum(r["off"])) < 6e-4 and abs(vals[1] - fnum(r["def"])) < 6e-4 and abs(vals[2] - fnum(r["net_pts_per_game"])) < 0.051
        if not same(ratings.get(t)):
            o = h_ if t == a_ else a_
            bad.append(f"{k}: {t} 매치업 수치(공격 {m.group(2)} · 수비 {m.group(3)} · 순마진 {m.group(4)}) ≠ 기준판 다이제스트 레이팅"
                       + (f" — {o} 값과 같음(팀 바꿔 씀)" if same(ratings.get(o)) else ""))
    inj_line = {t: (re.search(rf"(?m)^- 부상·QB {t}:[^\n]*", dsec) or [""])[0] for t in (a_, h_)}
    for m in re.finditer(rf"\b([A-Z]{{2,3}}) {POS} ([A-Z][\w.'’\-]+(?: [A-Z][\w.'’\-]+){{0,2}})(\(★?\s*(\d+)%\))?", body):
        t, name, snap = m.group(1), m.group(2), m.group(4)
        if t not in (a_, h_):
            continue
        sur = name.split()[-1]
        o = h_ if t == a_ else a_
        in_t, in_o = sur in inj_line[t], sur in inj_line[o]
        if in_o and not in_t:
            bad.append(f"{k}: 「{t} {name}」 — 다이제스트에선 {o} 부상 줄에 있음(귀속 오류)")
        elif not in_t and not in_o and snap:
            warn.append(f"{k}: 「{t} {name}({snap}%)」 스냅 수치가 다이제스트 부상 줄에 없음 — 웹 보도면 「보도」 라벨")
        if snap and in_t:
            sm = re.search(rf"{re.escape(sur)}\([^)]*스냅 (\d+)%", inj_line[t])
            if sm and sm.group(1) != snap:
                bad.append(f"{k}: 「{name}」 스냅 {snap}% ≠ 다이제스트 {sm.group(1)}%")
    return bad, warn


NUM_LINES = ("- 매치업", "- 맥락", "- 결론", "- 시장", "- 맞대결", "- 팀 비교", "- QB 비교", "- 선수 비교", "- 키커", "- 심판")      # 다이제스트 값을 옮기는 줄 — 뉴스·새 정보·📘 는 제외
MUST_LINES = ("- 맞대결:", "- 스탯 비교", "- 팀 비교:", "- 심판:")   # 2026-10-10 Paul 필수(값은 다이제스트 표 그대로) · 저녁 개정: QB·선수·키커는 「스탯 비교」 블록 안으로
COVER_TALK = re.compile(r"키 ?넘버|커버|점 ?차(?:로|까지|이면|면| 이상| 이내)[^\n]{0,14}(?:지면|이기면|맞|틀)")   # 스프레드 점수 차 설명 — 2026-10-10 Paul 「쓸데없는 정보」
# 행마다 허용 표기(발행 세션이 다이제스트 행 이름을 줄여 쓰는 경우 — 10/10 3차 발행 실측) · QB·주요 선수·키커는 별도 줄(「- QB 비교:」「- 선수 비교:」「- 키커:」)로도 인정
STAT_ROWS = (("득점",), ("실점",), ("공격 효율", "드라이브당 득점"), ("득점 드라이브",), ("수비 효율", "내준 드라이브당"), ("패스 공격",), ("러시 공격",), ("패스 수비",), ("러시 수비",),
             ("3rd down",), ("턴오버",), ("색 허용",), ("QB", "- QB 비교:"), ("주요 선수", "- 선수 비교:"), ("키커", "- 키커:"))
ML_SIDE = r"[A-Z]{2,3} ML(?:\s*[+-]\d{3,4})?"


def polarity(k, body, m, g, dsec):
    """부호·방향 반대 읽기(MLB 귀속 4패턴 중 「분해 부호 반대」 — 10/4 「편성 이득 −인데 득을 본다」) + 판 밖 숫자(H1 계열).
    ① 「TEAM 페이버릿/언더독」 ↔ 시장 스프레드 부호 ② 「TEAM 쪽으로 이동」 ↔ 개장→지금 홈 라인 변화 ③ 값 옮기는 줄의 소수·% 숫자가 기준판 경기 절에 있나(경고)."""
    bad, warn = [], []
    a_, h_ = k.split("@")
    hs = fnum(m.get("mkt_spread_home"))
    if hs:
        fav = h_ if hs < 0 else a_
        for mm in re.finditer(r"\b([A-Z]{2,3})(?:가|이|는|은|\s)*\s*(페이버릿|언더독)", body):
            t, w = mm.group(1), mm.group(2)
            if t in (a_, h_) and ((w == "페이버릿") != (t == fav)):
                bad.append(f"{k}: 「{t} {w}」 — 시장 스프레드 홈 {hs:+g} 이면 페이버릿은 {fav}(부호 반대 읽기)")
    o, n = fnum(g.get("open_spread_home")), fnum(g.get("spread_home"))
    for mm in re.finditer(r"\b([A-Z]{2,3}) 쪽(?:으로)?\s*(?:[\d.]+\s*점?\s*)?(?:이동|움직)", body):
        t = mm.group(1)
        if t not in (a_, h_):
            continue
        sent = body[max(body.rfind("\n", 0, mm.start()), body.rfind("。", 0, mm.start()), body.rfind(". ", 0, mm.start()), body.rfind("다.", 0, mm.start())) + 1:mm.end()]
        if re.search(r"ML|머니라인", sent):   # 「ML도」처럼 조사가 붙으면 \b 가 안 걸린다(10/10 DEN@LAC 오탐)
            continue                                           # ML 이동 문장 — 스프레드 부호 검사 대상 아님(10/10)
        pair = re.search(r"([A-Z]{2,3})?\s*([+-]?\d+(?:\.\d+)?)\s*에서\s*(?:[A-Z]{2,3}\s*)?([+-]?\d+(?:\.\d+)?)\s*(?:로|으로)", sent)
        if pair and pair.group(1) in (a_, h_, None):
            team = pair.group(1) or h_                         # 팀 표기 없으면 홈 기준 라인
            x, y = fnum(pair.group(2)), fnum(pair.group(3))
            if x is None or y is None or x == y:
                continue
            toward = team if y < x else (a_ if team == h_ else h_)   # 그 팀 라인이 나빠지면(숫자 감소) 그 팀 쪽 이동
            if t != toward:
                bad.append(f"{k}: 「{t} 쪽 이동」 — 문장의 {team} {x:+g} → {y:+g} 는 {toward} 쪽 이동(라인이 나빠진 팀 쪽)")
        elif o is not None and n is not None and o != n:
            toward = h_ if n < o else a_
            if t != toward:
                bad.append(f"{k}: 「{t} 쪽 이동」 — 개장 {o:+g} → 지금 {n:+g}(홈 기준)은 {toward} 쪽 이동")
    sec = dsec.replace("−", "-")
    for ln in body.splitlines():
        if not ln.startswith(NUM_LINES) or "보도" in ln:
            continue
        for x in re.findall(r"[+-]?\d+\.\d+%?|\d+%", ln):
            core = x.lstrip("+")
            if core not in sec and x not in sec:
                warn.append(f"{k}: 숫자 {x} 가 기준판 경기 절에 없음 — 「{ln[:40]}…」(재계산·외부 숫자면 「보도」 라벨)")
                break
    return bad, warn


def line_move(wd, game, hhmm, side, market):
    """발표 시각 직전 스냅샷 → 마지막 스냅샷 라인 이동(우리 쪽 + 점). 판단 못 하면 None."""
    hist = rd(os.path.join(wd, "line_history.csv"))
    hist = [r for r in hist if r["game"] == game]
    if not hist or not hhmm:
        return None
    today = datetime.now().strftime("%m-%d")
    stamp = f"{today} {int(hhmm.split(':')[0]):02d}:{hhmm.split(':')[1]}"
    before = [r for r in hist if r["pulled_at"] <= stamp] or hist[:1]
    b, e = before[-1], hist[-1]
    a_, h_ = game.split("@")
    if market == "spread":
        b0, e0 = fnum(b["spread_home"]), fnum(e["spread_home"])
        if b0 is None or e0 is None:
            return None
        team = side.split()[0]
        return (b0 - e0) if team == h_ else (e0 - b0)     # 홈 라인이 더 음수로 가면 홈 쪽으로 움직인 것
    b0, e0 = fnum(b["total"]), fnum(e["total"])
    if b0 is None or e0 is None:
        return None
    return (e0 - b0) if side.startswith("Over") else (b0 - e0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, required=True); ap.add_argument("--file", required=True); ap.add_argument("--record", action="store_true")
    ap.add_argument("--digest", help="귀속 대조 기준판(DIGEST-MMDD-HHMM.md 경로) — 기본은 발행문 머리의 판 시각으로 고름")
    a = ap.parse_args()
    wd = os.path.join(DATA, f"{SEASON}-w{a.week:02d}")
    games = rd(os.path.join(wd, "games.csv")); model = {f'{r["away"]}@{r["home"]}': r for r in rd(os.path.join(wd, "model.csv"))}
    txt = open(a.file, encoding="utf-8").read().replace("−", "-")
    secs = sections(txt)
    문제, 판단들, 방향들, 예측들, 경고, 새정보 = [], [], [], [], [], []
    snap = pick_snapshot(wd, txt, a.digest)
    games_by = {f'{r["away"]}@{r["home"]}': r for r in games}
    dsecs = digest_sections(snap)
    mkt_pred = {r["game"]: r for r in rd(os.path.join(wd, "predictions.csv")) if r.get("src") == "시장"}
    keys = [f'{g["away"]}@{g["home"]}' for g in games]
    missing = [k for k in keys if k not in secs]
    if missing:
        문제.append(f"커버리지: 발행문에 없는 경기 {len(missing)}: {', '.join(missing)}")
    for k, body in secs.items():
        if k not in model:
            문제.append(f"{k}: 이번 주 경기가 아님(경기 키 오타?)"); continue
        m = model[k]
        mk = re.search(r"스프레드 홈 ([+-]?[\d.]+)\s*·\s*총점 ([\d.]+)", body)
        if not mk:
            문제.append(f"{k}: 시장 줄 형식(「스프레드 홈 x · 총점 y」) 없음")
        else:
            if fnum(mk.group(1)) != fnum(m["mkt_spread_home"]):
                문제.append(f"{k}: 스프레드 홈 {mk.group(1)} ≠ 다이제스트 {m['mkt_spread_home']}")
            if fnum(mk.group(2)) != fnum(m["mkt_total"]):
                문제.append(f"{k}: 총점 {mk.group(2)} ≠ 다이제스트 {m['mkt_total']}")
        if not re.search(r"(?m)^- 뉴스 확인", body):
            문제.append(f"{k}: 「뉴스 확인(웹)」 줄 없음")
        miss = [x for x in MUST_LINES if not re.search(r"(?m)^" + re.escape(x), body)]
        if miss:
            문제.append(f"{k}: 필수 줄 없음(2026-10-10 Paul): {' '.join(miss)}")
        if re.search(r"티저|teaser", body, re.I):
            문제.append(f"{k}: 「티저」 언급 — 2026-10-10 폐지(쓰지 않는다)")
        sm = re.search(r"(?ms)^- 스탯 비교[^\n]*\n((?:[ \t]+[·•\-][^\n]*\n?)+)", body)
        if sm:
            miss_rows = [alts[0] for alts in STAT_ROWS if not any((a in sm.group(1)) or (a.startswith("- ") and re.search("(?m)^" + re.escape(a), body)) for a in alts)]
            if miss_rows:
                문제.append(f"{k}: 스탯 비교에 빠진 행 {len(miss_rows)}: {', '.join(miss_rows)} — 다이제스트 📊 표 전 행을 옮긴다")
        elif "- 스탯 비교" in body:
            문제.append(f"{k}: 스탯 비교 줄 아래 「  · 항목 …」 들여쓴 행이 없음")
        for ln in body.splitlines():
            if ln.startswith(("- 결론", "- 굳이 하나만", "📘")) or (ln.strip() and not ln.startswith("-") and "📘" in body[:body.find(ln) + 1]):
                if COVER_TALK.search(ln):
                    문제.append(f"{k}: 스프레드 점수 차·커버 설명(「{COVER_TALK.search(ln).group(0)}」) — 2026-10-10 Paul 「쓸데없는 정보」, 방향 줄 한 줄만 허용"); break
        dm = re.search(r"(?m)^- 방향:\s*스프레드\s+([A-Z]{2,3}) ([+-]?[\d.]+)\s*·\s*총점\s+(Over|Under|오버|언더) ([\d.]+)", body)
        dirs = {}
        if not dm:
            문제.append(f"{k}: 방향 줄(「- 방향: 스프레드 팀 ±x · 총점 Over|Under y」) 없음/형식 오류 — 패스여도 필수")
        else:
            a_, h_ = k.split("@")
            team, sp, ou, tot = dm.group(1), fnum(dm.group(2)), dm.group(3).replace("오버", "Over").replace("언더", "Under"), fnum(dm.group(4))
            hs = fnum(m["mkt_spread_home"])
            if team not in (a_, h_):
                문제.append(f"{k}: 방향 스프레드 팀 {team} 이 이 경기 팀이 아님")
            elif hs is not None and sp != (hs if team == h_ else -hs):
                문제.append(f"{k}: 방향 스프레드 {team} {dm.group(2)} ≠ 시장 라인({team} {(hs if team == h_ else -hs):+g})")
            if tot != fnum(m["mkt_total"]):
                문제.append(f"{k}: 방향 총점 {dm.group(4)} ≠ 시장 {m['mkt_total']}")
            dirs = {"스프레드": f"{team} {sp:+g}", "총점": f"{ou} {tot:g}"}
            방향들.append((k, dirs["스프레드"], dirs["총점"]))
        pm = re.search(r"(?m)^- 예측:\s*승자\s+([A-Z]{2,3})\s+(\d+(?:\.\d+)?)%\s*(?:★{1,4}\s*)?·\s*점수\s+([A-Z]{2,3})\s+(\d+(?:\.\d)?)\s*[–-]\s*([A-Z]{2,3})\s+(\d+(?:\.\d)?)", body)
        if not pm:
            문제.append(f"{k}: 예측 줄(「- 예측: 승자 팀 NN% · 점수 원정 x – 홈 y」) 없음/형식 오류 — 2026-10-04 결과 예측 의무")
        else:
            a_, h_ = k.split("@")
            if pm.group(1) not in (a_, h_) or pm.group(3) != a_ or pm.group(5) != h_:
                문제.append(f"{k}: 예측 줄 팀 순서/약칭 오류(점수는 원정 먼저)")
            else:
                예측들.append([k, pm.group(1), float(pm.group(2)) / 100, float(pm.group(4)), float(pm.group(6)), ""])
                pline = body[pm.start():body.find("\n", pm.start()) if body.find("\n", pm.start()) > 0 else len(body)]
                mp = mkt_pred.get(k)
                if mp and fnum(mp.get("p_pick")) is not None:
                    pm_ = fnum(mp["p_pick"]); pub = float(pm.group(2)) / 100
                    mine = pm_ if pm.group(1) == mp["pick"] else 1 - pm_      # 시장 확률을 발행 승자 기준으로
                    d = pub - mine
                    if abs(d) > CAP + 1e-9 and re.search(r"QB|새 정보|확정", pline):
                        예측들[-1][5] = "상한 예외"
                    if abs(d) > CAP + 1e-9 and not re.search(r"QB|새 정보|확정", pline):
                        문제.append(f"{k}: 예측 {pm.group(1)} {pub:.0%} — 시장 {mine:.0%}에서 {d * 100:+.0f}%p(상한 ±5%p, 예외 = QB 교체·라인 뒤 확정 결장 — 근거에 적을 것)")
                    want = "높게 봄" if d >= LABEL_BAND else "낮게 봄" if d <= -LABEL_BAND else "비슷"
                    got = re.search(r"시장보다 (높게 봄|낮게 봄)|시장과 비슷|비슷|시장 그대로", pline)
                    got_w = None if not got else ("비슷" if got.group(0) in ("시장과 비슷", "비슷", "시장 그대로") else got.group(1))
                    if got_w is None:
                        문제.append(f"{k}: 예측 근거에 쉬운 라벨(「시장보다 높게 봄 / 비슷 / 낮게 봄」) 없음")
                    elif got_w != want:
                        문제.append(f"{k}: 라벨 「{got.group(0)}」 ≠ 실제 차이 {d * 100:+.0f}%p → 「{want}」")
        nm = re.search(r"(?m)^- 새 정보:\s*([^\n]*)", body)
        if not nm:
            문제.append(f"{k}: 「- 새 정보:」 줄 없음 — 없으면 「- 새 정보: 없음」(2026-10-05)")
        elif not nm.group(1).strip().startswith("없음"):
            nx = re.match(r"(.+?)\s*·\s*발표\s+(\d{1,2}:\d{2})\s*(?:PT)?\s*·\s*쪽\s+(?:스프레드\s+|총점\s+)?([A-Z]{2,3} [+-][\d.]+|(?:Over|Under) [\d.]+)", nm.group(1).strip())
            if not nx:
                문제.append(f"{k}: 새 정보 줄 형식(「사실 · 발표 HH:MM PT · 쪽 팀 ±x | Over/Under y」) 오류")
            else:
                fact, hhmm, side = nx.group(1).strip(), nx.group(2), nx.group(3)
                a_, h_ = k.split("@"); hs = fnum(m["mkt_spread_home"])
                if side.startswith(("Over", "Under")):
                    mkt_ = "total"
                    if fnum(side.split()[1]) != fnum(m["mkt_total"]):
                        문제.append(f"{k}: 새 정보 쪽 {side} ≠ 시장 총점 {m['mkt_total']}")
                else:
                    mkt_ = "spread"; t_, ln = side.split()
                    if t_ not in (a_, h_) or (hs is not None and fnum(ln) != (hs if t_ == h_ else -hs)):
                        문제.append(f"{k}: 새 정보 쪽 {side} ≠ 시장 라인")
                mv = line_move(wd, k, hhmm, side, mkt_)
                sm_ = re.search(r"DIGEST-(\d{4})-(\d{4})\.md$", snap)
                early = bool(sm_ and sm_.group(1) == datetime.now().strftime("%m%d") and f"{int(hhmm.split(':')[0]):02d}{hhmm.split(':')[1]}" <= sm_.group(2))
                if early:
                    경고.append(f"{k}: 새 정보 발표 {hhmm} 가 기준판({sm_.group(2)[:2]}:{sm_.group(2)[2:]}) 이전 — 다이제스트에 이미 있었을 사실 → 판정 표본 아님(대조군으로 적립)")
                새정보.append((k, mkt_, side, fact, hhmm, mv, early))
        gm = re.search(r"(?m)^- 굳이 하나만:\s*(스프레드|총점|ML)\s+([A-Z]{2,3} [+-][\d.]+|(?:Over|Under|오버|언더) [\d.]+|" + ML_SIDE + ")", body)
        if gm and gm.group(1) == "ML":   # 2026-10-10 ML 허용 — 팀은 예측 승자와 같아야 한다
            if 예측들 and 예측들[-1][0] == k and gm.group(2).split()[0] != 예측들[-1][1]:
                문제.append(f"{k}: 굳이 하나만 ML {gm.group(2)} 이 예측 승자({예측들[-1][1]})와 다름")
        elif gm and dirs:   # 2026-10-08 Paul 「같은 쪽으로」 — 굳이 하나만은 방향 줄과 같은 쪽(가격이 싸다는 이유로 반대쪽 금지)
            gside = gm.group(2).replace("오버", "Over").replace("언더", "Under")
            if gside.split()[0] != dirs[gm.group(1)].split()[0]:
                문제.append(f"{k}: 굳이 하나만 {gside} 이 방향 줄({dirs[gm.group(1)]})과 반대 — 같은 쪽만(10/8)")
        cm = re.search(r"(?m)^- 결론:([^\n]*)", body)
        if not cm or not all(c in cm.group(1) for c in "①②③"):
            문제.append(f"{k}: 「- 결론: ① 가장 큰 근거 ② 가장 큰 반대 근거 ③ 위험 요소」 줄 없음/세 문장 아님(2026-10-05)")
        if re.search(r"유리\s*\d+\s*[·,/]\s*불리\s*\d+|불리\s*\d+\s*[·,/]\s*유리\s*\d+", body):
            문제.append(f"{k}: 개수 요약(「유리 n · 불리 n」) 금지 — 개수는 크기를 숨긴다")
        b_, w_ = attribution(k, body, dsecs.get(k, ""))
        문제 += b_; 경고 += w_
        b_, w_ = polarity(k, body, m, games_by.get(k, {}), dsecs.get(k, ""))
        문제 += b_; 경고 += w_
        j = re.search(r"(?m)^- 판단:\s*(패스|소액 관심|관심)(?:\s*·\s*(스프레드|총점|ML)\s*·\s*([^\n]+))?", body)
        if not j:
            문제.append(f"{k}: 판단 줄 없음/형식 오류"); continue
        verdict, market, side = j.group(1), j.group(2), (j.group(3) or "").strip()
        if verdict != "패스" and not (market and side):
            문제.append(f"{k}: {verdict}인데 시장·쪽 라인이 없음")
        if verdict != "패스":
            if market == "스프레드" and not re.fullmatch(r"[A-Z]{2,3} [+-][\d.]+", side):
                문제.append(f"{k}: 스프레드 쪽 형식 「팀 +3.5」 아님: {side}")
            if market == "총점" and not re.fullmatch(r"(Over|Under|오버|언더) [\d.]+", side):
                문제.append(f"{k}: 총점 쪽 형식 「Over 41.5」 아님: {side}")
            if market == "ML":   # 2026-10-10 Paul 「ML 에 집중」
                if not re.fullmatch(ML_SIDE, side):
                    문제.append(f"{k}: ML 쪽 형식 「DAL ML -520」 아님: {side}")
                elif 예측들 and 예측들[-1][0] == k and side.split()[0] != 예측들[-1][1]:
                    문제.append(f"{k}: 판단 ML {side} 이 예측 승자({예측들[-1][1]})와 다름")
            if dirs and market in dirs and side.replace("오버", "Over").replace("언더", "Under").split()[0] != dirs[market].split()[0]:
                문제.append(f"{k}: 판단 쪽 {side} 이 방향 줄({dirs[market]})과 반대")
            판단들.append((k, verdict, market, side))
        if re.search(r"캐시아웃|헤지(?:를|를 하|하세요|권)|라이브로 들어가", body) and not re.search(r"전제가 깨|QB 부상", body):
            문제.append(f"{k}: 캐시아웃·헤지·라이브 권유 문구(금지)")
    n관심 = sum(1 for x in 판단들 if x[1] == "관심")
    if n관심 > 3:
        문제.append(f"「관심」 {n관심}경기 — 주당 최대 3")
    print(f"■ NFL 발행문 검사 week {a.week}: 경기 {len(secs)}/{len(keys)} · 판단 {len(판단들)}(관심 {n관심}) · 방향 {len(방향들)} · 새 정보 {len(새정보)} · 문제 {len(문제)} · 경고 {len(경고)}")
    for x in 문제:
        print("  ✗", x)
    for x in 경고:
        print("  △", x)
    print(f"  (귀속 대조 기준판: {os.path.basename(snap)})")
    for k, mk_, sd, fact, hhmm, mv, early in 새정보:
        print(f"  🆕 {k} 새 정보{'(대조군 — 판 이전 발표)' if early else ''} {sd} · 발표 {hhmm} · 발표 뒤 라인 이동 {'?' if mv is None else f'{mv:+g}점(우리 쪽 +)'} · {fact}")
    for k, v, mk, sd in 판단들:
        print(f"  · {k} {v} · {mk} · {sd}")
    for k, s_, t_ in 방향들:
        print(f"  → {k} 방향 {s_} / {t_}")
    for k, pk, pp, sa, sh, fl in 예측들:
        print(f"  🔮 {k} 예측 {pk} {100 * pp:.0f}% · {sa:g}-{sh:g}" + (f" · {fl}" if fl else ""))
    if a.record and 예측들:
        import predictions as PR
        for k, pk, pp, sa, sh, fl in 예측들:
            PR.add_pub(a.week, k, pk, pp, sa, sh, flag=fl)
    if a.record and 새정보:
        import picks as P
        gid_of = {f'{r["away"]}@{r["home"]}': r["game_id"] for r in games}
        for k, mk_, sd, fact, hhmm, mv, early in 새정보:
            if k in gid_of:
                P.lean(a.week, f"{gid_of[k]}:{mk_}", sd, sd.split()[-1], "-110",
                       f"새 정보: {fact} · 발표 {hhmm} PT · 발표 뒤 라인 이동 {'?' if mv is None else f'{mv:+g}'}점",
                       suffix=":NC" if early else ":N", grade="새 정보(판 이전·대조)" if early else "새 정보(관찰)")
    if a.record and (판단들 or 방향들):
        import picks as P
        gid_of = {f'{r["away"]}@{r["home"]}': r["game_id"] for r in games}
        for k, v, mk, sd in 판단들:
            if k not in gid_of:
                continue
            if mk == "ML":   # 2026-10-10: side 「DAL ML」 · odds = 적힌 배당 또는 games.csv DK ML
                t_ = sd.split()[0]; g_ = games_by.get(k, {})
                mo = re.search(r"[+-]\d{3,4}", sd)
                odds = mo.group(0) if mo else (g_.get("ml_home") if t_ == k.split("@")[1] else g_.get("ml_away")) or "-110"
                P.lean(a.week, f"{gid_of[k]}:ml", f"{t_} ML", "", odds, f"발행 판단 {v}", suffix=":J", grade="관심(발행)")
                continue
            market = "spread" if mk == "스프레드" else "total"
            sd = sd.replace("오버", "Over").replace("언더", "Under")
            P.lean(a.week, f"{gid_of[k]}:{market}", sd, sd.split()[-1], "-110", f"발행 판단 {v}", suffix=":J", grade="관심(발행)")
        for k, s_, t_ in 방향들:
            if k not in gid_of:
                continue
            for market, sd in (("spread", s_), ("total", t_)):
                P.lean(a.week, f"{gid_of[k]}:{market}", sd, sd.split()[-1], "-110", "발행 방향", suffix=":D", grade="방향(발행)")
    return 1 if 문제 else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
