"""NFL 주간 보드 HTML(2026-10-04 Paul 「MLB 보드처럼 — 팀명·로고 같이」 · 10/5 「설명도 있고 깔끔하게」 — MLB 보드 세션 상의 반영).
  python nfl_board.py --week 4 [--out ../board/board-w04.html]
표시 전용 — 정본은 DIGEST.md·발행문·picks.csv·predictions.csv. 값을 옮겨 한 화면에 얹는다(가격 확률만 배당에서 계산).
로고는 Artifact CSP 가 외부 이미지를 막아 data: URI 로 넣는다(ESPN 64px PNG, data/cache/logos 캐시).
화면 순서(10/5): 머리(메타 한 줄 + 숫자 칩) → 이번 주 한 줄 결론 → 읽는 법 → 아직 안 한 경기 카드(실베팅 → 별 많은 순 → 킥오프)
→ 끝난 경기(한 줄로 접힘) → 별점별 적중 표 → 숫자 자세히(접힘) → 바닥글."""
import argparse, base64, glob, html, json, os, re, sys, urllib.request
from collections import defaultdict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nfl_pull as N   # noqa: E402
import picks as P      # noqa: E402
import predictions as PR   # noqa: E402

KR = N.TEAM_KR
esc = html.escape

# 용어 풀이 — 카드의 보라색 낱말에 마우스/손가락을 대면 뜬다(MLB 보드 _bt_mark·TIP 방식)
TERM = {
    "스프레드": "점수 차 핸디. NO −1.5 면 NO 가 2점 이상 이겨야 맞음, ATL +1.5 면 ATL 이 이기거나 1점 차 이내로 지면 맞음",
    "총점": "두 팀 점수를 더한 값. Over 47.5 = 48점 이상, Under 47.5 = 47점 이하",
    "ML": "머니라인 — 점수 차 상관없이 그냥 이길 팀",
    "티저": "핸디를 6점 유리하게 옮기는 대신 다리 2개를 한 장으로 묶어 둘 다 맞혀야 돈을 받는 베팅",
    "방향": "예측 점수에서 나온 스프레드·총점 쪽. 실력으로는 동전(≈50%)이라 돈 근거가 아니고 적중률만 잰다",
    "관찰": "돈을 걸지 않고 맞는지만 기록하는 페이퍼 실험",
    "CLV": "내가 산 가격이 경기 직전 마감 가격보다 좋았는지(+ = 싸게 샀다). 승패보다 빨리 실력이 보이는 숫자",
}


def term(word, label=None):
    return f'<abbr class="term" title="{esc(TERM[word])}">{esc(label or word)}</abbr>'


def logo_uri(team):
    """ESPN 64px 로고 → data URI(캐시)."""
    code = N.NV2ESPN.get(team, team).lower()
    d = os.path.join(N.CACHE, "logos"); os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{code}.png")
    if not os.path.exists(p):
        try:
            data = urllib.request.urlopen(f"https://a.espncdn.com/combiner/i?img=/i/teamlogos/nfl/500/{code}.png&w=64&h=64", timeout=20).read()
            open(p, "wb").write(data)
        except Exception:
            return ""
    return "data:image/png;base64," + base64.b64encode(open(p, "rb").read()).decode()


def short_kr(t):
    """한글 짧은 이름(별칭) — 「애틀랜타 팰컨스」 → 「팰컨스」."""
    return (KR.get(t) or t).split()[-1]


def pct(v):
    return f"{100 * v:.0f}%" if v is not None else "—"


def pub_lines(wd):
    """발행문(발행-*.md, 시각순) → {경기: {판단, 굳이}} — 뒤 판이 앞 판을 덮는다."""
    out = {}
    for p in sorted(glob.glob(os.path.join(wd, "발행-*.md"))):
        txt = open(p, encoding="utf-8").read()
        for m in re.finditer(r"(?ms)^🏈\s*([A-Z]{2,3}@[A-Z]{2,3})\b[^\n]*\n(.*?)(?=^🏈|^🏁|\Z)", txt):
            b = m.group(2)
            j = re.search(r"(?m)^- 판단:\s*([^\n]+)", b); k = re.search(r"(?m)^- 굳이 하나만:\s*([^\n]+)", b)
            out[m.group(1)] = {"판단": j.group(1).strip() if j else "", "굳이": k.group(1).strip() if k else ""}
    return out


