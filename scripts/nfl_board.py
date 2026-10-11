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
    "방향": "예측 점수에서 나온 스프레드·총점 쪽. 실력으로는 동전(≈50%)이라 돈 근거가 아니고 적중률만 잰다",
    "관찰": "돈을 걸지 않고 맞는지만 기록하는 페이퍼 실험",
    "CLV": "내가 산 가격이 경기 직전 마감 가격보다 좋았는지(+ = 싸게 샀다). 승패보다 빨리 실력이 보이는 숫자",
}


def term(word, label=None):
    return f'<abbr class="term" title="{esc(TERM[word])}">{esc(label or word)}</abbr>'


# 주차 비교표·발행문 펼침(2026-10-11 Paul 「MLB 보드처럼 카드 누르면 설명 · 전 경기 표 · 발행 설명문·보완 다 넣어」)
EXTRA_CSS = """
.tblwrap{overflow-x:auto;background:var(--panel);border:1px solid var(--line)}
table.cmp{border-collapse:collapse;width:100%;font-size:.84rem;min-width:900px}
table.cmp th{font-size:.72rem;color:var(--muted);font-weight:500;text-align:left;padding:6px 8px;border-bottom:2px solid var(--line);white-space:nowrap}
table.cmp td{padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap;vertical-align:middle}
table.cmp tbody tr:hover{background:var(--soft)}
table.cmp .mini{vertical-align:middle}
thead th.sortable{cursor:pointer;user-select:none}
thead th.sortable:hover{color:var(--acc)}
thead th.s-d::after{content:" \\25BC";font-size:.7em;color:var(--acc)}
thead th.s-a::after{content:" \\25B2";font-size:.7em;color:var(--acc)}
tbody tr[data-g],.card[data-g]{cursor:pointer}
.publist{display:grid;gap:6px}
details.pubd{background:var(--panel);border:1px solid var(--line)}
details.pubd>summary{padding:8px 12px;cursor:pointer;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
details.pubd .md{padding:0 14px 14px;font-size:.88rem;overflow-wrap:anywhere}
.md h4{font-size:1rem;margin:10px 0 4px}
.md p{margin:4px 0}
.md .li{margin:2px 0}
.md .qt{border-left:3px solid var(--line);padding:4px 8px;color:var(--muted);margin:6px 0;font-size:.82rem}
.md hr{border:0;border-top:1px dashed var(--line)}
.md a{color:var(--term)}
.mdt{overflow-x:auto;margin:6px 0}
.mdt table{border-collapse:collapse;font-size:.8rem}
.mdt th,.mdt td{border:1px solid var(--line);padding:3px 7px;text-align:left;vertical-align:top}
.pubv{border-top:1px dashed var(--line);padding-top:8px;margin-top:8px}
.pubv:first-child{border-top:0;margin-top:0}
.pubh{font-size:.72rem;color:var(--muted);font-family:var(--mono)}
.pubv.supp{background:var(--soft);padding:8px 10px}
details.prevv{margin-top:10px;border:1px dashed var(--line);padding:4px 10px}
details.prevv>summary{cursor:pointer;font-size:.8rem;color:var(--muted)}
details.flash{outline:2px solid var(--acc);outline-offset:2px;transition:outline-color 1.2s ease}
details.flash.off{outline-color:transparent}
a.goto{font-size:.8rem;color:var(--term);cursor:pointer;text-decoration:underline}
:root{--pk:#0b5fc0;--pkbg:#e4efff}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--pk:#86bfff;--pkbg:#1b2a3f}}
:root[data-theme="dark"]{--pk:#86bfff;--pkbg:#1b2a3f}
.pk{color:var(--pk);font-weight:700}
span.pk{background:var(--pkbg);padding:0 3px;border-radius:3px}
.tname.pk{text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:3px}
abbr.tm{text-decoration:none;border-bottom:1px dotted var(--muted);cursor:help}
table.cmp{min-width:1100px}
"""

