"""NFL 주간 보드 HTML(2026-10-04 Paul 「MLB 보드처럼 — 팀명·로고 같이」).
  python nfl_board.py --week 4 [--out ../board/board-w04.html]
표시 전용 — 정본은 DIGEST.md·발행문·picks.csv. 값을 옮겨 한 화면에 얹는다(가격 확률만 배당에서 계산).
로고는 Artifact CSP 가 외부 이미지를 막아 data: URI 로 넣는다(ESPN 64px PNG, data/cache/logos 캐시)."""
import argparse, base64, csv, glob, html, json, os, re, sys, urllib.request
from collections import defaultdict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nfl_pull as N   # noqa: E402
import picks as P      # noqa: E402

KR = N.TEAM_KR
esc = html.escape


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
    import predictions as PR
    preds = defaultdict(dict)
    for r in N.rd(PR.path(a.week)):
        preds[r["game"]][r["src"]] = r
    psum = PR.summary(PR.all_rows())
    games.sort(key=lambda g: g["kickoff_utc"])

    def result_of(r, gk):
        if r.get("result"):
            return r["result"]
        lv = live.get(gk)
        if lv and lv["state"] == "STATUS_FINAL":
            wl, _ = P._grade_one(r, {"away_score": lv["sa"], "home_score": lv["sh"]})
            return wl or ""
        return ""

    def chip(res):
        return {"W": '<span class="res w">적중</span>', "L": '<span class="res l">실패</span>', "P": '<span class="res p">환불</span>'}.get(res, "")
    # 실베팅 요약(시즌 전체 + 이번 주)
    allp = [r for r in P.rd(P.PICKS) if r.get("status") == "placed"]
    done = [r for r in allp if r.get("result") in ("W", "L", "P")]
    su = sum(P.fnum(r.get("units")) or 0 for r in done)
    sw = sum(1 for r in done if r["result"] == "W"); sl = sum(1 for r in done if r["result"] == "L")
    cvs = [P.fnum(r.get("clv_prob")) for r in done if P.fnum(r.get("clv_prob")) is not None]
    wk_bets = [r for r in picks if r.get("status") == "placed"]
    cards = []
    for g in games:
        A, H = g["away"], g["home"]; gk = f"{A}@{H}"
        lv = live.get(gk, {})
        hl = P.fnum(g.get("spread_home")); tl = P.fnum(g.get("total"))
        sh_, sa_ = N._novig(g.get("sp_home_odds"), g.get("sp_away_odds"))
        po, pu = N._novig(g.get("over_odds"), g.get("under_odds"))
        ma, mh = N._novig(g.get("ml_away"), g.get("ml_home"))
        st = lv.get("state", g.get("status", ""))
        if st == "STATUS_FINAL":
            status = f'<span class="state fin">종료</span> <b class="score">{esc(A)} {esc(str(lv.get("sa")))} – {esc(str(lv.get("sh")))} {esc(H)}</b>'
        elif st == "STATUS_IN_PROGRESS":
            status = f'<span class="state live">진행 중</span> <b class="score">{esc(A)} {esc(str(lv.get("sa")))} – {esc(str(lv.get("sh")))} {esc(H)}</b> <span class="muted">{esc(lv.get("detail", ""))}</span>'
        else:
            status = f'<span class="state pre">예정</span> <span class="muted">{esc(g["kickoff_et"].split(" ", 1)[0])} {esc(g["kickoff_pt"])} PT</span>'
        rows = by.get(gk, [])
        bets = [r for r in rows if r.get("status") == "placed"]
        dirs = [r for r in rows if r["grade"] == "방향(발행)"]
        obs = [r for r in rows if r["grade"] in ("바람 언더(관찰)", "티저 다리(관찰)") or r["grade"].startswith("각도 관찰")]
        pub = pubs.get(gk, {})

        def team(t, name):
            return (f'<div class="team"><img src="{logo_uri(t)}" alt="" width="40" height="40">'
                    f'<div><div class="tname">{esc(name or t)}</div><div class="tkr">{esc(KR.get(t, ""))} · {esc(t)}</div></div></div>')
        price = []
        if hl is not None:
            price.append(f'<div class="mk"><span class="lab">스프레드</span><span>{esc(H)} {hl:+g} <em>{esc(g.get("sp_home_odds") or "")}</em> · {esc(A)} {-hl:+g} <em>{esc(g.get("sp_away_odds") or "")}</em></span>'
                         f'<span class="prob">{esc(H)} {pct(sh_)} / {esc(A)} {pct(sa_)}</span></div>')
        if tl is not None:
            price.append(f'<div class="mk"><span class="lab">총점</span><span>{tl:g} · O <em>{esc(g.get("over_odds") or "")}</em> · U <em>{esc(g.get("under_odds") or "")}</em></span>'
                         f'<span class="prob">Over {pct(po)} / Under {pct(pu)}</span></div>')
        if g.get("ml_home"):
            price.append(f'<div class="mk"><span class="lab">ML</span><span>{esc(A)} <em>{esc(g.get("ml_away"))}</em> · {esc(H)} <em>{esc(g.get("ml_home"))}</em></span>'
                         f'<span class="prob">승리 {esc(A)} {pct(ma)} / {esc(H)} {pct(mh)}</span></div>')
        dir_txt = " · ".join(esc(r["side"]) + chip(result_of(r, gk)) for r in dirs)
        line_items = []
        if pub.get("판단") or dir_txt:
            line_items.append(f'<li><span class="tag pub">발행</span> 판단 <b>{esc(pub.get("판단", "—"))}</b>' + (f' · 방향 {dir_txt}' if dir_txt else "")
                              + (f'<div class="sub">굳이 하나만: {esc(pub["굳이"])}</div>' if pub.get("굳이") else "") + "</li>")
        for r in obs:
            lab = "바람" if r["grade"].startswith("바람") else "티저" if r["grade"].startswith("티저") else r["grade"].split("(")[0].replace("각도 관찰 ", "")
            line_items.append(f'<li><span class="tag obs">관찰 {esc(lab)}</span> {esc(r["side"])} {chip(result_of(r, gk))}<div class="sub">{esc(r.get("note", ""))}</div></li>')
        for r in bets:
            stake = P.fnum(r.get("stake")) or 1
            u = r.get("units") or ""
            line_items.append(f'<li><span class="tag bet">실베팅</span> <b>{esc(r["side"])}</b> {esc(r.get("odds", ""))} · {stake:g}u {chip(result_of(r, gk))}'
                              + (f' <span class="muted">{float(u):+.2f}u</span>' if u else "")
                              + (f' <span class="muted">CLV {esc(r["clv_prob"])}%p</span>' if r.get("clv_prob") else "") + "</li>")
        pr = preds.get(gk, {})
        fin = lv.get("state") == "STATUS_FINAL"
        win = (H if float(lv.get("sh") or 0) > float(lv.get("sa") or 0) else A if float(lv.get("sa") or 0) > float(lv.get("sh") or 0) else "") if fin else ""

        def pchip(r):
            if not fin or not win:
                return ""
            return chip("W" if r.get("pick") == win else "L")
        pred_html = ""
        m_, d_, b_ = pr.get("시장"), pr.get("모델"), pr.get("발행")
        if m_:
            pp = P.fnum(m_.get("p_pick"))
            pred_html = (f'<div class="pred"><span class="lab">예측</span><span>이길 팀 <b>{esc(m_["pick"])} {pct(pp)}</b> <span class="star" title="2018~25 이 별 승자 적중 {PR.STAR_HIT.get(PR.stars(pp), "")}">{PR.star_str(pp)}</span>{pchip(m_)}'
                         f' · 예상 {esc(A)} {esc(m_["score_away"])} – {esc(H)} {esc(m_["score_home"])} <span class="muted">(시장)</span></span>')
            if b_:
                pred_html += (f'<span>발행 <b>{esc(b_["pick"])} {pct(P.fnum(b_.get("p_pick")))}</b>{pchip(b_)} · {esc(A)} {esc(b_["score_away"])} – {esc(H)} {esc(b_["score_home"])}</span>')
            if d_:
                pred_html += (f'<span class="muted">모델 {esc(A)} {esc(d_["score_away"])} – {esc(H)} {esc(d_["score_home"])} → {esc(d_["pick"])}'
                              + (" ⚠️ 엇갈림" if d_["pick"] != m_["pick"] else "") + "</span>")
            pred_html += "</div>"
        cards.append(f'''<article class="card{' hasbet' if bets else ''}">
  <header class="match">{team(A, lv.get("na"))}<span class="at">@</span>{team(H, lv.get("nh"))}</header>
  {pred_html}
  <div class="meta">{status}{' <span class="chip">디비전</span>' if g.get("div_game") == "1" else ""}{' <span class="chip">중립</span>' if g.get("neutral") == "1" else ""}</div>
  <div class="mkts">{"".join(price) or '<div class="muted">가격 없음(경기 시작 뒤엔 사라짐)</div>'}</div>
  {f'<ul class="lines">{"".join(line_items)}</ul>' if line_items else ""}
</article>''')
    now = datetime.now().strftime("%m/%d %H:%M")
    bet_rows = "".join(
        f'<tr><td>{esc(r["game"])}</td><td><b>{esc(r["side"])}</b></td><td class="num">{esc(r.get("odds", ""))}</td><td class="num">{(P.fnum(r.get("stake")) or 1):g}u</td>'
        f'<td>{chip(result_of(r, r["game"])) or "<span class=muted>대기</span>"}</td></tr>' for r in wk_bets)
    page = f'''<title>NFL {a.week}주차 보드</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Saira+Extra+Condensed:wght@600;800&family=Noto+Sans+KR:wght@400;500;700&family=IBM+Plex+Mono:wght@500&display=swap" rel="stylesheet">
<style>
/* 구장 라인 감성 — 잔디 기운의 중립색 위에 흰 분필선, 강조는 엔드존 파일런 주황. 카드 그리드(폰 1열) */
:root{{--bg:#eef2ec;--panel:#ffffff;--ink:#14231b;--muted:#5d6b62;--line:#d4ddd3;--acc:#e8590c;--ok:#1f8a4c;--bad:#c2362b;--push:#8a7a1f;
  --display:"Saira Extra Condensed","Arial Narrow",sans-serif;--body:"Noto Sans KR","Apple SD Gothic Neo","Malgun Gothic",sans-serif;--mono:"IBM Plex Mono",ui-monospace,monospace}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#0f1712;--panel:#16211a;--ink:#e6efe7;--muted:#97a69b;--line:#26352b;--acc:#ff7a2e;--ok:#4cc27a;--bad:#ef6a5f;--push:#cdbb52;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#0f1712;--panel:#16211a;--ink:#e6efe7;--muted:#97a69b;--line:#26352b;--acc:#ff7a2e;--ok:#4cc27a;--bad:#ef6a5f;--push:#cdbb52;color-scheme:dark}}
body{{background:var(--bg);color:var(--ink);font-family:var(--body);font-size:14px;line-height:1.5}}
.wrap{{max-width:1180px;margin:0 auto;padding-inline:16px;padding-block:20px 40px;display:grid;gap:18px}}
h1{{font-family:var(--display);font-weight:800;font-size:2.4rem;letter-spacing:.02em;margin:0;text-wrap:balance;line-height:1}}
.top{{display:flex;flex-wrap:wrap;gap:12px 24px;align-items:end;justify-content:space-between;border-bottom:2px solid var(--ink);padding-bottom:10px}}
.muted{{color:var(--muted)}}
.summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}}
.stat{{background:var(--panel);border:1px solid var(--line);padding:10px 12px}}
.stat .k{{font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}}
.stat .v{{font-family:var(--display);font-size:1.7rem;font-weight:600;font-variant-numeric:tabular-nums}}
table{{border-collapse:collapse;width:100%;background:var(--panel)}}
.tbl{{overflow-x:auto;border:1px solid var(--line)}}
td,th{{padding:6px 10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}}
th{{font-size:.72rem;letter-spacing:.06em;color:var(--muted);font-weight:500}}
.num{{font-family:var(--mono);font-variant-numeric:tabular-nums}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px}}
.card{{background:var(--panel);border:1px solid var(--line);padding:14px;display:grid;gap:10px;min-width:0}}
.card.hasbet{{border-color:var(--acc);box-shadow:inset 0 3px 0 var(--acc)}}
.match{{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:8px}}
.team{{display:flex;align-items:center;gap:8px;min-width:0}}
.match .team:last-child{{flex-direction:row-reverse;text-align:right}}
.team img{{width:40px;height:40px;flex:none}}
.tname{{font-family:var(--display);font-weight:600;font-size:1.15rem;line-height:1.1}}
.tkr{{font-size:.75rem;color:var(--muted)}}
.at{{font-family:var(--display);color:var(--muted);font-size:1.1rem}}
.meta{{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:.85rem}}
.state{{font-size:.7rem;letter-spacing:.05em;padding:1px 6px;border:1px solid var(--line)}}
.state.live{{color:var(--acc);border-color:var(--acc)}}
.state.fin{{color:var(--ink)}}
.score{{font-family:var(--mono);font-variant-numeric:tabular-nums}}
.chip{{font-size:.7rem;padding:1px 6px;border:1px dashed var(--line);color:var(--muted)}}
.mkts{{display:grid;gap:4px;border-top:1px dashed var(--line);padding-top:8px}}
.mk{{display:grid;grid-template-columns:64px 1fr;gap:2px 8px;font-size:.85rem}}
.mk .lab{{color:var(--muted);font-size:.75rem;grid-row:span 2;align-self:start;padding-top:2px}}
.mk em{{font-style:normal;font-family:var(--mono);font-size:.8rem}}
.mk .prob{{color:var(--muted);font-size:.78rem}}
.pred{{display:grid;gap:3px;font-size:.88rem;background:var(--bg);padding:8px 10px;border-left:3px solid var(--ink)}}
.pred .lab{{font-size:.7rem;letter-spacing:.06em;color:var(--muted)}}
.star{{color:var(--acc);letter-spacing:.05em}}
.lines{{list-style:none;margin:0;padding:0;display:grid;gap:6px;border-top:1px dashed var(--line);padding-top:8px;font-size:.85rem}}
.lines .sub{{color:var(--muted);font-size:.76rem}}
.tag{{font-size:.68rem;letter-spacing:.04em;padding:1px 6px;margin-right:4px;border:1px solid var(--line)}}
.tag.bet{{background:var(--acc);border-color:var(--acc);color:var(--panel)}}
.tag.pub{{color:var(--ink)}}
.tag.obs{{color:var(--muted);border-style:dashed}}
.res{{font-size:.7rem;padding:0 6px;margin-left:4px;font-weight:700}}
.res.w{{color:var(--ok);border:1px solid var(--ok)}}
.res.l{{color:var(--bad);border:1px solid var(--bad)}}
.res.p{{color:var(--push);border:1px solid var(--push)}}
.note{{font-size:.78rem;color:var(--muted);max-width:70ch}}
@media (max-width:420px){{h1{{font-size:2rem}}.grid{{grid-template-columns:1fr}}}}
</style>
<div class="wrap">
  <div class="top"><h1>NFL {a.week}주차 보드</h1><div class="muted">갱신 {now} PT · DK 배당(ESPN) · 발행 10/4 판 · 표시 전용(정본은 다이제스트·발행문·picks.csv)</div></div>
  <section class="summary">
    <div class="stat"><div class="k">실베팅 시즌</div><div class="v">{sw}-{sl}</div></div>
    <div class="stat"><div class="k">유닛 손익</div><div class="v">{su:+.2f}u</div></div>
    <div class="stat"><div class="k">평균 가격 CLV</div><div class="v">{(sum(cvs) / len(cvs)) if cvs else 0:+.1f}%p</div></div>
    <div class="stat"><div class="k">이번 주 실베팅</div><div class="v">{len(wk_bets)}건</div></div>
    <div class="stat"><div class="k">승자 예측 · 시장</div><div class="v">{psum.get("시장", {}).get("w", 0)}-{psum.get("시장", {}).get("l", 0)}</div></div>
    <div class="stat"><div class="k">승자 예측 · 발행</div><div class="v">{psum.get("발행", {}).get("w", 0)}-{psum.get("발행", {}).get("l", 0)}</div></div>
  </section>
  {f'<div class="tbl"><table><thead><tr><th>경기</th><th>베팅</th><th>배당</th><th>크기</th><th>결과</th></tr></thead><tbody>{bet_rows}</tbody></table></div>' if wk_bets else ""}
  <section class="grid">{"".join(cards)}</section>
  <p class="note">확률은 DK 배당에서 수수료를 뺀 값. 「발행」은 claude.ai 발행 세션 판단, 「관찰」은 돈을 걸지 않는 페이퍼 기록(바람 15mph+ 언더 · A1 원정 큰 페이버릿 반대 · A2 드라이브 우위 언더독 반대), 「실베팅」은 Paul 의 실제 베팅. 주황 테두리 = 실베팅 걸린 경기.</p>
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