def verdict_word(v):
    """발행 판단 → 카드 결론 낱말."""
    if not v:
        return ""
    if v.startswith("패스"):
        return "후보 아님"
    return "소액 관심" if v.startswith("소액") else "관심" if v.startswith("관심") else v


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--week", type=int, required=True); ap.add_argument("--out")
    a = ap.parse_args()
    wd = N.week_dir(a.week)
    games = N.rd(os.path.join(wd, "games.csv"))
    # 실시간 상태·점수(배당 들어 있는 espn_scoreboard.json 은 건드리지 않는다 — 끝난 경기는 배당이 사라지므로 따로 받는다)
    live = {}
    try:
        sb = os.path.join(wd, "board_scoreboard.json")
        N.fetch(f"{N.ESPN}?week={a.week}&seasontype=2&dates={N.SEASON}", sb, 0.05)
        for ev in json.load(open(sb, encoding="utf-8")).get("events", []):
            c = ev["competitions"][0]
            d = {t["homeAway"]: (N.ESPN2NV.get(t["team"]["abbreviation"], t["team"]["abbreviation"]), t.get("score", ""), t["team"].get("displayName", ""))
                 for t in c["competitors"]}
            live[f'{d["away"][0]}@{d["home"][0]}'] = dict(state=ev["status"]["type"]["name"], detail=ev["status"]["type"].get("shortDetail", ""),
                                                        sa=d["away"][1], sh=d["home"][1], na=d["away"][2], nh=d["home"][2])
    except Exception:
        pass
    picks = [r for r in P.rd(P.PICKS) if str(r.get("week")) == str(a.week)]
    by = defaultdict(list)
    for r in picks:
        by[r["game"]].append(r)
    pubs = pub_lines(wd)
    preds = defaultdict(dict)
    wk_pred_rows = N.rd(PR.path(a.week))
    for r in wk_pred_rows:
        preds[r["game"]][r["src"]] = r
    psum = PR.summary(PR.all_rows())
    wsum = PR.summary(wk_pred_rows)

    def result_of(r, gk):
        if r.get("result"):
            return r["result"]
        lv = live.get(gk)
        if lv and lv["state"] == "STATUS_FINAL":
            wl, _ = P._grade_one(r, {"away_score": lv["sa"], "home_score": lv["sh"]})
            return wl or ""
        return ""

    def hit(res):
        """예측·방향·관찰 결과 — 테두리만(실베팅 색 pill 과 구분)."""
        return {"W": '<span class="hit w">맞힘</span>', "L": '<span class="hit l">틀림</span>', "P": '<span class="hit p">무승부</span>'}.get(res, "")

    def betpill(r, gk):
        res = result_of(r, gk); u = P.fnum(r.get("units"))
        if res == "W":
            return f'<span class="bp w">승 {u:+.2f}u</span>' if u is not None else '<span class="bp w">승</span>'
        if res == "L":
            return f'<span class="bp l">패 {u:+.2f}u</span>' if u is not None else '<span class="bp l">패</span>'
        if res == "P":
            return '<span class="bp p">환불</span>'
        return '<span class="bp wait">대기</span>'

    allp = [r for r in P.rd(P.PICKS) if r.get("status") == "placed"]
    done = [r for r in allp if r.get("result") in ("W", "L", "P")]
    su = sum(P.fnum(r.get("units")) or 0 for r in done)
    sw = sum(1 for r in done if r["result"] == "W"); sl = sum(1 for r in done if r["result"] == "L")
    cvs = [P.fnum(r.get("clv_prob")) for r in done if P.fnum(r.get("clv_prob")) is not None]
    wk_bets = [r for r in picks if r.get("status") == "placed"]

    def team(t, name, right=False):
        return (f'<div class="team{" r" if right else ""}" title="{esc(name or t)}"><img src="{logo_uri(t)}" alt="" width="36" height="36">'
                f'<div><div class="tname">{esc(short_kr(t))}</div><div class="tkr">{esc(t)}</div></div></div>')

    def mini(t):
        return f'<img class="mini" src="{logo_uri(t)}" alt="" width="22" height="22">'

    pre_cards, done_rows = [], []
    teaser_open = []
    for g in games:
        A, H = g["away"], g["home"]; gk = f"{A}@{H}"
        lv = live.get(gk, {})
        st = lv.get("state", g.get("status", ""))
        fin = st == "STATUS_FINAL"
        rows = by.get(gk, [])
        bets = [r for r in rows if r.get("status") == "placed"]
        dirs = [r for r in rows if r["grade"] == "방향(발행)"]
        obs = [r for r in rows if r["grade"] in ("바람 언더(관찰)", "티저 다리(관찰)") or r["grade"].startswith("각도 관찰")]
        pub = pubs.get(gk, {})
        pr = preds.get(gk, {})
        m_, d_, b_ = pr.get("시장"), pr.get("모델"), pr.get("발행")
        pp = P.fnum(m_.get("p_pick")) if m_ else None
        win = ""
        if fin:
            fa, fh = float(lv.get("sa") or 0), float(lv.get("sh") or 0)
            win = H if fh > fa else A if fa > fh else ""

        def phit(r):
            return hit("W" if r.get("pick") == win else "L") if fin and win and r else ""
        # ── 예측(맨 위)
        pred_html = ""
        if m_:
            stars = PR.star_str(pp)
            pred_html = (f'<div class="pred"><div>이길 팀 <b>{esc(short_kr(m_["pick"]))}({esc(m_["pick"])}) {pct(pp)}</b> '
                         f'<span class="star" title="2018~25 이 별 승자 적중 {PR.STAR_HIT.get(PR.stars(pp), "")}">{stars}</span> {phit(m_)}</div>'
                         f'<div class="sub">예상 점수 {esc(A)} {int(float(m_["score_away"]) + 0.5)} – {esc(H)} {int(float(m_["score_home"]) + 0.5)} · 시장 배당 기준</div>')
            if b_:
                pred_html += f'<div class="sub">발행 예측 {esc(b_["pick"])} {pct(P.fnum(b_.get("p_pick")))} {phit(b_)}</div>'
            if d_ and d_["pick"] != m_["pick"]:
                pred_html += f'<div class="sub">우리 모델은 {esc(d_["pick"])} 쪽 — 시장과 반대(덜 정확한 두 번째 의견)</div>'
            pred_html += "</div>"
        # ── 결론 줄(낱말만, 근거는 title)
        items = []
        for r in bets:
            stake = P.fnum(r.get("stake")) or 1
            items.append(f'<li><span class="tag bet">실베팅</span> <b>{esc(r["side"])}</b> <span class="num">{esc(r.get("odds", ""))}</span> · {stake:g}u {betpill(r, gk)}</li>')
        vw = verdict_word(pub.get("판단", ""))
        if vw or dirs:
            dir_txt = " · ".join(esc(r["side"]) + " " + hit(result_of(r, gk)) for r in dirs)
            items.append(f'<li><span class="tag pub" title="claude.ai 발행 세션 판단">발행</span> '
                         + (f'<b title="{esc(pub.get("굳이", ""))}">{esc(vw)}</b>' + (" · " if dir_txt else "") if vw else "")
                         + (f'{term("방향")} {dir_txt}' if dir_txt else "") + "</li>")
        for r in obs:
            if r["grade"].startswith("티저"):
                lab = term("티저", "티저 다리")
                if not fin:
                    teaser_open.append(r)
            elif r["grade"].startswith("바람"):
                lab = "바람 언더"
            else:
                lab = r["grade"].split("(")[0].replace("각도 관찰 ", "각도 ")
            items.append(f'<li><span class="tag obs">{term("관찰", "관찰만")}</span> {lab} <b title="{esc(r.get("note", ""))}">{esc(r["side"])}</b> {hit(result_of(r, gk))}</li>')
        lines = f'<ul class="lines">{"".join(items)}</ul>' if items else ""
        div = '<span class="chip">디비전</span>' if g.get("div_game") == "1" else ""
        neu = '<span class="chip">중립 구장</span>' if g.get("neutral") == "1" else ""
        if fin:
            bet_s = " ".join(betpill(r, gk) for r in bets)
            done_rows.append(f'''<details class="done{' hasbet' if bets else ''}"><summary>
  <span class="dm">{mini(A)}<b>{esc(short_kr(A))}</b> <span class="num">{esc(str(lv.get("sa")))} – {esc(str(lv.get("sh")))}</span> <b>{esc(short_kr(H))}</b>{mini(H)}</span>
  <span class="dr">{f'예측 {esc(m_["pick"])} <span class="star">{PR.star_str(pp)}</span> {phit(m_)}' if m_ else ''} {bet_s}</span></summary>
  <div class="dbody">{pred_html}{lines}</div></details>''')
            continue
        # ── 아직 안 한 경기 / 진행 중
        if st == "STATUS_IN_PROGRESS":
            status = f'<span class="state live">진행 중</span> <b class="num">{esc(A)} {esc(str(lv.get("sa")))} – {esc(str(lv.get("sh")))} {esc(H)}</b> <span class="muted">{esc(lv.get("detail", ""))}</span>'
        else:
            status = f'<span class="state pre">예정</span> <span class="muted">{esc(g["kickoff_et"].split(" ", 1)[0])} {esc(g["kickoff_pt"])} PT</span>'
        hl = P.fnum(g.get("spread_home")); tl = P.fnum(g.get("total"))
        sh_, sa_ = N._novig(g.get("sp_home_odds"), g.get("sp_away_odds"))
        po, pu = N._novig(g.get("over_odds"), g.get("under_odds"))
        ma, mh = N._novig(g.get("ml_away"), g.get("ml_home"))
        quick, price = [], []
        if hl is not None:
            fav, fl = (H, hl) if hl < 0 else (A, -hl)
            quick.append(f'{term("스프레드")} {esc(fav)} {fl:+g}')
            price.append(f'<tr><td>{term("스프레드")}</td><td>{esc(H)} {hl:+g} <span class="num">{esc(g.get("sp_home_odds") or "")}</span> · {esc(A)} {-hl:+g} <span class="num">{esc(g.get("sp_away_odds") or "")}</span></td>'
                         f'<td class="muted">{esc(H)} {pct(sh_)} / {esc(A)} {pct(sa_)}</td></tr>')
        if tl is not None:
            quick.append(f'{term("총점")} {tl:g}')
            price.append(f'<tr><td>{term("총점")}</td><td>{tl:g} · O <span class="num">{esc(g.get("over_odds") or "")}</span> · U <span class="num">{esc(g.get("under_odds") or "")}</span></td>'
                         f'<td class="muted">Over {pct(po)} / Under {pct(pu)}</td></tr>')
        if g.get("ml_home"):
            quick.append(f'{term("ML")} {esc(A)} <span class="num">{esc(g.get("ml_away"))}</span> / {esc(H)} <span class="num">{esc(g.get("ml_home"))}</span>')
            price.append(f'<tr><td>{term("ML")}</td><td>{esc(A)} <span class="num">{esc(g.get("ml_away"))}</span> · {esc(H)} <span class="num">{esc(g.get("ml_home"))}</span></td>'
                         f'<td class="muted">승리 {esc(A)} {pct(ma)} / {esc(H)} {pct(mh)}</td></tr>')
        mk = (f'<div class="quick">{" · ".join(quick)}</div><details class="px"><summary>배당 자세히(DK · 수수료 뺀 확률)</summary>'
              f'<table>{"".join(price)}</table></details>') if quick else ""
        key = (0 if bets else 1, -PR.stars(pp), g["kickoff_utc"])
        pre_cards.append((key, f'''<article class="card{' hasbet' if bets else ''}">
  <header class="match">{team(A, lv.get("na"))}<span class="at">@</span>{team(H, lv.get("nh"), right=True)}</header>
  <div class="meta">{status}{div}{neu}</div>
  {pred_html}{mk}{lines}
</article>'''))
    pre_cards.sort(key=lambda x: x[0])
    now = datetime.now().strftime("%m/%d %H:%M")
    # ── 이번 주 한 줄 결론
    wk_open_bets = [r for r in wk_bets if not result_of(r, r["game"])]
    wk_done_bets = [r for r in wk_bets if result_of(r, r["game"])]
    wb_w = sum(1 for r in wk_done_bets if result_of(r, r["game"]) == "W"); wb_l = sum(1 for r in wk_done_bets if result_of(r, r["game"]) == "L")
    wm = wsum.get("시장", {})
    tz_txt = ("없음" if not teaser_open else f"{len(teaser_open)}개(" + " · ".join(esc(r["side"]) for r in teaser_open) + ")"
              + (" — 묶을 짝 있음" if len(teaser_open) >= 2 else " — 짝이 없어 걸 수 없음"))
    verdicts = [verdict_word(pubs.get(f'{g["away"]}@{g["home"]}', {}).get("판단", "")) for g in games
                if live.get(f'{g["away"]}@{g["home"]}', {}).get("state") != "STATUS_FINAL"]
    cand = sum(1 for v in verdicts if v in ("관심", "소액 관심"))
    headline = (f'남은 경기 <b>{len(pre_cards)}</b> · 발행 후보 <b>{cand}</b> · {term("티저", "티저 다리")} {tz_txt} · '
                f'이번 주 실베팅 <b>{wb_w}-{wb_l}</b>' + (f'(대기 {len(wk_open_bets)})' if wk_open_bets else "")
                )
    ms = psum.get("시장", {})
    star_rows = "".join(
        f'<tr><td class="star">{"★" * k}</td><td class="num">{w}-{l}</td><td class="num">{(f"{100 * w / (w + l):.0f}%") if w + l else "—"}</td><td class="num muted">{PR.STAR_HIT[k]}</td></tr>'
        for k, (w, l) in ms.get("stars", {}).items())
    page = f'''<title>NFL {a.week}주차 보드</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Saira+Extra+Condensed:wght@600;800&family=Noto+Sans+KR:wght@400;500;700&family=IBM+Plex+Mono:wght@500&display=swap" rel="stylesheet">
<style>
/* 구장 라인 감성 — 잔디 기운의 중립색 위에 흰 분필선, 강조는 엔드존 파일런 주황 · 모르는 말은 보라(MLB 보드와 같은 신호) */
:root{{--bg:#eef2ec;--panel:#ffffff;--ink:#14231b;--muted:#5d6b62;--line:#d4ddd3;--acc:#e8590c;--ok:#1f8a4c;--bad:#c2362b;--push:#8a7a1f;--term:#6b3fb5;--soft:#f6f8f4;
  --display:"Saira Extra Condensed","Arial Narrow",sans-serif;--body:"Noto Sans KR","Apple SD Gothic Neo","Malgun Gothic",sans-serif;--mono:"IBM Plex Mono",ui-monospace,monospace}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#0f1712;--panel:#16211a;--ink:#e6efe7;--muted:#97a69b;--line:#26352b;--acc:#ff7a2e;--ok:#4cc27a;--bad:#ef6a5f;--push:#cdbb52;--term:#b99af0;--soft:#1b281f;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#0f1712;--panel:#16211a;--ink:#e6efe7;--muted:#97a69b;--line:#26352b;--acc:#ff7a2e;--ok:#4cc27a;--bad:#ef6a5f;--push:#cdbb52;--term:#b99af0;--soft:#1b281f;color-scheme:dark}}
body{{background:var(--bg);color:var(--ink);font-family:var(--body);font-size:14px;line-height:1.55}}
.wrap{{max-width:1180px;margin:0 auto;padding-inline:16px;padding-block:20px 40px;display:grid;gap:18px}}
h1{{font-family:var(--display);font-weight:800;font-size:2.4rem;letter-spacing:.02em;margin:0;line-height:1}}
h2{{font-family:var(--display);font-weight:600;font-size:1.35rem;letter-spacing:.03em;margin:0}}
.top{{display:flex;flex-wrap:wrap;gap:8px 24px;align-items:end;justify-content:space-between;border-bottom:2px solid var(--ink);padding-bottom:10px}}
.muted{{color:var(--muted)}}
.num{{font-family:var(--mono);font-variant-numeric:tabular-nums}}
.chips{{display:flex;flex-wrap:wrap;gap:8px}}
.stat{{background:var(--panel);border:1px solid var(--line);padding:6px 12px;display:flex;gap:8px;align-items:baseline}}
.stat .k{{font-size:.75rem;color:var(--muted)}}
.stat .v{{font-family:var(--display);font-size:1.4rem;font-weight:600;font-variant-numeric:tabular-nums}}
.headline{{background:var(--panel);border-left:4px solid var(--acc);padding:10px 14px;font-size:1rem}}
.legend{{background:var(--soft);border:1px solid var(--line);padding:12px 14px;display:grid;gap:4px;font-size:.86rem}}
.legend b{{font-weight:700}}
.term{{color:var(--term);text-decoration:none;border-bottom:1px dotted var(--term);cursor:help}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}}
.card{{background:var(--panel);border:1px solid var(--line);padding:14px;display:grid;gap:10px;min-width:0;align-content:start}}
.card.hasbet,.done.hasbet{{border-color:var(--acc);box-shadow:inset 3px 0 0 var(--acc)}}
.match{{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:8px}}
.team{{display:flex;align-items:center;gap:8px;min-width:0}}
.team.r{{flex-direction:row-reverse;text-align:right}}
.team img{{width:36px;height:36px;flex:none}}
.tname{{font-weight:700;font-size:1.02rem;line-height:1.15}}
.tkr{{font-size:.72rem;color:var(--muted);font-family:var(--mono)}}
.at{{font-family:var(--display);color:var(--muted);font-size:1.1rem}}
.meta{{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:.85rem}}
.state{{font-size:.7rem;padding:1px 6px;border:1px solid var(--line)}}
.state.live{{color:var(--acc);border-color:var(--acc)}}
.chip{{font-size:.7rem;padding:1px 6px;border:1px dashed var(--line);color:var(--muted)}}
.pred{{display:grid;gap:2px;font-size:.92rem;background:var(--soft);padding:8px 10px;border-left:3px solid var(--ink)}}
.pred .sub,.sub{{color:var(--muted);font-size:.8rem}}
.star{{color:var(--acc);letter-spacing:.05em}}
.quick{{font-size:.86rem}}
details.px summary{{font-size:.76rem;color:var(--muted);cursor:pointer}}
details.px table{{border-collapse:collapse;width:100%;font-size:.8rem;margin-top:4px}}
details.px td{{padding:3px 6px 3px 0;border-bottom:1px dashed var(--line);vertical-align:top}}
.lines{{list-style:none;margin:0;padding:0;display:grid;gap:5px;border-top:1px dashed var(--line);padding-top:8px;font-size:.86rem}}
.tag{{font-size:.68rem;padding:1px 6px;margin-right:4px;border:1px solid var(--line)}}
.tag.bet{{background:var(--acc);border-color:var(--acc);color:var(--panel)}}
.tag.obs{{border-style:dashed}}
.hit{{font-size:.7rem;padding:0 5px;margin-left:2px;border:1px solid}}
.hit.w{{color:var(--ok)}}.hit.l{{color:var(--bad)}}.hit.p{{color:var(--push)}}
.bp{{font-size:.72rem;padding:1px 7px;margin-left:4px;font-weight:700;color:var(--panel)}}
.bp.w{{background:var(--ok)}}.bp.l{{background:var(--bad)}}.bp.p{{background:var(--push)}}.bp.wait{{background:var(--muted)}}
.donelist{{display:grid;gap:6px}}
details.done{{background:var(--panel);border:1px solid var(--line)}}
details.done summary{{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;justify-content:space-between;padding:8px 12px;cursor:pointer;list-style:none}}
details.done summary::-webkit-details-marker{{display:none}}
.dm{{display:flex;align-items:center;gap:6px}}
.mini{{width:22px;height:22px}}
.dr{{font-size:.85rem}}
.dbody{{padding:0 12px 12px;display:grid;gap:8px}}
table.tiers{{border-collapse:collapse;background:var(--panel);font-size:.88rem}}
table.tiers td,table.tiers th{{padding:5px 14px;border-bottom:1px solid var(--line);text-align:left}}
table.tiers th{{font-size:.74rem;color:var(--muted);font-weight:500}}
details.more{{background:var(--panel);border:1px solid var(--line);padding:10px 14px}}
details.more summary{{cursor:pointer;font-weight:500}}
.note{{font-size:.78rem;color:var(--muted);max-width:75ch}}
@media (max-width:420px){{h1{{font-size:2rem}}.grid{{grid-template-columns:1fr}}}}
</style>
<div class="wrap">
  <div class="top"><h1>NFL {a.week}주차 보드</h1><div class="muted">갱신 {now} PT · 표시 전용(정본: 다이제스트·발행문) · 시간은 PT(캘리포니아)</div></div>
  <div class="chips">
    <div class="stat"><span class="k">승자 예측 시즌</span><span class="v">{ms.get("w", 0)}-{ms.get("l", 0)}</span></div>
    <div class="stat"><span class="k">실베팅 시즌</span><span class="v">{sw}-{sl}</span></div>
    <div class="stat"><span class="k">손익</span><span class="v">{su:+.2f}u</span></div>
    <div class="stat"><span class="k">승자 예측 이번 주</span><span class="v">{wm.get("w", 0)}-{wm.get("l", 0)}</span></div>
  </div>
  <div class="headline">{headline}</div>
  <section class="legend">
    <div><b>읽는 법</b> — 보라색 낱말에 손가락·마우스를 대면 뜻이 나와요.</div>
    <div><span class="star">★</span> = <b>이길 확률이 높은 정도</b>(2018~25 실제 적중 ★ 50% · ★★ 61% · ★★★ 71% · ★★★★ 82%). <b>돈 버는 신호가 아니에요</b> — 별 4개 팀도 {term("스프레드")}는 절반만 맞았어요.</div>
    <div>{term("스프레드")} = 점수 차 핸디 · {term("총점")} = 두 팀 점수 합이 기준보다 많을지(Over)·적을지(Under) · {term("ML")} = 그냥 이길 팀 · {term("티저")} = 핸디를 6점 유리하게 받는 대신 2경기를 묶어 둘 다 맞혀야 함</div>
    <div>{term("방향")} = 예측에서 나온 쪽(동전 — 적중률만 봄) · {term("관찰", "관찰만")} = 돈 안 건 기록 · <span class="tag bet">실베팅</span> = Paul 이 실제로 건 것(주황 테두리 카드) · 맞힘/틀림 = 예측·관찰 결과, <span class="bp w">승</span><span class="bp l">패</span> = 실베팅 결과</div>
  </section>
  <h2>아직 안 한 경기</h2>
  {f'<section class="grid">{"".join(c for _, c in pre_cards)}</section>' if pre_cards else '<p class="muted">이번 주 경기가 모두 끝났어요.</p>'}
  {f'<h2>끝난 경기 <span class="muted" style="font-size:.9rem">— 눌러서 펼치기</span></h2><section class="donelist">{"".join(done_rows)}</section>' if done_rows else ""}
  <h2>별점별 승자 적중 — 시즌(시장 예측)</h2>
  <div><table class="tiers"><thead><tr><th>별</th><th>W-L</th><th>올해</th><th>2018~25 기대</th></tr></thead><tbody>{star_rows}</tbody></table>
  <p class="note">1~4주차 일부는 마감 배당으로 소급한 기록이에요. 표본이 작아 몇 주는 기대와 어긋나는 게 정상이에요.</p></div>
  <details class="more"><summary>숫자 자세히</summary>
    <p>실베팅 시즌 {sw}-{sl} · {su:+.2f}u · 평균 {term("CLV")} {(sum(cvs) / len(cvs)) if cvs else 0:+.1f}%p(n {len(cvs)}) — 마감보다 비싸게 샀으면 −, 싸게 샀으면 +. 수십 건이 쌓여야 의미가 있어요.</p>
    <p>승자 예측 시즌 · 시장 {ms.get("w", 0)}-{ms.get("l", 0)} · 발행 {psum.get("발행", {}).get("w", 0)}-{psum.get("발행", {}).get("l", 0)} · 우리 모델 {psum.get("모델", {}).get("w", 0)}-{psum.get("모델", {}).get("l", 0)}</p>
  </details>
  <p class="note">표시 전용 — 재계산 없음 · 정본은 다이제스트(DIGEST.md)·발행문·picks.csv · 배당은 DraftKings(ESPN), 경기가 시작되면 ESPN 에서 사라져 끝난 경기엔 표시하지 않아요.</p>
</div>'''
    out = a.out or os.path.join(os.path.dirname(HERE), "board", f"board-w{a.week:02d}.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write(page)
    print("wrote", out, f"{len(page):,} bytes")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