# 표 머리 클릭 정렬(숫자 열 첫 클릭 큰 값부터 · 경기·시간 열은 킥오프 순) + 줄·카드·「보기」 클릭 → 그 경기 발행문 펼침·스크롤
# (MLB board_publish._SORT_JS 와 같은 동작 — 카드 안의 배당 접기·용어 풀이를 누를 땐 이동하지 않는다).
BOARD_JS = """
<script>
(function(){
  function openPub(g){
    var d=document.querySelector('details.pubd[data-p="'+g+'"]');if(!d)return;
    d.open=true;d.scrollIntoView({behavior:"smooth",block:"start"});
    setTimeout(function(){if(Math.abs(d.getBoundingClientRect().top)>60)d.scrollIntoView({block:"start"});},700);
    d.classList.add("flash");d.classList.remove("off");
    setTimeout(function(){d.classList.add("off");},900);
    setTimeout(function(){d.classList.remove("flash","off");},2400);
  }
  var tb=document.querySelector('.tblwrap table');
  if(tb&&tb.tHead){
    var ths=tb.tHead.rows[0].cells,tbody=tb.tBodies[0];
    [].forEach.call(tbody.rows,function(r,i){r.dataset.i=i;});
    var cur=-1,dir=0;
    function num(tr,i){
      var c=tr.cells[i];if(!c)return null;
      if(c.dataset.s!==undefined){return c.dataset.s===""?null:parseFloat(c.dataset.s);}
      return null;
    }
    function apply(){
      var rs=[].slice.call(tbody.rows);
      rs.sort(function(a,b){
        var x=num(a,cur),y=num(b,cur);
        if(x===null&&y===null)return a.dataset.i-b.dataset.i;
        if(x===null)return 1;if(y===null)return -1;
        if(x!==y)return dir*(x-y);
        return a.dataset.i-b.dataset.i;
      });
      rs.forEach(function(r){tbody.appendChild(r);});
    }
    [].forEach.call(ths,function(th,i){
      var has=[].some.call(tbody.rows,function(r){return r.cells[i]&&r.cells[i].dataset.s!==undefined;});
      if(!has)return;
      th.classList.add("sortable");th.title="누르면 이 열 기준 정렬 · 다시 누르면 반대";
      th.addEventListener("click",function(e){
        if(e.target.closest("abbr"))return;
        if(cur===i){dir=-dir;}else{[].forEach.call(ths,function(t){t.classList.remove("s-a","s-d");});cur=i;dir=(i===0||i===1)?1:-1;}
        th.classList.remove("s-a","s-d");th.classList.add(dir>0?"s-a":"s-d");apply();
      });
    });
    [].forEach.call(tbody.rows,function(tr){
      var g=tr.dataset.g;if(!g)return;tr.title="누르면 아래 발행문·보완으로 이동";
      tr.addEventListener("click",function(){openPub(g);});
    });
  }
  [].forEach.call(document.querySelectorAll('.card[data-g]'),function(c){
    c.title="누르면 아래 발행문·보완으로 이동";
    c.addEventListener("click",function(e){
      if(e.target.closest("details,summary,abbr,a"))return;
      openPub(c.dataset.g);
    });
  });
  [].forEach.call(document.querySelectorAll('a.goto[data-g]'),function(a){
    a.addEventListener("click",function(e){e.preventDefault();openPub(a.dataset.g);});
  });
})();
</script>"""


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


def name_kr(t):
    """한글 팀 이름 — 지역 + 팀(「휴스턴 텍선스」 · 2026-10-11 Paul 「지역 팀이름 둘다」, 종전 별칭만 「텍선스」)."""
    return KR.get(t) or t


def mark_teams(h, teams, pick):
    """발행문 HTML 안의 팀 약칭 → 우리 픽은 색(span.pk), 상대는 마우스를 대면 지역+팀 이름(abbr.tm). 태그 안은 건드리지 않는다."""
    codes = [t for t in teams if t]
    if not codes:
        return h
    pat = re.compile(r"(?<![A-Za-z])(" + "|".join(map(re.escape, sorted(codes, key=len, reverse=True))) + r")(?![A-Za-z])")

    def one(m):
        t = m.group(1)
        if t == pick:
            return f'<span class="pk" title="{esc(name_kr(t))} · 우리 픽(이길 팀 예측)">{t}</span>'
        return f'<abbr class="tm" title="{esc(name_kr(t))}">{t}</abbr>'
    return "".join(seg if seg.startswith("<") else pat.sub(one, seg) for seg in re.split(r"(<[^>]+>)", h))


def pct(v):
    return f"{100 * v:.0f}%" if v is not None else "—"


# 발행문 경기 머리 — 「🏈 CIN@MIA …」(3판까지) · 「## 🏈 CIN@MIA …」(6판) · 보완 글의 「**CIN@MIA**」 셋 다 받는다(2026-10-11).
GK_HEAD = re.compile(r"(?m)^(?:#{1,4}\s*)?(?:🏈\s*|\*\*)([A-Z]{2,3}@[A-Z]{2,3})\b[^\n]*$")
# 경기 절 안에서 이 줄이 나오면 그 경기 글은 끝 — 나머지는 파일 공통(머리말·요약·출처·감사 줄)으로 돌린다.
PUB_END = re.compile(r"(?m)^(?:---\s*$|#{1,6}\s|\*\*(?:🏁|판단|오후|NFL)|🏁|Sources:|> |기록용 줄|아직 확인이 남은)")


def pub_files(wd):
    """발행-*.md 시각순. 같은 판(발행-MMDD-HHMM)에 「최종」 사본이 있으면 그것만 쓴다(10/11 08:40 판 이중 저장)."""
    groups = defaultdict(list)
    for p in sorted(glob.glob(os.path.join(wd, "발행-*.md"))):
        parts = os.path.basename(p)[3:-3].split("-")
        key = "-".join(parts[:2]) if len(parts) > 1 and len(parts[1]) == 4 and parts[1].isdigit() else parts[0]
        groups[key].append(p)
    out = []
    for key in sorted(groups):
        ps = groups[key]
        out += [p for p in ps if "최종" in os.path.basename(p)] or ps
    return out


def pub_label(p):
    """발행-1011-0840-8경기-최종.md → 「10/11 08:40 · 8경기 최종」."""
    parts = os.path.basename(p)[3:-3].split("-")
    md = parts[0]; s = f"{md[:2]}/{md[2:]}"; rest = parts[1:]
    if rest and len(rest[0]) == 4 and rest[0].isdigit():
        s += f" {rest[0][:2]}:{rest[0][2:]}"; rest = rest[1:]
    return s + (" · " + " ".join(rest) if rest else "")


def split_pub(txt):
    """발행문 한 파일 → ({경기: [(머리 줄, 본문)]}, 공통 글)."""
    heads = list(GK_HEAD.finditer(txt))
    chunks, common, pos = defaultdict(list), [], 0
    for i, m in enumerate(heads):
        common.append(txt[pos:m.start()])
        end = heads[i + 1].start() if i + 1 < len(heads) else len(txt)
        body = txt[m.end():end]
        t = PUB_END.search(body)
        if t:
            common.append(body[t.start():]); body = body[:t.start()]
        chunks[m.group(1)].append((m.group(0).strip(), body.strip("\n")))
        pos = end
    common.append(txt[pos:])
    lines = [ln for ln in "\n".join(common).splitlines() if ln.strip() != "---"]
    return chunks, re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def pub_lines(wd):
    """발행문(시각순) → {경기: {판단, 굳이}} — 뒤 판이 앞 판을 덮는다(빈 값은 덮지 않음 — 보완 글엔 판단 줄이 없다)."""
    out = defaultdict(dict)
    for p in pub_files(wd):
        chunks, _ = split_pub(open(p, encoding="utf-8").read())
        for gk, lst in chunks.items():
            for _, b in lst:
                j = re.search(r"(?m)^- 판단:\s*([^\n]+)", b); k = re.search(r"(?m)^- 굳이 하나만:\s*([^\n]+)", b)
                if j:
                    out[gk]["판단"] = j.group(1).strip()
                if k:
                    out[gk]["굳이"] = k.group(1).strip()
    return out


def md_html(txt):
    """발행문 마크다운 → HTML(머리·굵게·링크·목록·표·인용·구분선만 — 발행문에 쓰는 것만)."""
    def inline(s):
        s = esc(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        return re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    out, tbl = [], []

    def flush():
        if not tbl:
            return
        rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in tbl]
        rows = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c) for c in r if c)]
        if rows:
            out.append('<div class="mdt"><table><thead><tr>' + "".join(f"<th>{inline(c)}</th>" for c in rows[0]) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:]) + "</tbody></table></div>")
        tbl.clear()
    for ln in txt.splitlines():
        if ln.lstrip().startswith("|"):
            tbl.append(ln); continue
        flush()
        if not ln.strip():
            continue
        m = re.match(r"^(\s*)[-*]\s+(.*)$", ln)
        if re.match(r"^#{1,6}\s", ln):
            out.append(f"<h4>{inline(re.sub(r'^#{1,6}\s+', '', ln))}</h4>")
        elif ln.strip() == "---":
            out.append("<hr>")
        elif ln.startswith(">"):
            out.append(f'<div class="qt">{inline(ln.lstrip("> "))}</div>')
        elif m:
            out.append(f'<div class="li" style="margin-left:{0.4 + len(m.group(1)) * 0.35:.2f}em">• {inline(m.group(2))}</div>')
        else:
            out.append(f"<p>{inline(ln)}</p>")
    flush()
    return "".join(out)


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
    # 경기별 발행문·보완 전문 — 카드·표 줄을 누르면 펼쳐지는 곳(MLB 보드 발행문 카드 방식, 2026-10-11 Paul 「카드 누르면 설명」)
    ptext = defaultdict(lambda: {"main": [], "supp": []}); pcommon = []
    for p in pub_files(wd):
        lab = pub_label(p); supp = "보완" in os.path.basename(p)
        chunks, common = split_pub(open(p, encoding="utf-8").read())
        for gk_, lst in chunks.items():
            for h_, b_ in lst:
                ptext[gk_]["supp" if supp else "main"].append((lab, h_, b_))
        if common:
            pcommon.append((lab, common))
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

    mini_used = set()

    def team(t, name, right=False, rec="", pk=False):
        """카드 팀 칸 — 한글 별칭 밑에 약칭 · 이번 시즌 전적(games.csv away_rec/home_rec · 10/11 Paul 「팀명 밑에 이번 시즌 기록」)."""
        mini_used.add(t)
        return (f'<div class="team{" r" if right else ""}" title="{esc(name or t)}"><span class="tlogo lg-{esc(t)}" role="img" aria-label="{esc(t)}"></span>'
                f'<div><div class="tname{" pk" if pk else ""}">{esc(name_kr(t))}</div><div class="tkr">{esc(t)}{(" · " + esc(rec)) if rec else ""}</div></div></div>')

    def mini(t):
        """작은 로고 — 표·펼침 머리에 경기마다 반복돼서(10/11 514KB) 팀별 CSS 배경으로 한 번만 싣는다."""
        mini_used.add(t)
        return f'<span class="mini lg-{esc(t)}" role="img" aria-label="{esc(t)}"></span>'

    pre_cards, done_rows, trows, pick_of, star_of = [], [], [], {}, {}
    for g in games:
        A, H = g["away"], g["home"]; gk = f"{A}@{H}"
        lv = live.get(gk, {})
        st = lv.get("state", g.get("status", ""))
        fin = st == "STATUS_FINAL"
        rows = by.get(gk, [])
        bets = [r for r in rows if r.get("status") == "placed"]
        dirs = [r for r in rows if r["grade"] == "방향(발행)"]
        obs = [r for r in rows if r["grade"] in ("바람 언더(관찰)", "새 정보(관찰)") or r["grade"].startswith("각도 관찰")]   # 티저는 2026-10-10 폐지
        pub = pubs.get(gk, {})
        pr = preds.get(gk, {})
        m_, d_, b_ = pr.get("시장"), pr.get("모델"), pr.get("발행")
        pp = P.fnum(m_.get("p_pick")) if m_ else None
        pick_t = (b_ or m_ or {}).get("pick", ""); pick_of[gk] = pick_t
        star_of[gk] = P.fnum(b_.get("p_pick")) if b_ and b_.get("p_pick") else pp   # 펼침 머리 별점 — 발행 예측 확률(없으면 시장)

        def nm(t):   # 표·끝난 경기 줄의 팀 이름 — 우리 픽은 색
            return f'<span class="{"pk" if t == pick_t else "tn"}">{esc(name_kr(t))}</span>'
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
            pred_html = (f'<div class="pred"><div>이길 팀 <b>{esc(name_kr(m_["pick"]))}({esc(m_["pick"])}) {pct(pp)}</b> '
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
            if r["grade"].startswith("바람"):
                lab = "바람 언더"
            elif r["grade"].startswith("새 정보"):
                lab = "라인 뒤 새 정보"
            else:
                lab = r["grade"].split("(")[0].replace("각도 관찰 ", "각도 ")
            items.append(f'<li><span class="tag obs">{term("관찰", "관찰만")}</span> {lab} <b title="{esc(r.get("note", ""))}">{esc(r["side"])}</b> {hit(result_of(r, gk))}</li>')
        lines = f'<ul class="lines">{"".join(items)}</ul>' if items else ""
        div = '<span class="chip">디비전</span>' if g.get("div_game") == "1" else ""
        neu = '<span class="chip">중립 구장</span>' if g.get("neutral") == "1" else ""
        # ── 주차 전체 비교표 한 줄(MLB 서열표처럼 — 머리 누르면 정렬, 줄 누르면 발행문 펼침 · 10/11 Paul)
        hl0 = P.fnum(g.get("spread_home")); tl0 = P.fnum(g.get("total"))
        if hl0 is None and m_:   # 시작·끝난 경기는 ESPN 배당이 사라져 games.csv 가 빈다 → 예측 기록(킥오프 동결)의 라인
            hl0 = P.fnum(m_.get("line_home"))
        if tl0 is None and m_:
            tl0 = P.fnum(m_.get("total_line"))
        sp_txt = ((f"{H} {hl0:+g}" if hl0 < 0 else f"{A} {-hl0:+g}" if hl0 > 0 else "PK") if hl0 is not None else "—")
        ml_txt, ml_s = "—", ""
        mh0, ma0 = P.fnum(g.get("ml_home")), P.fnum(g.get("ml_away"))
        if mh0 is not None and ma0 is not None:
            fav0 = (H, g["ml_home"], mh0) if mh0 < ma0 else (A, g["ml_away"], ma0)
            ml_txt, ml_s = f"{fav0[0]} {fav0[1]}", f"{-fav0[2]:g}"
        if fin:
            res_txt, res_s = f'<span class="num">{esc(str(lv.get("sa")))} – {esc(str(lv.get("sh")))}</span> {phit(m_) if m_ else ""}', 2
        elif st == "STATUS_IN_PROGRESS":
            res_txt, res_s = f'<span class="state live">진행 중</span> <span class="num">{esc(str(lv.get("sa")))} – {esc(str(lv.get("sh")))}</span>', 1
        else:
            res_txt, res_s = '<span class="muted">예정</span>', 0
        kts = re.sub(r"\D", "", g.get("kickoff_utc", ""))[:12] or ""
        sc_txt = f'{int(float(m_["score_away"]) + 0.5)} – {int(float(m_["score_home"]) + 0.5)}' if m_ else "—"
        dir_cell = " · ".join(esc(r["side"]) + " " + hit(result_of(r, gk)) for r in dirs) or '<span class="muted">—</span>'
        vw0 = verdict_word(pub.get("판단", ""))
        trows.append((g.get("kickoff_utc", ""), f'<tr data-g="{esc(gk)}">'
                      f'<td data-s="{kts}">{mini(A)} {nm(A)} <small class="muted">{esc(A)} · {esc(g.get("away_rec", ""))}</small> @ {mini(H)} {nm(H)} <small class="muted">{esc(H)} · {esc(g.get("home_rec", ""))}</small></td>'
                      f'<td data-s="{kts}">{esc(g["kickoff_et"].split(" ", 1)[0])} {esc(g["kickoff_pt"])}</td>'
                      f'<td data-s="{pp if pp is not None else ""}">{(esc(name_kr(m_["pick"])) + " " + pct(pp)) if m_ else "—"}</td>'
                      f'<td class="star" data-s="{PR.stars(pp) if m_ else ""}">{PR.star_str(pp) if m_ else ""}</td>'
                      f'<td class="num">{esc(A)} {sc_txt} {esc(H)}</td>'
                      f'<td data-s="{abs(hl0) if hl0 is not None else ""}">{esc(sp_txt)}</td>'
                      f'<td class="num" data-s="{tl0 if tl0 is not None else ""}">{f"{tl0:g}" if tl0 is not None else "—"}</td>'
                      f'<td data-s="{ml_s}">{esc(ml_txt)}</td>'
                      f'<td>{dir_cell}</td><td>{esc(vw0) or "—"}</td><td data-s="{res_s}">{res_txt}</td></tr>'))
        if fin:
            bet_s = " ".join(betpill(r, gk) for r in bets)
            done_rows.append(f'''<details class="done{' hasbet' if bets else ''}"><summary>
  <span class="dm">{mini(A)}<b>{nm(A)}</b><small class="muted">{esc(g.get("away_rec", ""))}</small> <span class="num">{esc(str(lv.get("sa")))} – {esc(str(lv.get("sh")))}</span> <b>{nm(H)}</b><small class="muted">{esc(g.get("home_rec", ""))}</small>{mini(H)}</span>
  <span class="dr">{f'예측 {esc(m_["pick"])} <span class="star">{PR.star_str(pp)}</span> {phit(m_)}' if m_ else ''} {bet_s}</span></summary>
  <div class="dbody">{pred_html}{lines}<a class="goto" data-g="{esc(gk)}">발행문·보완 전문 보기 ↓</a></div></details>''')
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
        pre_cards.append((key, f'''<article class="card{' hasbet' if bets else ''}" data-g="{esc(gk)}">
  <header class="match">{team(A, lv.get("na"), rec=g.get("away_rec", ""), pk=A == pick_t)}<span class="at">@</span>{team(H, lv.get("nh"), right=True, rec=g.get("home_rec", ""), pk=H == pick_t)}</header>
  <div class="meta">{status}{div}{neu}</div>
  {pred_html}{mk}{lines}
</article>'''))
    pre_cards.sort(key=lambda x: x[0])
    trows.sort(key=lambda x: x[0])
    cmp_tbl = ('<div class="tblwrap"><table class="cmp"><thead><tr><th>경기</th><th>시간(PT)</th><th>예측 승자</th><th>★</th><th>예상 점수</th>'
               f'<th>{term("스프레드")}</th><th>{term("총점")}</th><th>{term("ML")} 페이버릿</th><th>발행 {term("방향")}</th><th>판단</th><th>결과</th></tr></thead>'
               f'<tbody>{"".join(r for _, r in trows)}</tbody></table></div>')
    # ── 경기별 발행문·보완 전문(최신 발행 + 보완 · 이전 판은 접어 둠)
    pub_secs = []
    if pcommon:
        pub_secs.append('<details class="pubd"><summary><b>발행 공통</b> <span class="muted">— 머리말·요약표·출처·감사 줄(파일별)</span></summary><div class="md">'
                        + "".join(f'<div class="pubv"><div class="pubh">{esc(l)}</div>{md_html(c)}</div>' for l, c in pcommon) + "</div></details>")
    for g in sorted(games, key=lambda x: x.get("kickoff_utc", "")):
        A, H = g["away"], g["home"]; gk = f"{A}@{H}"
        d = ptext.get(gk); pk_ = pick_of.get(gk, "")

        def mk(x):
            return mark_teams(md_html(x), (A, H), pk_)
        if d and (d["main"] or d["supp"]):
            body, mains = "", d["main"]
            if mains:
                l0, h0, b0 = mains[-1]
                body += f'<div class="pubv"><div class="pubh">{esc(l0)} 발행</div>{mk(h0)}{mk(b0)}</div>'
            for l1, h1, b1 in d["supp"]:
                # 보완 머리 「**DEN@LAC** — LAC 오펜스 라인이 더 비어요」 의 뒷말도 보인다(10/11 11:35 보완 — 경기 코드만 떼고)
                h1r = re.sub(r"^(?:#{1,4}\s*)?(?:🏈\s*)?(?:\*\*)?[A-Z]{2,3}@[A-Z]{2,3}(?:\*\*)?\s*(?:[—-]\s*)?", "", h1).strip()
                body += (f'<div class="pubv supp"><div class="pubh">{esc(l1)}{"" if "보완" in l1 else " · 보완"}</div>'
                         + (f'<div style="font-weight:600">{mk(h1r)}</div>' if h1r else "") + f'{mk(b1)}</div>')
            if len(mains) > 1:
                body += ('<details class="prevv"><summary>이전 판 보기 — ' + esc(" · ".join(x[0] for x in mains[:-1])) + "</summary>"
                         + "".join(f'<div class="pubv"><div class="pubh">{esc(l2)} 발행</div>{mk(h2)}{mk(b2)}</div>' for l2, h2, b2 in reversed(mains[:-1]))
                         + "</details>")
            cnt = f"발행 {len(mains)}판" + (f" · 보완 {len(d['supp'])}" if d["supp"] else "")
        else:
            body, cnt = '<p class="muted">아직 이 경기 발행문이 없어요.</p>', "발행문 없음"
        pub_secs.append(f'<details class="pubd" data-p="{esc(gk)}"><summary>{mini(A)} <b class="{"pk" if A == pk_ else ""}">{esc(name_kr(A))}</b> <small class="muted">{esc(g.get("away_rec", ""))}</small> @ <b class="{"pk" if H == pk_ else ""}">{esc(name_kr(H))}</b> <small class="muted">{esc(g.get("home_rec", ""))}</small> {mini(H)} {(f'<span class="star">{PR.star_str(star_of[gk])}</span> <span class="pk">{esc(pk_)} {pct(star_of[gk])}</span> ') if pk_ and star_of.get(gk) is not None else ""}'
                        f'<span class="muted">{esc(g["kickoff_et"].split(" ", 1)[0])} {esc(g["kickoff_pt"])} PT · {cnt}</span></summary><div class="md">{body}</div></details>')
    logo_css = (".mini{display:inline-block;width:22px;height:22px;background-size:contain;background-repeat:no-repeat;vertical-align:middle}"
                + ".tlogo{display:inline-block;width:36px;height:36px;flex:none;background-size:contain;background-repeat:no-repeat}"
                + "".join(f'.lg-{t}{{background-image:url("{logo_uri(t)}")}}' for t in sorted(mini_used)))
    now = datetime.now().strftime("%m/%d %H:%M")
    # ── 이번 주 한 줄 결론
    wk_open_bets = [r for r in wk_bets if not result_of(r, r["game"])]
    wk_done_bets = [r for r in wk_bets if result_of(r, r["game"])]
    wb_w = sum(1 for r in wk_done_bets if result_of(r, r["game"]) == "W"); wb_l = sum(1 for r in wk_done_bets if result_of(r, r["game"]) == "L")
    wm = wsum.get("시장", {})
    verdicts = [verdict_word(pubs.get(f'{g["away"]}@{g["home"]}', {}).get("판단", "")) for g in games
                if live.get(f'{g["away"]}@{g["home"]}', {}).get("state") != "STATUS_FINAL"]
    cand = sum(1 for v in verdicts if v in ("관심", "소액 관심"))
    headline = (f'남은 경기 <b>{len(pre_cards)}</b> · 발행 후보 <b>{cand}</b> · '
                f'이번 주 실베팅 <b>{wb_w}-{wb_l}</b>' + (f'(대기 {len(wk_open_bets)})' if wk_open_bets else "")
                )
    ms = psum.get("시장", {})
    star_rows = "".join(
        f'<tr><td class="star">{"★" * k}</td><td class="num">{w}-{l}</td><td class="num">{(f"{100 * w / (w + l):.0f}%") if w + l else "—"}</td><td class="num muted">{PR.STAR_HIT[k]}</td></tr>'
        for k, (w, l) in ms.get("stars", {}).items())
    page = f'''<meta charset="utf-8"><title>NFL {a.week}주차 보드</title>
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
{EXTRA_CSS}
{logo_css}
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
    <div>{term("스프레드")} = 점수 차 핸디 · {term("총점")} = 두 팀 점수 합이 기준보다 많을지(Over)·적을지(Under) · {term("ML")} = 그냥 이길 팀(10/10부터 주인공)</div>
    <div>{term("방향")} = 예측에서 나온 쪽(동전 — 적중률만 봄) · {term("관찰", "관찰만")} = 돈 안 건 기록 · <span class="tag bet">실베팅</span> = Paul 이 실제로 건 것(주황 테두리 카드) · 맞힘/틀림 = 예측·관찰 결과, <span class="bp w">승</span><span class="bp l">패</span> = 실베팅 결과</div>
    <div><span class="pk">파란 글씨</span> = <b>우리 픽</b>(이길 팀 예측 — 발행 예측, 없으면 시장 예측) · 발행문 속 팀 약칭(HOU 등)에 마우스·손가락을 대면 지역+팀 이름이 나와요.</div>
    <div><b>카드나 표 줄을 누르면</b> 그 경기의 발행문·보완 전문이 아래에서 펼쳐져요. 표 머리(예측 승자·★·스프레드 …)를 누르면 그 기준으로 정렬돼요.</div>
  </section>
  <h2>{a.week}주차 전체 경기 <span class="muted" style="font-size:.9rem">— 머리 누르면 정렬 · 줄 누르면 발행문</span></h2>
  {cmp_tbl}
  <h2>아직 안 한 경기</h2>
  {f'<section class="grid">{"".join(c for _, c in pre_cards)}</section>' if pre_cards else '<p class="muted">이번 주 경기가 모두 끝났어요.</p>'}
  {f'<h2>끝난 경기 <span class="muted" style="font-size:.9rem">— 눌러서 펼치기</span></h2><section class="donelist">{"".join(done_rows)}</section>' if done_rows else ""}
  <h2>발행문·보완 전문 — 경기별 <span class="muted" style="font-size:.9rem">(카드·표 줄을 누르면 여기서 펼쳐져요)</span></h2>
  <section class="publist">{"".join(pub_secs)}</section>
  <h2>별점별 승자 적중 — 시즌(시장 예측)</h2>
  <div><table class="tiers"><thead><tr><th>별</th><th>W-L</th><th>올해</th><th>2018~25 기대</th></tr></thead><tbody>{star_rows}</tbody></table>
  <p class="note">1~4주차 일부는 마감 배당으로 소급한 기록이에요. 표본이 작아 몇 주는 기대와 어긋나는 게 정상이에요.</p></div>
  <details class="more"><summary>숫자 자세히</summary>
    <p>실베팅 시즌 {sw}-{sl} · {su:+.2f}u · 평균 {term("CLV")} {(sum(cvs) / len(cvs)) if cvs else 0:+.1f}%p(n {len(cvs)}) — 마감보다 비싸게 샀으면 −, 싸게 샀으면 +. 수십 건이 쌓여야 의미가 있어요.</p>
    <p>승자 예측 시즌 · 시장 {ms.get("w", 0)}-{ms.get("l", 0)} · 발행 {psum.get("발행", {}).get("w", 0)}-{psum.get("발행", {}).get("l", 0)} · 우리 모델 {psum.get("모델", {}).get("w", 0)}-{psum.get("모델", {}).get("l", 0)}</p>
  </details>
  <p class="note">표시 전용 — 재계산 없음 · 정본은 다이제스트(DIGEST.md)·발행문·picks.csv · 배당은 DraftKings(ESPN), 경기가 시작되면 ESPN 에서 사라져 끝난 경기엔 표시하지 않아요.</p>
</div>''' + BOARD_JS
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
