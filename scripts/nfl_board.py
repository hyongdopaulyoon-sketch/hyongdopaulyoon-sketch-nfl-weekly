"""NFL 주간 보드 HTML(2026-10-04 Paul 「MLB 보드처럼 — 팀명·로고 같이」 · 10/5 「설명도 있고 깔끔하게」 — MLB 보드 세션 상의 반영).
  python nfl_board.py --week 4 [--out ../board/board-w04.html]
표시 전용 — 정본은 DIGEST.md·발행문·picks.csv·predictions.csv. 값을 옮겨 한 화면에 얹는다(가격 확률만 배당에서 계산).
로고는 Artifact CSP 가 외부 이미지를 막아 data: URI 로 넣는다(ESPN 64px PNG, data/cache/logos 캐시).
화면 순서(10/5): 머리(메타 한 줄 + 숫자 칩) → 이번 주 한 줄 결론 → 읽는 법 → 아직 안 한 경기 카드(별 많은 순 → 킥오프)
→ 끝난 경기(한 줄로 접힘) → 별점별 적중 표 → 숫자 자세히(접힘) → 바닥글."""
import argparse, base64, glob, html, json, os, re, sys, urllib.request
from collections import defaultdict
from datetime import datetime, timedelta

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
table.cmp{border-collapse:collapse;width:100%;font-size:.84rem;min-width:720px}
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
.md a{color:inherit;text-decoration:underline}
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
a.goto{font-size:.8rem;color:var(--ink);cursor:pointer;text-decoration:underline}
.pk{font-weight:700}
.cat{border:1px solid var(--line);background:var(--panel);padding:8px 12px;margin:8px 0}
.cat>h5{display:inline-block;margin:0 0 8px;padding:2px 10px;border-radius:4px;background:var(--soft);border:1px solid var(--line);font-size:.78rem;color:var(--ink);font-weight:800;letter-spacing:.06em}
.cat.supp{background:var(--soft)}
.cat .cat{margin:6px 0}
.cat .cat>h5{font-size:.72rem;color:var(--muted);background:var(--panel)}
.mdt table{width:100%}
.mdt th{background:var(--soft)}
.mdt tbody tr:nth-child(even) td{background:color-mix(in srgb,var(--soft) 60%,transparent)}
.mdt td.n,.mdt th.n{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}
.md .pn{font-weight:700;color:var(--ink)}
.md .tm{font-weight:800;color:var(--acc)}
.md .tm.pk{color:var(--acc2)}
.md .st{font-weight:600;color:var(--muted)}
.md .para{margin:2px 0 6px}.md .para .sn{margin:2px 0;line-height:1.6}
.md ul.dl{margin:2px 0 6px;padding-left:20px;columns:2 380px;column-gap:32px}.md ul.dl li{margin:2px 0;break-inside:avoid;line-height:1.5}
.md .li.rich .lh{font-weight:700}.md .sh{font-weight:700}
.md table.vs{table-layout:fixed}.md table.vs th:first-child{width:15%}.md table.vs th:nth-child(2),.md table.vs th:nth-child(3){width:30%}
.md table.vs td{vertical-align:top;line-height:1.5}.md table.vs td.vl{color:var(--muted);font-weight:600}
.md table.vs td.hi{font-weight:700}.md table.vs td.lo{color:var(--muted)}.md table.vs td.vt{color:var(--muted);font-size:.78rem}
.md .h2w{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:10px}
.pth{font-size:.8rem;font-weight:700;margin:12px 0 2px}
.pt2{display:grid;grid-template-columns:1fr 1fr;gap:12px;align-items:start;margin:4px 0}
@media (max-width:980px){.pt2{grid-template-columns:1fr}}
.pt2>div{overflow-x:auto;min-width:0}
table.ptab{width:100%;table-layout:fixed;border-collapse:separate;border-spacing:2px;font-size:.72rem;font-variant-numeric:tabular-nums}
table.ptab th{font-family:var(--mono);font-size:.64rem;color:var(--muted);font-weight:700;text-align:center;padding:3px 1px;white-space:nowrap;overflow:hidden}
table.ptab tr.th0 th{font-family:var(--body);font-size:.84rem;color:var(--ink);text-align:left;padding:2px 2px 4px}
table.ptab tr.gh th{border-top:1px solid var(--line);padding-top:6px}
table.ptab tr.gh th.pnm{text-align:left;color:var(--ink);font-family:var(--body);font-size:.72rem}
table.ptab col.cn{width:128px}table.ptab .pnm{text-align:left}
table.ptab td{padding:4px 1px;border-radius:3px;text-align:center;font-family:var(--mono);font-size:.94em;letter-spacing:-.02em}table.ptab td.n{white-space:nowrap}
table.ptab td.pnm{font-family:var(--body);white-space:normal;border-bottom:1px solid var(--line);border-radius:0}
table.ptab .pnn{display:block;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
table.ptab .psub{display:block;color:var(--muted);font-size:.86em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
table.ptab .stt{display:block;font-size:.86em;color:var(--wait);font-weight:700}
table.ptab .smp{display:inline-block;margin-top:2px;padding:0 5px;border:1px dashed var(--muted);border-radius:4px;font-size:.82em;color:var(--muted)}
table.ptab td.sm{color:var(--muted);font-style:italic;background:repeating-linear-gradient(135deg,transparent 0 4px,rgba(127,127,127,.10) 4px 8px)}
table.ptab td.tx{color:var(--muted);font-size:.92em;white-space:normal}
table.ptab tr.out td{opacity:.5}
table.ptab tr.sum td{color:var(--muted)}table.ptab tr.sum td.hi{font-weight:800;color:var(--ink)}
table.ptab tr.sum td.pnm{background:var(--soft)}
.smnote{margin:4px 0 6px;font-size:.8rem}.sznote{margin:2px 0 6px;font-size:.8rem;color:var(--muted)}.sznote b{color:var(--ink)}.smnote b{color:var(--wait)}
.ptcap{font-size:.7rem;color:var(--muted);margin:2px 0 10px;line-height:1.55}
.ptcap .kc{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 3px 0 6px;vertical-align:-1px}
.reft{margin:2px 0 4px}
.gl{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:3px 22px;font-size:.76rem;line-height:1.45;margin:6px 0 4px;color:var(--ink)}
.gl b{font-family:var(--mono);font-weight:800}.gl i{color:var(--muted);font-style:normal;font-size:.92em}
.gl .gh2{grid-column:1/-1;font-weight:700;color:var(--muted);margin-top:6px;font-size:.74rem}
.gl .kc{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px;border:1px solid var(--line)}
details.gloss{margin-top:4px}details.gloss>summary{cursor:pointer}
nav.dnav{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:.82rem}
nav.dnav a,nav.dnav .cur{border:1px solid var(--line);border-radius:999px;padding:3px 11px;text-decoration:none;color:var(--ink);background:var(--panel)}
nav.dnav a:hover{border-color:var(--ink)}nav.dnav .cur{border-color:var(--ink);font-weight:800}nav.dnav a.hub{font-weight:700}
a.prevb{display:inline-block;border:1px solid var(--line);border-radius:8px;padding:8px 14px;text-decoration:none;color:var(--ink);background:var(--panel)}
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


TEAM_EN = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens", "BUF": "Buffalo Bills",
    "CAR": "Carolina Panthers", "CHI": "Chicago Bears", "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns",
    "DAL": "Dallas Cowboys", "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars", "KC": "Kansas City Chiefs",
    "LA": "Los Angeles Rams", "LAC": "Los Angeles Chargers", "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins",
    "MIN": "Minnesota Vikings", "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers", "SEA": "Seattle Seahawks",
    "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers", "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}


def name_kr(t):
    """보드 팀 이름 — 10/18 Paul 「팀명 영어로 하자 그냥」부터 영어 지역+팀(「Houston Texans」). 함수 이름은 호출부 호환으로 둠
    (10/11 「지역 팀이름 둘다」 한글판 → 영어판). 없는 약칭은 그대로."""
    return TEAM_EN.get(t) or KR.get(t) or t


# ── 설명문 강조(2026-10-24 NBA 보드 d2f02af·1d7eb60 → 10/25 NFL 이식 · Paul 「어제 nba 보드 고친 것들 nfl 도」)
# 우리 픽 팀 = 파랑 굵게(.tm.pk) · 상대 팀 = 주황 굵게(.tm) · 선수 = 굵은 검정(.pn) · 스탯 이름 = 회색 굵게(.st, 칩 상자 없음).
# 흔한 낱말(타깃·캐리·드롭백·야드·득점 …)은 강조하지 않는다. 경기 밖 팀(작년 소속 등)도 강조하지 않는다.
STAT_TERMS = ["EPA/드롭백", "EPA/플레이", "러시당 EPA", "EPA", "CPOE", "야드/시도", "야드/캐리", "야드/타깃", "성공률", "캐치율", "완성률",
              "압박률", "색률", "색 허용률", "놓친 태클", "QB 히트", "득점 드라이브 비율", "드라이브당 득점", "3rd down", "턴오버 마진"]


def team_alias(t):
    """팀 약칭 → [약칭, 영어 풀네임, 별칭(Bears 등)] — 본문 강조용(10/24 NBA 「본문 강조 별칭에 영어 이름 추가」)."""
    full = TEAM_EN.get(t, "")
    return [x for x in (t, full, full.split()[-1] if full else "") if x]


def deco_regex(names, pick_teams=(), opp_teams=()):
    """선수 이름·우리 픽 팀·상대 팀·스탯 이름을 한 번에 찾는 정규식(긴 것 먼저). 이름은 esc 된 꼴로 맞춘다(NBA deco_regex 와 같음)."""
    def alt(xs):
        xs = sorted(set(x for x in xs if x), key=len, reverse=True)
        return "|".join(re.escape(esc(x)) for x in xs) if xs else r"(?!x)x"
    ascii_stats = [x for x in STAT_TERMS if re.match(r"[A-Za-z0-9+]", x)]
    kor_stats = [x for x in STAT_TERMS if x not in ascii_stats]
    pat = (r"(?P<p>(?<![A-Za-z0-9.])(?:" + alt(names) + r")(?![A-Za-z]))"
           r"|(?P<k>(?<![A-Za-z0-9])(?:" + alt(pick_teams) + r")(?![A-Za-z]))"
           r"|(?P<t>(?<![A-Za-z0-9])(?:" + alt(opp_teams) + r")(?![A-Za-z]))"
           r"|(?P<s>(?<![A-Za-z0-9/])(?:" + alt(ascii_stats) + r")(?![A-Za-z])|(?<![0-9가-힣])(?:" + alt(kor_stats) + r")(?![가-힣]))")
    return re.compile(pat)


def deco(html_s, hl, only_pick=False):
    """태그 밖 글자에만 강조. only_pick = 표 칸(팀만 색 — 선수·스탯 강조 없음). 링크(<a>) 안은 건드리지 않는다."""
    if not hl:
        return html_s

    def sub(m):
        if only_pick and not (m.group("k") or m.group("t")):
            return m.group(0)
        x = m.group(0)
        if m.group("k") or m.group("t"):
            tip = TEAM_EN.get(x, "")
            cls = "tm pk" if m.group("k") else "tm"
            t_attr = f' title="{esc(tip)}"' if tip else ""
            return f'<span class="{cls}"{t_attr}>{x}</span>'
        return f'<span class="{"pn" if m.group("p") else "st"}">{x}</span>'
    parts = re.split(r"(<[^>]+>)", html_s)
    in_a = False
    for i, p_ in enumerate(parts):
        if p_.startswith("<"):
            if p_.startswith("<a "):
                in_a = True
            elif p_.startswith("</a"):
                in_a = False
            continue
        if not in_a:
            parts[i] = hl.sub(sub, p_)
    return "".join(parts)


def _top_split(s_, sep=" · "):
    """괄호·「」 밖, 굵게(**) 밖의 sep 에서만 자른다(NBA _top_split)."""
    out_, cur, depth, i, bold = [], [], 0, 0, False
    while i < len(s_):
        if s_.startswith("**", i):
            bold = not bold; cur.append("**"); i += 2; continue
        ch = s_[i]
        if ch in "([「":
            depth += 1
        elif ch in ")]」" and depth:
            depth -= 1
        if depth == 0 and not bold and s_.startswith(sep, i):
            out_.append("".join(cur)); cur = []; i += len(sep); continue
        cur.append(ch); i += 1
    out_.append("".join(cur))
    return out_


def _sentences(s_):
    """괄호·굵게 밖 「. 」에서 문장을 끊는다 — 이니셜(D. Maye)·Jr./Sr.·「1. 」 번호는 끊지 않는다(NBA _sentences)."""
    out_, depth, start, bold = [], 0, 0, False
    for i, ch in enumerate(s_):
        if s_.startswith("**", i) and (i == 0 or s_[i - 1] != "*"):
            bold = not bold
        if ch in "([「":
            depth += 1
        elif ch in ")]」" and depth:
            depth -= 1
        elif ch == "." and depth == 0 and not bold and i + 1 < len(s_) and s_[i + 1] == " " and i > 0:
            initial = s_[i - 1].isupper() and (i < 2 or not s_[i - 2].isalpha())
            if not initial and s_[max(0, i - 2):i] not in ("Jr", "Sr", "vs") and not s_[start:i].strip().isdigit():
                out_.append(s_[start:i + 1].strip()); start = i + 2
    if s_[start:].strip():
        out_.append(s_[start:].strip())
    return out_


def _colon_head(s_):
    """괄호·굵게 밖 첫 「: 」 앞까지를 머리로."""
    depth, bold = 0, False
    for i, ch in enumerate(s_):
        if s_.startswith("**", i) and (i == 0 or s_[i - 1] != "*"):
            bold = not bold
        if ch in "([「":
            depth += 1
        elif ch in ")]」" and depth:
            depth -= 1
        elif depth == 0 and not bold and s_.startswith(": ", i):
            return s_[:i + 1], s_[i + 2:]
    return "", s_


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


_HML = {}


def _h2h_ml(season, week, away, home):
    """맞대결 표용 — nflverse 일정 캐시의 마감 ML (원정, 홈). 없으면 None(10/24 NBA _h2h_ml 이식)."""
    if not _HML:
        try:
            for g in N.rd(os.path.join(N.CACHE, "games.csv")):
                _HML[(g.get("season"), g.get("week"), g.get("away_team"), g.get("home_team"))] = (g.get("away_moneyline") or "", g.get("home_moneyline") or "")
        except OSError:
            _HML[None] = None
    return _HML.get((str(season), str(week), away, home))


def _sgn(x):
    v = P.fnum(x)
    return f"+{v:g}" if v is not None and v > 0 else (f"{v:g}" if v is not None else (x or "—"))


# 「- 항목: NE 값 vs CHI 값 — 판정」 줄 2개+ → 항목 | 원정 | 홈 | 판정 비교표(10/24 NBA cmp_table 「숫자 앞에 어느 팀 숫자인지」 이식)
_VS = re.compile(r"^(?P<lab>[^:：]{1,40})[:：]\s*(?P<t1>[A-Z]{2,3})\s+(?P<v1>.+?)\s+vs\s+(?P<t2>[A-Z]{2,3})\s+(?P<v2>.+?)(?:\s+—\s+(?P<tail>.+))?$")


def _vs_table(rows, teams, hl, inline):
    A, H = teams[:2]
    out = []
    for m in rows:
        v1, v2, tail = m["v1"], m["v2"], m["tail"] or ""
        if not tail:   # 「… CPOE +9.8(1/35위·상위). Williams 값은 얇은 표본…」 — 둘째 값 뒤 문장은 판정·메모 칸으로
            ss = _sentences(v2)
            if len(ss) > 1:
                v2, tail = ss[0].rstrip("."), " ".join(ss[1:])
        if m["t1"] == H:
            v1, v2 = v2, v1
        side = re.search(r"([A-Z]{2,3}) 쪽", tail)
        c1 = c2 = ""
        if side and side.group(1) in (A, H):
            c1, c2 = (" hi", " lo") if side.group(1) == A else (" lo", " hi")
        cell = lambda v: "<br>".join(deco(inline(x.strip()), hl) for x in _top_split(v) if x.strip())
        out.append(f'<tr><td class="vl">{deco(inline(m["lab"].strip()), hl)}</td><td class="vv{c1}">{cell(v1)}</td><td class="vv{c2}">{cell(v2)}</td>'
                   f'<td class="vt">{deco(inline(tail), hl)}</td></tr>')
    head = (f'<tr><th>항목</th><th>{deco(esc(A), hl, only_pick=True)}(원정)</th><th>{deco(esc(H), hl, only_pick=True)}(홈)</th>'
            f'<th>판정·메모</th></tr>')
    return f'<div class="mdt vsw"><table class="vs"><thead>{head}</thead><tbody>{"".join(out)}</tbody></table></div>'


def md_html(txt, hl=None, teams=None):
    """발행문 마크다운 → HTML. hl = deco_regex(...)면 선수·팀·스탯 강조, teams = (원정, 홈, 우리 픽).
    10/25(NBA 10/24 이식): 긴 글머리 줄은 머리 + 「 / 」 묶음·문장마다 줄 · 「 · 」 4개+ 는 글머리 목록 · 「A 값 vs H 값」 줄 2개+ 는 비교표 ·
    맞대결 표는 우리 픽 팀 마감 ML 열 + 7경기+ 는 반씩 두 칸."""
    def inline(s):
        s = esc(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        return re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    out, tbl, vs = [], [], []

    def flush():
        if not tbl:
            return
        rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in tbl]
        rows = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c) for c in r if c)]
        if rows and any("실베팅" in c for c in rows[0]):   # 옛 📊 시즌 표의 「Paul 실베팅」 열은 보드에 안 보인다(10/15 Paul)
            keep = [i for i, c in enumerate(rows[0]) if "실베팅" not in c]
            rows = [[r[i] for i in keep if i < len(r)] for r in rows]
        if rows and teams and rows[0] and rows[0][0].startswith("시즌·주차") and len(teams) > 2 and teams[2]:
            pk = teams[2]   # 맞대결 표 — 마지막 열 = 우리 픽 팀 마감 ML(NBA 94a36ca 「마감 ML(홈)은 헷갈리니 우리 픽 마감 ML 로」)
            rows[0] = rows[0] + [f"{pk} 마감 ML"]
            for r in rows[1:]:
                ms, msc = re.match(r"(\d{4})\s+(\d+)주", r[0] if r else ""), re.match(r"([A-Z]{2,3})\s+\d+\s*[–-]\s*\d+\s+([A-Z]{2,3})", r[3] if len(r) > 3 else "")
                got = _h2h_ml(ms.group(1), ms.group(2), msc.group(1), msc.group(2)) if ms and msc else None
                r.append(_sgn(got[0] if pk == msc.group(1) else got[1]) if got and pk in (msc.group(1), msc.group(2)) else "—")
        if rows:
            body_ = rows[1:]
            numc = {i for i in range(max(len(r) for r in rows))
                    if body_ and sum(1 for r in body_ if i < len(r) and re.fullmatch(r"[+\-−]?[\d.,]+%?", r[i].strip())) * 2 > len(body_)}
            cl = lambda i: ' class="n"' if i in numc else ""
            th = "<thead><tr>" + "".join(f"<th{cl(i)}>{deco(inline(c), hl, only_pick=True)}</th>" for i, c in enumerate(rows[0])) + "</tr></thead>"
            trs = lambda rs: "".join("<tr>" + "".join(f"<td{cl(i)}>{deco(inline(c), hl, only_pick=True)}</td>" for i, c in enumerate(r)) + "</tr>" for r in rs)
            if rows[0][0].startswith("시즌·주차") and len(body_) > 6:
                half = (len(body_) + 1) // 2
                out.append('<div class="h2w">' + "".join(f'<div class="mdt"><table>{th}<tbody>{trs(p_)}</tbody></table></div>' for p_ in (body_[:half], body_[half:])) + "</div>")
            else:
                out.append(f'<div class="mdt"><table>{th}<tbody>{trs(body_)}</tbody></table></div>')
        tbl.clear()

    def flush_vs():
        if len(vs) >= 2 and teams:
            out.append(_vs_table([m for _, m in vs], teams, hl, inline))
        else:
            for ind, m in vs:
                out.append(li(ind, m.string))
        vs.clear()

    def rich(s_):
        head, body = _colon_head(s_)
        parts_ = []
        for seg in _top_split(body, " / "):
            for s2 in (_sentences(seg) if len(seg) > 160 else [seg]):
                items = [x for x in _top_split(s2) if x.strip()]
                m2 = re.match(r"^(.{2,24}?) — ", items[0]) if items else None
                lead = ""
                if m2:
                    lead, items[0] = f'<b class="sh">{deco(inline(m2.group(1)), hl)}</b> — ', items[0][m2.end():]
                if len(items) >= 4:
                    parts_.append(f'<div class="sn">{lead}</div>' if lead else "")
                    parts_.append('<ul class="dl">' + "".join(f"<li>{deco(inline(x.strip()), hl)}</li>" for x in items) + "</ul>")
                else:
                    parts_.append(f'<div class="sn">{lead}{deco(inline(" · ".join(x.strip() for x in items)), hl)}</div>')
        return (f'<b class="lh">{deco(inline(head), hl)}</b>' if head else "") + f'<div class="para">{"".join(parts_)}</div>'

    def li(ind, s_):
        style = f' style="margin-left:{0.4 + ind * 0.35:.2f}em"'
        if len(s_) > 160:
            return f'<div class="li rich"{style}>{rich(s_)}</div>'
        return f'<div class="li"{style}>• {deco(inline(s_), hl)}</div>'
    for ln in txt.splitlines():
        if ln.lstrip().startswith("|"):
            flush_vs(); tbl.append(ln); continue
        flush()
        if not ln.strip():
            continue
        m = re.match(r"^(\s*)[-*]\s+(.*)$", ln)
        mv = _VS.match(m.group(2)) if (m and teams) else None
        if mv and {mv["t1"], mv["t2"]} == set(teams[:2]):
            vs.append((len(m.group(1)), mv)); continue
        flush_vs()
        if re.match(r"^#{1,6}\s", ln):
            out.append(f"<h4>{deco(inline(re.sub(r'^#{1,6}\s+', '', ln)), hl)}</h4>")
        elif ln.strip() == "---":
            out.append("<hr>")
        elif ln.startswith(">"):
            out.append(f'<div class="qt">{deco(inline(ln.lstrip("> ")), hl)}</div>')
        elif m:
            out.append(li(len(m.group(1)), m.group(2)))
        else:   # 문단 — 긴 문단은 문장마다 줄 · 「 · 」 나열 4개+ 는 글머리 목록(NBA 10/24 「읽기 쉽게」)
            parts_ = []
            for s_ in (_sentences(ln) if len(ln) > 160 else [ln]):
                items = [x for x in _top_split(s_) if x.strip()]
                if len(items) >= 4:
                    head, items[0] = _colon_head(items[0])
                    parts_.append((f'<div class="sn">{deco(inline(head), hl)}</div>' if head else "")
                                  + '<ul class="dl">' + "".join(f"<li>{deco(inline(x.strip()), hl)}</li>" for x in items) + "</ul>")
                else:
                    parts_.append(f'<div class="sn">{deco(inline(s_), hl)}</div>')
            out.append(f'<div class="para">{"".join(parts_)}</div>')
    flush_vs()
    flush()
    return "".join(out)


# 펼쳐보기 상자(2026-10-22 Paul 「NFL 보드 깔끔하게」 — NBA 보드 pub_cats 방식): 경기 절의 「- 라벨:」 줄로 묶어
# 결론 → (보완) → 시장 → 팀 상태 → 선수 → 팀 비교 → 심판 → 기타. 모르는 라벨·하위 글머리·표·설명 줄은 앞 상자에 붙는다.
CAT_ORDER = ["결론", "시장", "팀 상태", "선수", "팀 비교", "심판", "기타"]
CAT_OF = {"예측": "결론", "판단": "결론", "정리": "결론", "결론": "결론", "굳이 하나만": "결론", "방향": "결론",
          "시장": "시장", "시장 변동": "시장",
          "새 정보": "팀 상태", "명단": "팀 상태", "변수": "팀 상태",
          "선수 비교": "선수", "선수 표": "선수", "수비 표": "선수", "QB 비교": "선수", "키커": "선수",
          "팀 비교": "팀 비교", "맞대결": "팀 비교", "스탯 비교": "팀 비교", "매치업": "팀 비교", "맥락": "팀 비교",
          "심판": "심판"}
_CAT_LAB = re.compile(r"^-\s+(?:\*\*)?(" + "|".join(map(re.escape, sorted(CAT_OF, key=len, reverse=True))) + r")(?:\*\*)?(?=[\s:：(]|$)")


def pub_cats(body):
    """경기 절 본문 → [(상자, 글)] CAT_ORDER 순. 맨 왼쪽 「- 라벨」 줄에서만 상자가 바뀐다."""
    acc, cur = defaultdict(list), "기타"
    for ln in body.splitlines():
        m = _CAT_LAB.match(ln)
        if m:
            cur = CAT_OF[m.group(1)]
        acc[cur].append(ln)
    return [(c, "\n".join(acc[c]).strip("\n")) for c in CAT_ORDER if "\n".join(acc[c]).strip()]


def _md_inline(s):
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    return re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)


def _tbl_rows(lines):
    rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in lines]
    return [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c) for c in r if c)]


_PT_HEAD = re.compile(r"([A-Z]{2,3})\s+(선수|수비)")
# ── 선수·수비 표(2026-10-24 NBA side_by_side·PT_COLS·_tile·SMALL_GP → 10/25 NFL 이식):
# 두 팀 표를 나란히(원정 왼쪽 · 홈 오른쪽) · 포지션 묶음(QB/RB/WR·TE/K · 패스러시/커버리지)마다 열 머리(영어 약어 · 한국어 뜻은 툴팁·아래 풀이) ·
# 숫자 = 열마다 다른 색 타일(진할수록 큰 값 · 투명도 0.14~0.72) · INT·SK%·수비 Y/TGT·MISS 는 빨강(나쁨) · EPA 는 초록 +/빨강 − ·
# 다이제스트 「※ 얇음」(드롭백 150·캐리 40·타깃 30 미만)은 「표본 적음」 — 회색 기울임, 색칠·척도 계산 제외 · 포지션·경기·상태는 이름 칸 둘째 줄.
STATUS_KR = {"Out": "결장", "IR": "결장(IR)", "Injured Reserve": "결장(IR)", "Doubtful": "결장 유력", "D": "결장 유력",
             "Questionable": "출전 불투명", "Q": "출전 불투명", "Probable": "출전 유력", "Day-To-Day": "당일 결정"}
_GRP_OF = {"QB": "QB", "러셔": "RB", "리시버": "WR", "키커": "K", "패스러시": "PR", "커버리지": "CV", "합계": "TEAM"}
_GRP_LABEL = {"QB": "QB", "RB": "RB", "WR": "WR·TE", "K": "K", "PR": "패스러시", "CV": "커버리지"}
_BL, _GR, _PU, _OR, _TE, _IN, _RD, _GY = (59, 130, 246), (34, 197, 94), (168, 85, 247), (249, 115, 22), (20, 184, 166), (99, 102, 241), (239, 68, 68), (150, 150, 150)
_EPA = ("EPA", "EPA", "플레이당 EPA(기대 득점 기여) — 초록 +, 빨강 −", "pm", _GR)
_DEF = [("PRS", "PRS", "압박 — QB 를 몰아붙인 횟수", "cnt", _BL), ("SK", "SK", "색", "cnt", _PU), ("QBH", "QBH", "QB 히트", "cnt", _IN),
        ("TGT", "TGT", "그 선수 쪽으로 온 패스", "cnt", _GY), ("ALW", "ALW", "허용한 캐치", "cnt", _GY),
        ("Y/TGT", "Y/TGT", "타깃 1번당 내준 야드 — 낮을수록 좋음(빨강 진할수록 많이 내줌)", "badr", _RD),
        ("MISS", "MISS", "놓친 태클/태클 시도 — 낮을수록 좋음", "badr", _RD)]
# (키, 머리, 한국어 뜻, 척도 cnt/pct/rate/pm/bad/badr/txt, 색)
PT_COLS = {
    "QB": [("ATT", "ATT", "패스 시도", "cnt", _BL), ("CMP%", "CMP%", "패스 성공률", "pct", _OR), ("YDS", "YDS", "패스 야드", "cnt", _GR),
           ("TD", "TD", "패스 TD", "cnt", _PU), ("INT", "INT", "인터셉션 — 적을수록 좋음(빨강 진할수록 많음)", "bad", _RD),
           ("Y/A", "Y/A", "패스 1번당 야드", "rate", _TE), ("SK%", "SK%", "색 당한 비율 — 낮을수록 좋음", "badr", _RD), _EPA,
           ("RK", "RK", "리그 순위(EPA/드롭백)", "txt", None), ("'25", "'25", "작년 EPA/드롭백(순위)", "txt", None)],
    "RB": [("CAR", "CAR", "캐리(러시 시도)", "cnt", _BL), ("YDS", "YDS", "러시 야드", "cnt", _GR), ("TD", "TD", "러시 TD", "cnt", _PU),
           ("YPC", "YPC", "캐리 1번당 야드", "rate", _TE), ("SR%", "SR%", "성공 플레이 비율", "pct", _OR), _EPA,
           ("RK", "RK", "리그 순위(YPC)", "txt", None), ("'25", "'25", "작년 YPC(순위)", "txt", None)],
    "WR": [("TGT", "TGT", "타깃 — 패스 대상이 된 횟수", "cnt", _BL), ("REC", "REC", "받은 공", "cnt", _IN), ("YDS", "YDS", "리시브 야드", "cnt", _GR),
           ("TD", "TD", "리시브 TD", "cnt", _PU), ("CT%", "CT%", "캐치율", "pct", _OR), ("Y/TGT", "Y/TGT", "타깃 1번당 야드", "rate", _TE), _EPA,
           ("RK", "RK", "리그 순위(Y/TGT)", "txt", None), ("'25", "'25", "작년 Y/TGT(순위)", "txt", None)],
    "K": [("FG", "FG", "필드골 성공/시도(2024~26)", "txt", None), ("FG%", "FG%", "필드골 성공률", "pct", _OR), ("50+", "50+", "50야드+ 성공/시도", "txt", None)],
    "PR": _DEF, "CV": _DEF}
_SIZE_COLS = [("HT", "HT", "키(cm) — 마우스를 대면 피트-인치", "size", (100, 116, 139)), ("WT", "WT", "몸무게(kg) — 마우스를 대면 파운드", "size", (180, 120, 60))]


def cols_of(g):
    """포지션 묶음의 표 열 — 맨 앞 HT·WT(10/25 NBA 0af7634 키 열 이식 · NFL 은 몸무게도) + 기록 열."""
    return _SIZE_COLS + PT_COLS[g]


_ROS = None


def _size_of(team, name):
    """nflverse roster_weekly 캐시(가장 최근 주) → (키 인치, 몸무게 파운드). 「D.Maye」 꼴은 성 + 이름 앞글자로, 하나뿐일 때만."""
    global _ROS
    if _ROS is None:
        _ROS = defaultdict(dict)
        try:
            for r in N.rd(os.path.join(N.CACHE, f"roster_weekly_{N.SEASON}.csv")):
                t, fn, wk = r.get("team", ""), r.get("full_name", ""), int(P.fnum(r.get("week")) or 0)
                if fn and (fn not in _ROS[t] or wk >= _ROS[t][fn][0]):
                    _ROS[t][fn] = (wk, r)
        except OSError:
            pass
    sfx = r"\s+(?:Jr\.?|Sr\.?|II|III|IV|V)$"
    norm = lambda x: re.sub(r"[^a-z]", "", re.sub(sfx, "", (x or "").strip()).lower())
    roster = [v[1] for v in _ROS.get(team, {}).values()]
    cands = [r for r in roster if norm(r.get("full_name")) == norm(name)]
    if not cands and "." in name and " " not in name.strip():
        pre, last = name.strip().rsplit(".", 1)
        cands = [r for r in roster if norm(r.get("last_name")) == norm(last)
                 and (norm(r.get("first_name")).startswith(norm(pre)) or norm(r.get("football_name")).startswith(norm(pre)))]
    if len(cands) != 1:
        return None, None
    return P.fnum(cands[0].get("height")), P.fnum(cands[0].get("weight"))


def _cm(v):
    return f"{v * 2.54:.0f}"


def _kg(v):
    return f"{v * 0.4536:.0f}"


def _ftin(v):
    return f"{int(v // 12)}-{int(round(v % 12))}"


_THIN = {"QB": ("DB", 150, "드롭백"), "RB": ("CAR", 40, "캐리"), "WR": ("TGT", 30, "타깃")}   # nfl_pull THIN_QB_DB·THIN_RB_CAR·THIN_WR_TGT 와 같은 기준


def _tbl_grid(lines):
    rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in lines]
    return [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c) for c in r if c)]


def _num(s):
    try:
        return float(str(s).replace(",", "").replace("−", "-"))
    except (TypeError, ValueError):
        return None


def parse_prow(hdr, r):
    """발행문 선수·수비 표 한 줄 → {name, ext(예상 선발), role, grp, g, st, v(숫자), d(보이는 글자), small, vol}."""
    c = {h: (r[i] if i < len(r) else "") for i, h in enumerate(hdr)}
    name, ext = r[0], ""
    mx = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", r[0])
    if mx:
        name, ext = mx.group(1), mx.group(2)
    role = c.get("역할", ""); grp = _GRP_OF.get(role, "")
    st = c.get("상태", "").strip(); st = "" if st in ("", "—", "-") else st
    p = dict(name=name.strip(), ext=ext, role=role, grp=grp, st=st, g=_num(re.sub(r"\D", "", c.get("경기", "")) or None), v={}, d={}, raw=c)

    def put(key, pat, s, grp_=1):
        m = re.search(pat, s or "")
        if m:
            p["d"][key] = m.group(grp_); p["v"][key] = _num(m.group(grp_))
    smp, yds, td, eff, epa = (c.get(k, "") for k in ("표본", "야드", "TD", "효율", "EPA/플레이"))
    rk, ly = c.get("리그 순위", ""), c.get("2025(작년·참고)", "")
    if grp in ("QB", "RB", "WR"):
        put("YDS", r"^\s*([\d,]+)", yds); put("EPA", r"([+\-−]?\d*\.\d+)", epa)
        m = re.search(r"(\d+)/(\d+)위", rk)
        p["d"]["RK"] = f"{m.group(1)}/{m.group(2)}" if m else "—"
        lab = {"QB": "EPA/드롭백", "RB": "야드/캐리", "WR": "야드/타깃"}[grp]
        m = re.search(re.escape(lab) + r"\s*([+\-−]?[\d.]+)(?:\((\d+)/\d+위\))?", ly)
        p["d"]["'25"] = (m.group(1) + (f" #{m.group(2)}" if m.group(2) else "")) if m else ("적음" if "표본 적음" in ly else "—")
    if grp == "QB":
        put("DB", r"드롭백\s*(\d+)", smp); put("ATT", r"시도\s*(\d+)", smp); put("TD", r"패스\s*(\d+)", td); put("INT", r"INT\s*(\d+)", td)
        put("CMP%", r"완성\s*([\d.]+)%", eff); put("Y/A", r"야드/시도\s*([\d.]+)", eff); put("SK%", r"색\s*([\d.]+)%", eff)
    elif grp == "RB":
        put("CAR", r"캐리\s*(\d+)", smp); put("TD", r"^\s*(\d+)", td); put("YPC", r"야드/캐리\s*([\d.]+)", eff); put("SR%", r"성공률\s*([\d.]+)%", eff)
    elif grp == "WR":
        put("TGT", r"타깃\s*(\d+)", smp); put("REC", r"캐치\s*(\d+)", smp); put("TD", r"^\s*(\d+)", td)
        put("CT%", r"캐치율\s*([\d.]+)%", eff); put("Y/TGT", r"야드/타깃\s*([\d.]+)", eff)
    elif grp == "K":
        m = re.search(r"FG\s*(\d+/\d+)", smp); p["d"]["FG"] = m.group(1) if m else "—"
        put("FG%", r"FG\s*([\d.]+)%", eff)
        m = re.search(r"50\+\s*(\d+/\d+)", eff); p["d"]["50+"] = m.group(1) if m else "—"
    elif grp in ("PR", "CV"):
        put("PRS", r"^\s*([\d.]+)", c.get("압박", "")); put("SK", r"^\s*([\d.]+)", c.get("색", "")); put("QBH", r"^\s*([\d.]+)", c.get("QB 히트", ""))
        m = re.match(r"\s*(\d+)\s*→\s*(\d+)", c.get("타깃→허용", ""))
        if m:
            p["d"]["TGT"], p["v"]["TGT"], p["d"]["ALW"], p["v"]["ALW"] = m.group(1), _num(m.group(1)), m.group(2), _num(m.group(2))
        put("Y/TGT", r"^\s*(-?[\d.]+)", c.get("야드/타깃", ""))
        m = re.match(r"\s*(\d+)/(\d+)", c.get("놓친 태클", ""))
        if m:
            p["d"]["MISS"] = f"{m.group(1)}/{m.group(2)}"; p["v"]["MISS"] = 100 * int(m.group(1)) / int(m.group(2)) if int(m.group(2)) else None
    th = _THIN.get(grp)
    p["vol"] = (th[2], p["v"].get(th[0])) if th else None
    p["small"] = bool(th and p["v"].get(th[0]) is not None and p["v"][th[0]] < th[1])
    return p


def _tile(rgb, rel):
    """색 타일 — rel 0~1(진하기) · NBA 10/24 「진하게」 투명도 0.14~0.72."""
    a = 0.14 + 0.58 * max(0.0, min(1.0, rel))
    return f' style="background:rgba({rgb[0]},{rgb[1]},{rgb[2]},{a:.2f})"'


# ── 줄임말 풀이(10/25 Paul 「ATT CMP% YDS TD INT Y/A SK% EPA RK '25 이런 것들 밑에 풀어서 알 수 있도록 · 다른 미식축구 전용 줄임말도」)
# 표 열 = 영어 원말 + 쉬운 한국어 · 표 밑에 그 표에 나온 열만 · 포지션·상태·발행문 용어는 맨 위 「미식축구 줄임말 풀이」에 전부.
GLOSS = {"HT": ("Height", "키 — cm(마우스를 대면 피트-인치 · 6-4 = 6피트 4인치 = 193cm)"),
         "WT": ("Weight", "몸무게 — kg(마우스를 대면 파운드)"),
         "ATT": ("Attempts", "패스 시도 — QB 가 공을 던진 횟수"),
         "CMP%": ("Completion %", "패스 성공률 — 던진 공 중 우리 편이 받은 비율"),
         "YDS": ("Yards", "전진 야드 — 공을 몇 야드 앞으로 옮겼나(QB 는 패스, RB 는 달리기, WR·TE 는 받은 공)"),
         "TD": ("Touchdown", "터치다운 — 엔드존에 공을 넣은 횟수(6점)"),
         "INT": ("Interception", "가로채기 당함 — 던진 공을 상대가 잡은 횟수(적을수록 좋음)"),
         "Y/A": ("Yards per Attempt", "패스 1번당 평균 전진 야드"),
         "SK%": ("Sack %", "색 당한 비율 — 던지려다 QB 가 공을 든 채 태클당한 비율(낮을수록 좋음)"),
         "EPA": ("Expected Points Added", "플레이 하나가 우리 팀 기대 득점을 얼마나 바꿨나 — 플레이당 평균, + 면 좋고 − 면 나쁨"),
         "RK": ("Rank", "리그 순위 — 14/35 = 35명 중 14위(QB 는 EPA, RB 는 YPC, WR·TE 는 Y/TGT 기준)"),
         "'25": ("2025 season", "작년(2025) 같은 지표 — #숫자는 그때 순위, 「적음」은 작년 표본이 작음"),
         "CAR": ("Carries", "캐리 — 공을 들고 달린 횟수(러시 시도)"),
         "YPC": ("Yards per Carry", "캐리 1번당 평균 전진 야드"),
         "SR%": ("Success Rate", "성공 플레이 비율 — 그 상황에 필요한 만큼 전진한 플레이의 비율"),
         "TGT": ("Targets", "타깃 — 그 선수에게 던진 패스 수"),
         "REC": ("Receptions", "받은 공 — 실제로 잡은 패스 수"),
         "CT%": ("Catch %", "캐치율 — 타깃 중 잡은 비율"),
         "Y/TGT": ("Yards per Target", "타깃 1번당 평균 전진 야드"),
         "FG": ("Field Goal", "필드골 성공/시도(2024~26 합) — 차서 넣는 3점 킥"),
         "FG%": ("Field Goal %", "필드골 성공률"),
         "50+": ("50+ yards", "50야드 넘는 먼 필드골 성공/시도")}
GLOSS_DEF = {"HT": ("Height", "키 — cm(마우스를 대면 피트-인치)"), "WT": ("Weight", "몸무게 — kg(마우스를 대면 파운드)"),
             "PRS": ("Pressures", "압박 — QB 를 몰아붙여 서둘러 던지게 만든 횟수"),
             "SK": ("Sacks", "색 — QB 가 던지기 전에 태클한 횟수(0.5 = 둘이 같이 잡음)"),
             "QBH": ("QB Hits", "QB 히트 — 던진 직후 QB 를 넘어뜨린 횟수"),
             "TGT": ("Targets", "그 수비수가 막던 선수에게 온 패스 수"),
             "ALW": ("Allowed", "그중 상대가 받은 캐치 수(적을수록 좋음)"),
             "Y/TGT": ("Yards per Target", "그 수비수 쪽 패스 1번당 내준 야드(낮을수록 좋음)"),
             "MISS": ("Missed Tackles", "놓친 태클/태클 시도 — 2/40 = 40번 중 2번 놓침(낮을수록 좋음)")}
POS_GLOSS = [("QB", "Quarterback", "쿼터백 — 공격 지휘, 패스를 던짐"), ("RB", "Running Back", "러닝백 — 공을 들고 달림(FB 풀백 = 앞에서 길을 여는 RB)"),
             ("WR", "Wide Receiver", "와이드리시버 — 패스를 받음"), ("TE", "Tight End", "타이트엔드 — 블로킹도 하고 패스도 받음"),
             ("OL", "Offensive Line", "공격 라인 — QB 를 지키는 5명: OT·T 태클(양 끝) · G 가드 · C 센터(가운데, 공을 QB 에게 넘김)"),
             ("DL", "Defensive Line", "수비 라인 — DT 디펜시브 태클(안쪽) · DE 디펜시브 엔드(바깥) · NT 노즈 태클(정가운데)"),
             ("EDGE", "Edge Rusher", "바깥에서 QB 를 잡으러 들어가는 패스러셔(DE·OLB)"),
             ("LB", "Linebacker", "라인배커 — 라인 뒤에서 달리기·짧은 패스를 막음(OLB 바깥 · ILB·MLB 가운데)"),
             ("CB", "Cornerback", "코너백 — 바깥 리시버를 따라붙어 패스를 막음"), ("S", "Safety", "세이프티 — 맨 뒤에서 긴 패스를 막음(FS·SS)"),
             ("DB", "Defensive Back", "수비 뒷선(CB + S)"), ("K", "Kicker", "키커 — 필드골·추가점"), ("P", "Punter", "펀터 — 공격을 포기할 때 멀리 차는 선수"),
             ("LS", "Long Snapper", "킥 때 공을 뒤로 넘겨 주는 선수")]
STATUS_GLOSS = [("Out", "결장 확정"), ("IR", "Injured Reserve — 부상자 명단(최소 몇 주 결장)"), ("D", "Doubtful — 결장 유력"),
                ("Q", "Questionable — 출전 불투명(반반)"), ("연습 DNP", "Did Not Practice — 그날 연습 불참"), ("Limited", "연습 일부만 함"),
                ("건강 제외", "healthy scratch — 다치지 않았지만 감독 결정으로 명단에서 뺌"),
                ("비활성 명단", "inactives — 킥오프 90분 전 각 팀이 발표하는 그날 안 뛰는 선수 명단(정본)")]
TERM_GLOSS = [("ML", "Moneyline — 점수 차 상관없이 그냥 이길 팀"), ("스프레드", "점수 차 핸디(−3 = 4점 차 이상 이겨야 맞음)"),
              ("드롭백", "dropback — 패스하려고 뒤로 물러선 횟수(시도 + 색 + 스크램블)"),
              ("CPOE", "Completion % Over Expected — 던진 공의 난이도를 감안한 예상보다 성공률이 얼마나 높은가"),
              ("EPA/드롭백", "드롭백 1번당 EPA — QB 실력 지표"), ("3rd down", "공격 세 번째 시도 — 여기서 못 이어 가면 보통 펀트"),
              ("레드존", "상대 20야드 안"), ("턴오버", "INT + 펌블 잃음 — 공을 상대에게 넘김"),
              ("색 허용률", "공격 라인이 QB 색을 허용한 비율"), ("압박률", "수비가 QB 를 압박한 비율"),
              ("득점 드라이브 비율", "공격 한 번(드라이브)이 점수로 끝난 비율"), ("스냅 %", "그 선수가 팀 플레이 중 뛴 비율"),
              ("★", "주전(스냅 상위)"), ("[운]", "운이 많이 섞인 숫자(TD·INT 등) — 다음 경기로 잘 이어지지 않음"),
              ("※ 얇음", "표본 적음 — 드롭백 150·캐리 40·타깃 30 미만")]


def table_gloss(groups, kind):
    """선수·수비 표 바로 밑 — 그 표에 나온 열 머리만 「약어(영어 원말) — 쉬운 뜻」, 열 색 칩 같이."""
    src = GLOSS_DEF if kind == "수비" else GLOSS
    out, seen = [], set()
    if kind == "수비":
        out.append('<div class="gh2">수비 — 패스러시 = QB 를 잡으러 들어가는 선수(DE·DT·EDGE·LB) · 커버리지 = 패스를 막는 선수(CB·S·LB)</div>')
    else:
        out.append('<div class="gh2">포지션 — QB 쿼터백 · RB 러닝백 · WR 와이드리시버 · TE 타이트엔드 · K 키커 · 그 밖의 줄임말은 맨 위 「미식축구 줄임말 풀이」</div>')
    for g in groups:
        for c_ in cols_of(g):
            if c_[1] in seen:
                continue
            seen.add(c_[1])
            en, ko = src.get(c_[0], ("", c_[2]))
            chip = f'<span class="kc" style="background:rgba({c_[4][0]},{c_[4][1]},{c_[4][2]},.65)"></span>' if c_[4] else '<span class="kc"></span>'
            out.append(f'<div>{chip}<b>{esc(c_[1])}</b>{f" <i>{esc(en)}</i>" if en else ""} — {esc(ko)}</div>')
    return '<div class="gl">' + "".join(out) + "</div>"


def gloss_all():
    """맨 위 읽는 법 안 「미식축구 줄임말 풀이」 — 포지션 · 부상 상태 · 표 열 · 발행문 용어 전부."""
    def sec(title, rows):
        return f'<div class="gh2">{esc(title)}</div>' + "".join(rows)
    pos = [f"<div><b>{esc(k)}</b> <i>{esc(en)}</i> — {esc(ko)}</div>" for k, en, ko in POS_GLOSS]
    st = [f"<div><b>{esc(k)}</b> — {esc(ko)}</div>" for k, ko in STATUS_GLOSS]
    off = [f"<div><b>{esc(k)}</b> <i>{esc(en)}</i> — {esc(ko)}</div>" for k, (en, ko) in GLOSS.items()]
    dfn = [f"<div><b>{esc(k)}</b> <i>{esc(en)}</i> — {esc(ko)}</div>" for k, (en, ko) in GLOSS_DEF.items()]
    tm = [f"<div><b>{esc(k)}</b> — {esc(ko)}</div>" for k, ko in TERM_GLOSS]
    return ('<details class="gloss"><summary><b>미식축구 줄임말 풀이</b> — 포지션 · 부상 상태 · 선수 표 열 · 발행문 용어(눌러서 펼치기)</summary><div class="gl">'
            + sec("포지션", pos) + sec("부상·명단 상태", st) + sec("선수 표 열(공격)", off) + sec("수비 표 열", dfn) + sec("발행문 용어", tm) + "</div></details>")


def nfl_side_by_side(kind, grids, A, H, pick):
    """두 팀 표(원정 왼쪽 · 홈 오른쪽) — 포지션 묶음마다 머리 줄, 색 타일, 표본 적음, RB·WR 합계 줄(두 팀 중 큰 값만 진하게)."""
    data = {t: [parse_prow(grids[t][0], r) for r in grids[t][1:]] for t in (A, H)}
    for t in (A, H):
        for p in data[t]:
            p["ht"], p["wt"] = _size_of(t, p["name"]) if p["grp"] in PT_COLS else (None, None)
    groups = []
    for t in (A, H):
        for p in data[t]:
            if p["grp"] in PT_COLS and p["grp"] not in groups:
                groups.append(p["grp"])
    sc = {}
    for t in (A, H):
        for p in data[t]:
            if p["small"] or p["grp"] not in PT_COLS:
                continue
            for key, _, _, scale, _ in PT_COLS[p["grp"]]:
                x = p["v"].get(key)
                if x is None:
                    continue
                k2 = (p["grp"], key)
                if scale in ("cnt", "bad"):
                    sc[k2] = max(sc.get(k2, 0), x)
                elif scale in ("pct", "rate", "badr"):
                    lo, hi = sc.get(k2, (x, x)); sc[k2] = (min(lo, x), max(hi, x))
                elif scale == "pm":
                    sc[k2] = max(sc.get(k2, 0), abs(x))
    sums = {t: defaultdict(float) for t in (A, H)}
    for t in (A, H):
        for p in data[t]:
            if p["grp"] in ("RB", "WR"):
                for key, _, _, scale, _ in PT_COLS[p["grp"]]:
                    if scale == "cnt" and p["v"].get(key) is not None:
                        sums[t][(p["grp"], key)] += p["v"][key]
    ncol = max([len(cols_of(g)) for g in groups] or [1])
    szr = {}   # 체격 색 척도 — 두 팀 같은 포지션 최저~최고(표본 적음 줄도 포함 — 경기 기록이 아니라서)
    for t in (A, H):
        for p in data[t]:
            for key in ("HT", "WT"):
                v = p.get("ht" if key == "HT" else "wt")
                if v and p["grp"] in PT_COLS:
                    lo, hi = szr.get((p["grp"], key), (v, v)); szr[(p["grp"], key)] = (min(lo, v), max(hi, v))
    lab = "선수" if kind == "선수" else "수비"
    tbls = []
    for t in (A, H):
        o = H if t == A else A
        tcls = "tm pk" if t == pick else "tm"
        trs = [f'<tr class="th0"><th colspan="{ncol + 1}"><span class="{tcls}" title="{esc(TEAM_EN.get(t, t))}">{esc(t)}</span> {lab} '
               f'<span class="muted">{"(원정)" if t == A else "(홈)"}</span></th></tr>']
        for g in groups:
            cols = cols_of(g)
            trs.append(f'<tr class="gh"><th class="pnm">{esc(_GRP_LABEL[g])}</th>' + "".join(f'<th title="{esc(c_[2])}">{esc(c_[1])}</th>' for c_ in cols)
                       + "<th></th>" * (ncol - len(cols)) + "</tr>")
            rows_g = [p for p in data[t] if p["grp"] == g]
            if not rows_g:
                trs.append(f'<tr><td class="pnm"><span class="psub">표에 없음</span></td>' + "<td></td>" * ncol + "</tr>")
                continue
            for p in rows_g:
                sub = " · ".join(x for x in (f'{p["g"]:g}경기' if p["g"] else "", p["ext"]) if x)
                badge = f'<span class="stt">{esc(STATUS_KR.get(p["st"], p["st"]))}</span>' if p["st"] else ""
                smb = (f'<span class="smp" title="{esc(p["vol"][0])} {p["vol"][1]:g} — 표본이 적어 숫자가 크게 부풀거나 작게 나올 수 있다(색칠·비교에서 뺐다)">표본 적음</span>'
                       if p["small"] else "")
                cells = [f'<td class="pnm"><span class="pnn" title="{esc(p["name"])}">{esc(p["name"])}</span>'
                         + (f'<span class="psub">{esc(sub)}</span>' if sub else "") + smb + badge + "</td>"]
                for key, _, _, scale, rgb in cols:
                    if scale == "size":
                        v = p.get("ht" if key == "HT" else "wt")
                        if not v:
                            cells.append('<td class="tx">—</td>'); continue
                        lo, hi = szr.get((g, key), (v, v))
                        cells.append(f'<td class="n" title="{_ftin(v) if key == "HT" else f"{v:g} lb"}"{_tile(rgb, 1.0 if hi <= lo else (v - lo) / (hi - lo))}>'
                                     f'{_cm(v) if key == "HT" else _kg(v)}</td>'); continue
                    disp, x = p["d"].get(key, "—"), p["v"].get(key)
                    if scale == "txt":
                        cells.append(f'<td class="tx">{esc(disp)}</td>'); continue
                    if p["small"]:
                        cells.append(f'<td class="n sm">{esc(disp)}</td>'); continue
                    sty, k2 = "", (g, key)
                    if x is not None and k2 in sc:
                        if scale in ("cnt", "bad") and sc[k2]:
                            sty = _tile(rgb, x / sc[k2])
                        elif scale in ("pct", "rate", "badr"):
                            lo, hi = sc[k2]; sty = _tile(rgb, 1.0 if hi <= lo else (x - lo) / (hi - lo))
                        elif scale == "pm" and sc[k2]:
                            sty = _tile(_GR if x >= 0 else _RD, abs(x) / sc[k2])
                    cells.append(f'<td class="n"{sty}>{esc(disp)}</td>')
                cells += ["<td></td>"] * (ncol - len(cols))
                trs.append(f'<tr{" class=out" if p["st"] in ("Out", "IR") else ""}>' + "".join(cells) + "</tr>")
            if g in ("RB", "WR") and len(rows_g) > 1:
                cells = ['<td class="pnm"><span class="pnn">합계</span><span class="psub">표의 선수</span></td>']
                for key, _, _, scale, rgb in cols:
                    if scale == "size":   # 체격은 평균(좋고 나쁨이 아니라 색·굵게 없음)
                        xs = [p.get("ht" if key == "HT" else "wt") for p in rows_g]
                        xs = [x for x in xs if x]
                        cells.append(f'<td class="tx" title="평균">{(_cm if key == "HT" else _kg)(sum(xs) / len(xs))}</td>' if xs else "<td></td>"); continue
                    v, w = sums[t].get((g, key)), sums[o].get((g, key))
                    if scale != "cnt" or not v:
                        cells.append("<td></td>"); continue
                    win = w is not None and v > w
                    cells.append(f'<td class="n{" hi" if win else ""}"{_tile(rgb, 0.75) if win else ""}>{v:g}</td>')
                cells += ["<td></td>"] * (ncol - len(cols))
                trs.append('<tr class="sum">' + "".join(cells) + "</tr>")
        tbls.append(f'<div><table class="ptab"><colgroup><col class="cn">{"<col>" * ncol}</colgroup>{"".join(trs)}</table></div>')
    small = {t: [f'{p["name"]}({p["vol"][0]} {p["vol"][1]:g})' for p in data[t] if p["small"]] for t in (A, H)}
    note = ""
    if any(small.values()):
        note = ('<p class="smnote"><b>표본 주의</b> — 드롭백 150·캐리 40·타깃 30 미만(다이제스트 「※ 얇음」 기준)은 몇 경기 숫자라 크게 부풀거나 작게 나온다. '
                "회색 기울임으로 두고 색칠·비교에서 뺐다: " + " / ".join(f"{esc(t)}: {esc(', '.join(small[t]) or '없음')}" for t in (A, H)) + "</p>")
    bits = []
    for g in [g_ for g_ in groups if g_ != "K"]:   # 키커 체격은 뺌
        av = {}
        for t in (A, H):
            hs = [p["ht"] for p in data[t] if p["grp"] == g and p.get("ht")]
            ws = [p["wt"] for p in data[t] if p["grp"] == g and p.get("wt")]
            if hs and ws:
                av[t] = (sum(hs) / len(hs), sum(ws) / len(ws))
        if len(av) == 2:
            d_ = (av[A][0] - av[H][0]) * 2.54
            bits.append(f"{_GRP_LABEL[g]} 평균 {A} {_cm(av[A][0])}cm·{_kg(av[A][1])}kg vs {H} {_cm(av[H][0])}cm·{_kg(av[H][1])}kg(키 차 {abs(d_):.0f}cm)")
    allp = [(p, t) for t in (A, H) for p in data[t] if p.get("ht")]
    if allp:
        tp, tt = max(allp, key=lambda x: (x[0]["ht"], x[0].get("wt") or 0))
        bits.append(f'가장 큰 선수 {tp["name"]}({tt}) {_cm(tp["ht"])}cm({_ftin(tp["ht"])})')
    if bits:
        note += ('<p class="sznote"><b>키·몸무게 비교</b>(값만 — 확률 재료 아님) — ' + esc(" · ".join(bits)) + "</p>")
    teamrow = []
    for t in (A, H):
        tr_ = next((p for p in data[t] if p["grp"] == "TEAM"), None)
        if tr_:
            bits = [tr_["raw"].get(k, "") for k in ("압박", "색", "놓친 태클")]
            teamrow.append(f'{esc(t)} 팀 — ' + " · ".join(esc(b) for b in bits if b and b not in ("—", "-")))
    cap = (table_gloss(groups, kind) + '<div class="ptcap">색이 진할수록 큰 값(횟수는 두 팀 같은 포지션 최댓값 대비, 비율은 두 팀 최저~최고 사이) · '
           "INT·SK%·수비 Y/TGT·MISS 는 빨강이 진할수록 나쁨 · EPA 는 초록 = +, 빨강 = − · 흐린 줄 = 결장 · 「합계」 줄은 두 팀 중 큰 값만 색칠·진하게"
           + ("<br>" + "<br>".join(teamrow) if teamrow else "") + "</div>")
    return note + '<div class="pt2">' + "".join(tbls) + "</div>" + cap


def game_player_rows(texts, A, H):
    """발행문 글들 → [(팀, [parse_prow …])] — 선수 첫 등장 꼬리표용."""
    out = []
    for txt in texts:
        cur = []
        for ln in (txt + "\n").splitlines():
            if ln.lstrip().startswith("|"):
                cur.append(ln); continue
            if cur:
                rows = _tbl_grid(cur); cur = []
                m = _PT_HEAD.fullmatch(rows[0][0]) if rows and rows[0] else None
                if m and m.group(1) in (A, H):
                    out.append((m.group(1), [parse_prow(rows[0], r) for r in rows[1:]]))
    return out


def players_html(txt, A, H, pick="", hl=None):
    """선수 상자 글 → HTML. 「| A 선수 |」·「| H 선수 |」(수비도) 한 쌍이면 nfl_side_by_side · 나머지 글은 md_html(강조·비교표)."""
    blocks = []
    for ln in txt.splitlines():
        k = "tbl" if ln.lstrip().startswith("|") else "txt"
        if blocks and blocks[-1][0] == k:
            blocks[-1][1].append(ln)
        else:
            blocks.append((k, [ln]))
    pairs = defaultdict(dict)
    for k, ls in blocks:
        if k == "tbl":
            rows = _tbl_grid(ls)
            m = _PT_HEAD.fullmatch(rows[0][0]) if rows and rows[0] else None
            if m and m.group(1) in (A, H):
                pairs[m.group(2)][m.group(1)] = rows
    out, done = [], set()
    for k, ls in blocks:
        if k == "txt":
            rest = []
            for ln in ls:
                mm = re.match(r"^\s*-\s+(선수 표|수비 표)\s*[:：]\s*$", ln)
                if mm:
                    if rest:
                        out.append(md_html("\n".join(rest), hl, (A, H, pick))); rest = []
                    out.append(f'<div class="pth">{mm.group(1)} — 왼쪽 원정 {esc(A)} · 오른쪽 홈 {esc(H)}</div>')
                else:
                    rest.append(ln)
            if rest:
                out.append(md_html("\n".join(rest), hl, (A, H, pick)))
            continue
        rows = _tbl_grid(ls)
        m = _PT_HEAD.fullmatch(rows[0][0]) if rows and rows[0] else None
        if m and A in pairs[m.group(2)] and H in pairs[m.group(2)]:
            if m.group(2) not in done:
                done.add(m.group(2))
                out.append(nfl_side_by_side(m.group(2), pairs[m.group(2)], A, H, pick))
        else:
            out.append(md_html("\n".join(ls), hl, (A, H, pick)))
    return "".join(out)


# ── 선수 첫 등장 꼬리표(NBA 1e24cc9 pos_maps·_ins_pos·annotate_pos 이식 — Paul 「아웃 확정인데 어느 팀이고 주전인지 알려줘야지」)
_POS_ROLE = {"QB": "QB", "러셔": "RB", "리시버": "WR·TE", "키커": "K", "패스러시": "패스러시", "커버리지": "커버리지"}
_POSP = r"\((?:QB|RB|FB|WR|TE|OT|OG|OL|T|G|C|DT|DE|DL|NT|EDGE|OLB|ILB|MLB|LB|CB|S|FS|SS|DB|K|P|LS)\b"


def _snap_role(star, snap):
    """비활성 명단 행 → 역할: ★(스냅 상위) 주전 · 스냅 60%+ 주력 · 25%+ 로테이션 · 그 밑 벤치."""
    if str(star) == "1":
        return "주전"
    s = P.fnum(snap)
    return "" if s is None else "주력" if s >= 60 else "로테이션" if s >= 25 else "벤치"


def pos_maps(tbl_rows, inact, A, H):
    """(전체 이름 → 꼬리표, 성 → (이름, 꼬리표)) — 꼬리표 = 「팀 · 포지션 · 역할 · 상태」. 성은 이 경기 두 팀 안에서 하나뿐일 때만."""
    full = {}
    for r in inact:
        t = r.get("team", "")
        if t not in (A, H) or not r.get("player"):
            continue
        full[r["player"]] = " · ".join(x for x in (t, r.get("pos", ""), _snap_role(r.get("star"), r.get("snap_pct")),
                                                   STATUS_KR.get(r.get("status", ""), r.get("status", ""))) if x)
    for t, rows in tbl_rows:
        for p in rows:
            if p["grp"] in ("", "TEAM") or not p["name"]:
                continue
            full.setdefault(p["name"], " · ".join(x for x in (t, _POS_ROLE.get(p["role"], ""), "주전" if "예상 선발" in p["ext"] else "",
                                                               STATUS_KR.get(p["st"], p["st"])) if x))
    seen = defaultdict(set)
    for nm, tg in full.items():
        last = re.sub(r"\s+(Jr\.|Sr\.|II|III|IV|V)$", "", nm).replace(".", ". ").split()[-1]
        if len(last) >= 4 and last != nm:
            seen[last].add((nm, tg))
    return full, {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}


def _ins_pos(line, i, tag):
    """이름 바로 뒤에 (꼬리표) — 이미 「(G · 햄스트링)」처럼 포지션 괄호가 있으면 앞에 팀만, 다른 괄호면 앞머리에 「꼬리표 · 」."""
    if line[i:i + 1] == "(":
        if re.match(_POSP, line[i:]):
            team = tag.split(" · ")[0]
            return line[:i + 1] + (f"{team} · " if re.fullmatch(r"[A-Z]{2,3}", team) else "") + line[i + 1:]
        return line[:i + 1] + f"{tag} · " + line[i + 1:]
    return line[:i] + f"({tag})" + line[i:]


def annotate_pos(txt, full, short):
    """본문 줄에서 선수 첫 등장에 (팀 · 포지션 · 역할 · 상태). 표·출처·링크 줄은 손대지 않는다. 이미 「(팀 ·」 꼬리표가 붙은 이름은 건너뛴다."""
    if not full:
        return txt
    done, out = set(), []
    names = sorted(full, key=len, reverse=True)
    skip = r"(?!\s*\([A-Z]{2,3} · )"
    for line in (txt or "").splitlines():
        if line.lstrip().startswith("|") or "](http" in line or line.lstrip().startswith(("출처", "Sources", "- [")):
            out.append(line); continue
        for nm in names:
            if nm in done or nm not in line:
                continue
            m = re.search(r"(?<![A-Za-z.])" + re.escape(nm) + r"(?![A-Za-z])" + skip, line)
            if m:
                line = _ins_pos(line, m.end(), full[nm])
            if re.search(r"(?<![A-Za-z.])" + re.escape(nm) + r"(?![A-Za-z])", line):
                done.add(nm)
        for k_, (nm, tg) in short.items():
            if nm in done:
                continue
            first = re.split(r"[.\s]", nm)[0]
            for m in re.finditer(r"(?<![A-Za-z.])" + re.escape(k_) + r"(?![A-Za-z])" + skip, line):
                pv = re.search(r"([A-Z][A-Za-z'\-]*)\.?\s*$", line[:m.start()])
                if pv and not re.fullmatch(r"[A-Z]{2,3}", pv.group(1)) and pv.group(1) != first and not (len(pv.group(1)) == 1 and first.startswith(pv.group(1))):
                    continue   # 「Tyree Wilson」 — 다른 이름이 바로 앞에 있으면 같은 성의 다른 선수(10/25 PIT Payton Wilson 오귀속)
                line = _ins_pos(line, m.end(), tg)
                done.add(nm)
                break
        out.append(line)
    return "\n".join(out)


def ref_table(wd, gk):
    """다이제스트(최신 DIGEST.md) 경기 절의 「🧑‍⚖️ 심판 크루」 줄 → 작은 표(NBA c93545a ref_table 이식). 미배정이면 ''."""
    try:
        txt = open(os.path.join(wd, "DIGEST.md"), encoding="utf-8").read()
    except OSError:
        return ""
    m = re.search(r"(?ms)^## " + re.escape(gk) + r"\s.*?(?=^## |\Z)", txt)
    ln = next((x for x in (m.group(0) if m else "").splitlines() if "심판 크루" in x), "")
    mm = re.search(r"2024~26 (\d+)경기\): (.+?) · 경기당 페널티 ([\d.]+)개 (\d+)야드\(리그 평균 ([\d.]+)개\) · 평균 총점 ([\d.]+)\(리그 ([\d.]+)\) · "
                   r"홈 승 (\d+)% · 홈 커버 (\d+)%\(n(\d+)\) · Over (\d+)%\(n(\d+)\)", ln)
    sub = '<p class="sub">nflverse 배정 · 2024~26 집계 · 심판별 차이는 표본이 작아 우연 범위 — 확률 근거 아님, 서술 전용</p>'
    if mm:
        g, ref, pen, pyd, lpen, tot, ltot, hw, hc, hcn, ov, ovn = mm.groups()
        return ('<div class="mdt reft"><table><thead><tr><th>심판(배정)</th><th class="n">경기 수</th><th class="n">경기당 페널티(리그)</th>'
                '<th class="n">평균 총점(리그)</th><th class="n">홈 승</th><th class="n">홈 커버</th><th class="n">Over</th></tr></thead><tbody>'
                f'<tr><td>{esc(ref)}</td><td class="n">{g}</td><td class="n">{pen}개 · {pyd}야드 ({lpen})</td><td class="n">{tot} ({ltot})</td>'
                f'<td class="n">{hw}%</td><td class="n">{hc}% (n{hcn})</td><td class="n">{ov}% (n{ovn})</td></tr></tbody></table></div>' + sub)
    m2 = re.search(r"심판 크루: (.+?) — 2024~26 기록 없음", ln)
    return (f'<div class="mdt reft"><table><thead><tr><th>심판(배정)</th><th>기록</th></tr></thead><tbody><tr><td>{esc(m2.group(1))}</td>'
            f'<td>2024~26 기록 없음(신임)</td></tr></tbody></table></div>' + sub) if m2 else ""


def verdict_word(v):
    """발행 판단 → 카드 결론 낱말."""
    if not v:
        return ""
    if v.startswith("패스"):
        return "후보 아님"
    return "소액 관심" if v.startswith("소액") else "관심" if v.startswith("관심") else v


BOARD_DIR = os.path.join(os.path.dirname(HERE), "board")
# ESPN 경기 중 상태 — 하프타임·쿼터 사이·연장·지연도 「진행 중」(10/18 HOU@JAX 하프타임이 「예정」으로 보이던 것)
IN_GAME = {"STATUS_IN_PROGRESS", "STATUS_HALFTIME", "STATUS_END_PERIOD", "STATUS_END_OF_REGULATION", "STATUS_OVERTIME", "STATUS_DELAYED", "STATUS_RAIN_DELAY"}
HUB_URL_FILE = os.path.join(BOARD_DIR, "hub_url.txt")


def records_before(week, split=False):
    """{팀: 「W-L(-T)」} — 그 주 경기 전까지의 전적(nflverse 캐시 일정·점수). 지난 주 보드의 games.csv 전적은 채점 때
    다시 받아 「그 경기 뒤」 값이라(3주 ATL 1-2 @ GB 1-2) 보드 전적은 이 값으로 통일한다(2026-10-12 주차별 보드).
    split=True 면 {팀: (홈 전적, 원정 전적)} — ESPN 「3-2, 1-1 Away」처럼(2026-10-15 Paul 「홈게임 어웨이게임 성적」) · 중립 구장 경기도 지정 홈/원정으로 센다(ESPN 과 같음)."""
    wlt = defaultdict(lambda: [0, 0, 0])
    for g in N.rd(os.path.join(N.CACHE, "games.csv")):
        if g.get("season") != str(N.SEASON) or g.get("game_type") != "REG" or int(g["week"]) >= week:
            continue
        fa, fh = N.fnum(g.get("away_score")), N.fnum(g.get("home_score"))
        if fa is None or fh is None:
            continue
        A, H = g["away_team"], g["home_team"]
        if split:   # 중립 구장(런던 등)도 지정 홈/원정으로 센다 — ESPN 표기와 같게(JAX 홈 3-0)
            A, H = (A, "road"), (H, "home")
        if fa == fh:
            wlt[A][2] += 1; wlt[H][2] += 1
        else:
            wlt[A if fa > fh else H][0] += 1; wlt[H if fa > fh else A][1] += 1
    fmt = lambda v: f"{v[0]}-{v[1]}" + (f"-{v[2]}" if v[2] else "")
    if split:
        teams = {t for t, _ in wlt}
        return {t: (fmt(wlt[(t, "home")]), fmt(wlt[(t, "road")])) for t in teams}
    return {t: fmt(v) for t, v in wlt.items()} if week > 1 or wlt else {}


def games_fallback(week):
    """games.csv 가 없는 주(1·2주 — 다이제스트 수집 전, 예측만 소급)는 nflverse 캐시 일정 + closing.csv(DK 마감)로
    보드 행을 만든다(2026-10-12 Paul 「MLB 날짜별처럼 주차별로」). 전적은 그 주에 들어올 때까지의 기록.
    시각은 9월(EDT, UTC−4 · PT = ET−3) 고정 — 이 경로는 1·2주(9월)만 쓴다."""
    cg = [g for g in N.rd(os.path.join(N.CACHE, "games.csv")) if g.get("season") == str(N.SEASON) and g.get("game_type") == "REG"]
    close = {r["game"]: r for r in N.rd(os.path.join(N.week_dir(week), "closing.csv"))}
    pre = records_before(week)
    rec = lambda t: pre.get(t, "0-0")
    out = []
    for g in sorted((g for g in cg if g["week"] == str(week)), key=lambda g: (g["gameday"], g["gametime"])):
        A, H = g["away_team"], g["home_team"]; c = close.get(f"{A}@{H}", {})
        et = datetime.strptime(f'{g["gameday"]} {g["gametime"]}', "%Y-%m-%d %H:%M")
        u = et + timedelta(hours=4); pt = et - timedelta(hours=3)
        fin = N.fnum(g.get("away_score")) is not None and N.fnum(g.get("home_score")) is not None
        out.append(dict(espn_id=c.get("espn_id", ""), game_id=g["game_id"], kickoff_utc=u.strftime("%Y-%m-%dT%H:%MZ"),
                        kickoff_et=et.strftime("%a %m-%d %H:%M"), kickoff_pt=pt.strftime("%H:%M"), away=A, home=H,
                        away_rec=rec(A), home_rec=rec(H), neutral="1" if g.get("location") == "Neutral" else "", div_game=g.get("div_game", ""),
                        status="STATUS_FINAL" if fin else "STATUS_SCHEDULED", away_score=g.get("away_score", ""), home_score=g.get("home_score", ""),
                        spread_home=c.get("spread_home", ""), total=c.get("total", ""), ml_away=c.get("ml_away", ""), ml_home=c.get("ml_home", ""),
                        sp_home_odds=c.get("sp_home_odds", ""), sp_away_odds=c.get("sp_away_odds", ""),
                        over_odds=c.get("over_odds", ""), under_odds=c.get("under_odds", "")))
    return out


def week_links():
    """[(주, URL)] — board/links.csv 레지스트리(주차별 보드 아티팩트, 새 주를 발행하면 한 줄 추가)."""
    try:
        return sorted((int(r["week"]), r["url"]) for r in N.rd(os.path.join(BOARD_DIR, "links.csv")) if r.get("week") and r.get("url"))
    except (OSError, ValueError):
        return []


def hub_url():
    try:
        return open(HUB_URL_FILE, encoding="utf-8").read().strip()
    except OSError:
        return ""


def week_nav(cur):
    """보드 머리 아래 주차별 보드 바로가기 줄(10/25 NBA 2b8031e dnav 이식) — links.csv 전부 · 현재 굵게 · 새 탭 · 끝에 허브."""
    links = dict(week_links()); links.setdefault(cur, "")
    parts = [f'<b class="cur">{w}주</b>' if w == cur else f'<a href="{esc(u)}" target="_blank" rel="noopener">{w}주</a>'
             for w, u in sorted(links.items()) if w == cur or u]
    hu = hub_url()
    return ('<nav class="dnav"><span class="muted">주차별 보드</span> ' + "".join(parts)
            + (f'<a class="hub" href="{esc(hu)}" target="_blank" rel="noopener">전체 주차 →</a>' if hu else "") + "</nav>")


def prev_week_link(cur):
    """맨 밑 「이전 보드」 — 바로 앞 주차 보드(없으면 '')."""
    u = dict(week_links()).get(cur - 1)
    return f'<p><a class="prevb" href="{esc(u)}" target="_blank" rel="noopener">← 이전 보드 · {cur - 1}주차</a></p>' if u else ""

def hub_html(live=None):
    """주차 허브 — 모든 주 보드의 「전체 주차 →」가 이 고정 URL 을 가리킨다. 새 주 보드가 생길 때 이 페이지만 다시 발행."""
    links = week_links()
    if not links:
        return "<meta charset=\"utf-8\"><title>NFL 주간 보드</title><p>등록된 보드 없음</p>"
    cg = [g for g in N.rd(os.path.join(N.CACHE, "games.csv")) if g.get("season") == str(N.SEASON) and g.get("game_type") == "REG"]
    days = defaultdict(set)
    for g in cg:
        days[int(g["week"])].add(g["gameday"])

    def span(w):   # 「9/10~9/14」 — 그 주 첫 경기일~마지막 경기일
        ds = sorted(days.get(w, ()))
        f = lambda d: f"{int(d[5:7])}/{int(d[8:10])}"
        return f"{f(ds[0])}~{f(ds[-1])}" if ds else ""
    rows = PR.all_rows()

    def wl(w):
        s = PR.summary([r for r in rows if r["week"] == str(w)])
        m, b = s.get("시장", {}), s.get("발행", {})
        if live and w in live and sum(live[w]) > m.get("w", 0) + m.get("l", 0):   # 채점 전 이번 주 = 실시간 승패(10/18)
            m = dict(m, w=live[w][0], l=live[w][1])
        if not m.get("w", 0) + m.get("l", 0):
            return '<span class="r none">결과 전</span>'
        t = f'<span class="r">{m["w"]}-{m["l"]}</span>'
        if b.get("w", 0) + b.get("l", 0):
            t += f'<span class="r2">발행 {b["w"]}-{b["l"]}</span>'
        return t
    w0, u0 = links[-1]
    items = "".join(f'<li><a href="{esc(u)}"><span class="d">{w}주차</span><span class="sp">{esc(span(w))}</span>{wl(w)}'
                    f'<span class="go">열기 →</span></a></li>' for w, u in reversed(links))
    return f"""<meta charset="utf-8"><title>NFL 주간 보드</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Saira+Extra+Condensed:wght@600;800&family=Noto+Sans+KR:wght@400;500;700&family=IBM+Plex+Mono:wght@500;600&display=swap">
<style>
:root {{ --bg:#eef2ec; --sur:#ffffff; --ink:#14231b; --ink2:#5d6b62; --line:#d4ddd3; --acc:#e8590c; --accT:#fbe9df; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg:#0f1712; --sur:#16211a; --ink:#e6efe7; --ink2:#97a69b; --line:#26352b; --acc:#ff7a2e; --accT:#2a1d14; color-scheme:dark; }} }}
:root[data-theme="dark"] {{ --bg:#0f1712; --sur:#16211a; --ink:#e6efe7; --ink2:#97a69b; --line:#26352b; --acc:#ff7a2e; --accT:#2a1d14; color-scheme:dark; }}
* {{ box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--ink); margin:0; font-family:"Noto Sans KR","Apple SD Gothic Neo","Malgun Gothic",sans-serif; line-height:1.55; }}
.wrap {{ max-width:640px; margin:0 auto; padding:28px 16px 60px; font-variant-numeric:tabular-nums; }}
h1 {{ font-family:"Saira Extra Condensed","Arial Narrow",sans-serif; font-weight:800; font-size:2.2rem; margin:0; letter-spacing:.02em; line-height:1; }}
.meta {{ color:var(--ink2); font-size:.86rem; margin:8px 0 18px; }}
a.latest {{ display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; text-decoration:none; color:var(--ink);
  background:var(--sur); border:1px solid var(--line); border-left:5px solid var(--acc); padding:16px 18px; }}
a.latest small {{ color:var(--acc); font-weight:700; letter-spacing:.08em; font-size:.74rem; }}
a.latest b {{ font-family:"Saira Extra Condensed","Arial Narrow",sans-serif; font-size:1.6rem; }}
a.latest .go {{ margin-left:auto; color:var(--acc); font-weight:700; }}
a.latest:hover, a.latest:focus-visible {{ border-color:var(--acc); outline:none; }}
h2 {{ font-size:.8rem; margin:30px 0 10px; color:var(--acc); letter-spacing:.12em; }}
h2 small {{ color:var(--ink2); font-weight:400; letter-spacing:0; margin-left:6px; }}
ol.list {{ list-style:none; margin:0; padding:0; border:1px solid var(--line); background:var(--sur); }}
ol.list li + li {{ border-top:1px solid var(--line); }}
ol.list a {{ display:flex; gap:12px; align-items:center; flex-wrap:wrap; padding:10px 14px; color:var(--ink); text-decoration:none; }}
ol.list a:hover, ol.list a:focus-visible {{ background:var(--accT); outline:none; }}
.d {{ font-weight:700; min-width:58px; }}
.sp {{ color:var(--ink2); font-size:.84rem; min-width:84px; font-family:"IBM Plex Mono",monospace; }}
.r {{ font-family:"IBM Plex Mono",monospace; font-weight:600; }}
.r2 {{ color:var(--ink2); font-size:.82rem; }}
.r.none {{ color:var(--ink2); font-weight:400; font-family:inherit; font-size:.84rem; }}
ol.list .go {{ margin-left:auto; color:var(--acc); font-size:.84rem; }}
</style>
<div class="wrap">
<h1>🏈 NFL 주간 보드</h1>
<p class="meta">주차별 보드는 그 주 결과가 찍힌 채로 남아요. 새 주차 보드가 생기면 맨 위 링크가 바뀝니다. 숫자 = 승자 예측(시장 ML 승자) 맞힘-틀림.</p>
<a class="latest" href="{esc(u0)}"><small>최신 주차</small><b>{w0}주차</b><span class="go">열기 →</span></a>
<h2>전체 주차<small>주차 · 날짜 · 승자 예측 맞힘-틀림</small></h2>
<ol class="list">{items}</ol>
</div>"""


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--week", type=int, required=True); ap.add_argument("--out")
    ap.add_argument("--hub-out", default=os.path.join(BOARD_DIR, "hub.html"))
    a = ap.parse_args()
    wd = N.week_dir(a.week)
    games = N.rd(os.path.join(wd, "games.csv")) if os.path.exists(os.path.join(wd, "games.csv")) else games_fallback(a.week)
    pre = records_before(a.week)   # 보드 전적 = 그 주 경기 전(1주는 0-0)
    hr = records_before(a.week, split=True)   # 원정팀은 원정 성적, 홈팀은 홈 성적을 덧붙인다(ESPN 「3-2, 1-1 Away」)
    for g in games:
        g["away_rec"] = pre.get(g["away"], "0-0" if a.week == 1 else g.get("away_rec", ""))
        g["home_rec"] = pre.get(g["home"], "0-0" if a.week == 1 else g.get("home_rec", ""))
        for sd in ("away", "home"):   # 카드용 — 두 팀 모두 홈·원정 성적 둘 다(10/18 Paul), 표엔 전체 성적만
            h_, r_ = hr.get(g[sd], ("0-0", "0-0"))
            g[f"{sd}_rec_full"] = g[f"{sd}_rec"] + (f" · 홈 {h_} · 원정 {r_}" if a.week > 1 else "")
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
    inact = N.rd(os.path.join(wd, "inactives.csv")) if os.path.exists(os.path.join(wd, "inactives.csv")) else []   # 선수 꼬리표(10/25)
    # 경기별 발행문·보완 전문 — 카드·표 줄을 누르면 펼쳐지는 곳(MLB 보드 발행문 카드 방식, 2026-10-11 Paul 「카드 누르면 설명」)
    ptext = defaultdict(lambda: {"main": [], "supp": []}); pcommon = []
    for p in pub_files(wd):
        lab = pub_label(p); supp = "보완" in os.path.basename(p)
        chunks, common = split_pub(open(p, encoding="utf-8").read())
        for gk_, lst in chunks.items():
            for h_, b_ in lst:
                # 예측·시장·선수 줄이 다 있는 보완 = 새 판 전체 재발행 → 최신 발행으로(앞 판은 「이전 판」 · 10/22 중복 없이 · 10/18 「발행문은 최근 걸로」)
                # 명단 보완(예측·판단·명단·정리만)은 그대로 보완 상자
                full = all(re.search(rf"(?m)^- {k}", b_) for k in ("예측:", "시장:", "선수 (?:비교|표):"))
                ptext[gk_]["supp" if supp and not full else "main"].append((lab, h_, b_))
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
        """예측·방향·관찰 결과 — 테두리만. 실베팅은 보드에 표시하지 않는다(2026-10-15 Paul 「의미 없음 · 추천만」)."""
        return {"W": '<span class="hit w">맞힘</span>', "L": '<span class="hit l">틀림</span>', "P": '<span class="hit p">무승부</span>'}.get(res, "")

    mini_used = set()

    def team(t, name, rec="", pk=False, home=False):
        """카드 팀 한 줄 — 원정/홈 표지 · 로고 · 이름 · 전적(전체 · 홈 · 원정). 10/18 Paul 「카드 너무 정신없다」 → 두 팀을 위아래 두 줄로."""
        mini_used.add(t)
        return (f'<div class="trow" title="{esc(name or t)} ({esc(t)})">{ha(home)}<span class="tlogo lg-{esc(t)}" role="img" aria-label="{esc(t)}"></span>'
                f'<span class="tinfo"><span class="tname">{esc(name_kr(t))}</span><span class="trec">{esc(rec)}</span></span></div>')

    def ha(home):
        """「원정」/「홈」 표지 — 이 경기에서 누가 홈인지(10/18 Paul 「확실히 나타나게」)."""
        return '<span class="ha h">홈</span>' if home else '<span class="ha">원정</span>'

    def mini(t):
        """작은 로고 — 표·펼침 머리에 경기마다 반복돼서(10/11 514KB) 팀별 CSS 배경으로 한 번만 싣는다."""
        mini_used.add(t)
        return f'<span class="mini lg-{esc(t)}" role="img" aria-label="{esc(t)}"></span>'

    pre_cards, done_rows, trows, pick_of, star_of = [], [], [], {}, {}
    live_wl = [0, 0]   # 이번 주 끝난 경기 시장 예측 승패(실시간 — 화요일 채점 전에도 반영, 10/18 Paul)
    remaining = 0
    for g in games:
        A, H = g["away"], g["home"]; gk = f"{A}@{H}"
        lv = live.get(gk, {})
        st = lv.get("state", g.get("status", ""))
        fin = st == "STATUS_FINAL"
        rows = by.get(gk, [])
        # 10판 ML 전용(2026-10-16 Paul): 방향(스프레드/총점)·바람·A1·A2 페이퍼는 표시 안 함 — 새 정보·각도 A3·A4 관찰만
        obs = [r for r in rows if r["grade"].startswith(("새 정보", "각도 관찰 A3", "각도 관찰 A4"))]   # 새 정보 = 관찰(:N)·대조군(:NC)
        pub = pubs.get(gk, {})
        pr = preds.get(gk, {})
        m_, d_, b_ = pr.get("시장"), pr.get("모델"), pr.get("발행")
        pp = P.fnum(m_.get("p_pick")) if m_ else None
        pick_t = (b_ or m_ or {}).get("pick", ""); pick_of[gk] = pick_t
        star_of[gk] = P.fnum(b_.get("p_pick")) if b_ and b_.get("p_pick") else pp   # 펼침 머리 별점 — 발행 예측 확률(없으면 시장)
        # 킥오프 뒤 발행(기록용 · 집계 제외 — 10/18 Paul 「기록용으로 발행 요청한 건데」)은 꼬리표로 구분
        late_tag = ' <small class="muted" title="킥오프 뒤 발행 — 예측만 기록, 시즌 발행 예측 집계에서 빠짐">기록용(킥오프 뒤)</small>' if b_ and "기록용" in (b_.get("flag") or "") else ""

        def nm(t):   # 표·끝난 경기 줄의 팀 이름 — 우리 픽은 색
            return f'<span class="tn">{esc(name_kr(t))}</span>'   # 파란 글씨(우리 픽)는 발행문 칸에만(10/18 Paul 「너무 정신없으니」)
        win = ""
        if fin:
            fa, fh = float(lv.get("sa") or 0), float(lv.get("sh") or 0)
            win = H if fh > fa else A if fa > fh else ""
            if win and m_:
                live_wl[0 if m_.get("pick") == win else 1] += 1

        def phit(r):
            return hit("W" if r.get("pick") == win else "L") if fin and win and r else ""
        # ── 예측(맨 위)
        pred_html = ""
        if m_:
            stars = PR.star_str(pp)
            pred_html = (f'<div class="pred"><div>이길 팀 <b>{esc(name_kr(m_["pick"]))}({esc(m_["pick"])}) {pct(pp)}</b> '
                         f'<span class="star" title="2018~25 이 별 승자 적중 {PR.STAR_HIT.get(PR.stars(pp), "")}">{stars}</span> {phit(m_)}</div>')
            if b_ and (b_["pick"] != m_["pick"] or abs((P.fnum(b_.get("p_pick")) or 0) - (pp or 0)) >= 0.005 or late_tag):
                pred_html += f'<div class="sub">발행 예측 {esc(b_["pick"])} {pct(P.fnum(b_.get("p_pick")))} {phit(b_)}{late_tag}</div>'
            if d_ and d_["pick"] != m_["pick"]:
                pred_html += f'<div class="sub">우리 모델은 {esc(d_["pick"])} 쪽 — 시장과 반대(덜 정확한 두 번째 의견)</div>'
            pred_html += "</div>"
        # ── 결론 줄(낱말만, 근거는 title)
        items = []
        vw =verdict_word(pub.get("판단", ""))
        if vw in ("관심", "소액 관심"):
            items.append(f'<li><span class="tag pub" title="claude.ai 발행 세션 판단">발행</span> '
                         f'<b title="{esc(pub.get("굳이", ""))}">{esc(vw)}</b></li>')
        for r in obs:
            if r["grade"].startswith("새 정보"):
                lab = "새 정보(대조 — 판 이전 발표)" if "대조" in r["grade"] else "라인 뒤 새 정보"
            else:
                lab = r["grade"].split("(")[0].replace("각도 관찰 ", "각도 ")
            items.append(f'<li><span class="tag obs">{term("관찰", "관찰만")}</span> {lab} <b title="{esc(r.get("note", ""))}">{esc(r["side"])}</b> {hit(result_of(r, gk))}</li>')
        lines = f'<ul class="lines">{"".join(items)}</ul>' if items else ""
        div = '<span class="chip">디비전</span>' if g.get("div_game") == "1" else ""
        neu = '<span class="chip">중립 구장</span>' if g.get("neutral") == "1" else ""
        # ── 주차 전체 비교표 한 줄(MLB 서열표처럼 — 머리 누르면 정렬, 줄 누르면 발행문 펼침 · 10/11 Paul · 10/16 ML 전용)
        ml_txt, ml_s = "—", ""
        mh0, ma0 = P.fnum(g.get("ml_home")), P.fnum(g.get("ml_away"))
        if mh0 is not None and ma0 is not None:
            fav0 = (H, g["ml_home"], mh0) if mh0 < ma0 else (A, g["ml_away"], ma0)
            ml_txt, ml_s = f"{fav0[0]} {fav0[1]}", f"{-fav0[2]:g}"
        if fin:
            res_txt, res_s = f'<span class="num">{esc(str(lv.get("sa")))} – {esc(str(lv.get("sh")))}</span> {phit(m_) if m_ else ""}', 2
        elif st in IN_GAME:
            res_txt, res_s = f'<span class="state live">진행 중</span> <span class="num">{esc(str(lv.get("sa")))} – {esc(str(lv.get("sh")))}</span>', 1
        else:
            res_txt, res_s = '<span class="muted">예정</span>', 0
        kts = re.sub(r"\D", "", g.get("kickoff_utc", ""))[:12] or ""
        bp_ = P.fnum(b_.get("p_pick")) if b_ else None
        pub_cell = (f'{esc(name_kr(b_["pick"]))} {pct(bp_)} {phit(b_)}{late_tag}' if b_ else '<span class="muted">—</span>')
        vw0 = verdict_word(pub.get("판단", ""))
        trows.append((g.get("kickoff_utc", ""), f'<tr data-g="{esc(gk)}">'
                      f'<td data-s="{kts}"><div>{ha(False)}{mini(A)} {nm(A)} <small class="muted">{esc(g.get("away_rec", ""))}</small></div><div>{ha(True)}{mini(H)} {nm(H)} <small class="muted">{esc(g.get("home_rec", ""))}</small></div></td>'
                      f'<td data-s="{kts}">{esc(g["kickoff_et"].split(" ", 1)[0])} {esc(g["kickoff_pt"])}</td>'
                      f'<td data-s="{pp if pp is not None else ""}">{(esc(name_kr(m_["pick"])) + " " + pct(pp)) if m_ else "—"}</td>'
                      f'<td class="star" data-s="{PR.stars(pp) if m_ else ""}">{PR.star_str(pp) if m_ else ""}</td>'
                      f'<td data-s="{bp_ if bp_ is not None else ""}">{pub_cell}</td>'
                      f'<td data-s="{ml_s}">{esc(ml_txt)}</td>'
                      f'<td>{esc(vw0) or "—"}</td><td data-s="{res_s}">{res_txt}</td></tr>'))
        if fin:
            done_rows.append(f'''<details class="done"><summary>
  <span class="dm">{mini(A)}<b>{nm(A)}</b><small class="muted">{esc(g.get("away_rec", ""))}</small> <span class="num">{esc(str(lv.get("sa")))} – {esc(str(lv.get("sh")))}</span> <b>{nm(H)}</b><small class="muted">{esc(g.get("home_rec", ""))}</small>{mini(H)}</span>
  <span class="dr">{f'예측 {esc(m_["pick"])} <span class="star">{PR.star_str(pp)}</span> {phit(m_)}' if m_ else ''}</span></summary>
  <div class="dbody">{pred_html}{lines}<a class="goto" data-g="{esc(gk)}">발행문·보완 전문 보기 ↓</a></div></details>''')
            continue
        # ── 아직 안 한 경기 / 진행 중
        if st in IN_GAME:
            status = f'<span class="state live">진행 중</span> <b class="num">{esc(A)} {esc(str(lv.get("sa")))} – {esc(str(lv.get("sh")))} {esc(H)}</b> <span class="muted">{esc(lv.get("detail", ""))}</span>'
        else:
            status = f'<span class="state pre">예정</span> <span class="muted">{esc(g["kickoff_et"].split(" ", 1)[0])} {esc(g["kickoff_pt"])} PT</span>'
        ma, mh = N._novig(g.get("ml_away"), g.get("ml_home"))
        quick, price = [], []   # 10/16 ML 전용 — 스프레드·총점 줄 삭제
        if g.get("ml_home"):
            quick.append(f'{term("ML")} {esc(A)} <span class="num">{esc(g.get("ml_away"))}</span> / {esc(H)} <span class="num">{esc(g.get("ml_home"))}</span>')
            price.append(f'<tr><td>{term("ML")}</td><td>{esc(A)} <span class="num">{esc(g.get("ml_away"))}</span> · {esc(H)} <span class="num">{esc(g.get("ml_home"))}</span></td>'
                         f'<td class="muted">승리 {esc(A)} {pct(ma)} / {esc(H)} {pct(mh)}</td></tr>')
        mk = f'<div class="quick">{" · ".join(quick)}</div>' if quick else ""
        remaining += 1
        if not (b_ or (ptext.get(gk) or {}).get("main")):   # 발행문 없는 경기는 카드 안 만듦 — 표에만(10/18 Paul 「심플하게」)
            continue
        key = (-PR.stars(pp), g["kickoff_utc"])   # 별 많은 순 → 킥오프(10/15 실베팅 우선 정렬 삭제)
        pre_cards.append((key, f'''<article class="card" data-g="{esc(gk)}">
  <header class="match2">{team(A, lv.get("na"), rec=g.get("away_rec_full", ""), pk=A == pick_t)}{team(H, lv.get("nh"), rec=g.get("home_rec_full", ""), pk=H == pick_t, home=True)}</header>
  <div class="meta">{status}{div}{neu}</div>
  {pred_html}{mk}{lines}
</article>'''))
    pre_cards.sort(key=lambda x: x[0])
    trows.sort(key=lambda x: x[0])
    cmp_tbl = ('<div class="tblwrap"><table class="cmp"><thead><tr><th>경기</th><th>시간(PT)</th><th>예측 승자(시장)</th><th>★</th><th>발행 예측</th>'
               f'<th>{term("ML")} 페이버릿</th><th>판단</th><th>결과</th></tr></thead>'
               f'<tbody>{"".join(r for _, r in trows)}</tbody></table></div>')
    # ── 경기별 발행문·보완 전문(최신 발행 + 보완 · 이전 판은 접어 둠)
    pub_secs = []
    if pcommon:
        pub_secs.append('<details class="pubd"><summary><b>발행 공통</b> <span class="muted">— 머리말·요약표·출처·감사 줄(파일별)</span></summary><div class="md">'
                        + "".join(f'<div class="pubv"><div class="pubh">{esc(l)}</div>{md_html(c)}</div>' for l, c in pcommon) + "</div></details>")
    for g in sorted(games, key=lambda x: x.get("kickoff_utc", "")):
        A, H = g["away"], g["home"]; gk = f"{A}@{H}"
        d = ptext.get(gk); pk_ = pick_of.get(gk, "")

        # 강조·꼬리표 재료(10/25 NBA 10/24 이식): 우리 픽 팀 파랑 · 상대 주황 · 선수 굵게 · 스탯 회색 굵게 · 선수 첫 등장 (팀 · 포지션 · 역할 · 상태)
        opp_ = H if pk_ == A else A if pk_ == H else ""
        texts_ = [b_ for _, _, b_ in ((d["main"][-1:] + d["supp"]) if d else [])]
        full_, short_ = pos_maps(game_player_rows(texts_, A, H), [r for r in inact if r.get("game") == gk], A, H)
        hl_ = deco_regex(list(full_) + list(short_), team_alias(pk_) if pk_ else [], team_alias(opp_) if opp_ else team_alias(A) + team_alias(H))
        ref_html = ref_table(wd, gk)

        def mk(x):
            return md_html(annotate_pos(x, full_, short_), hl_, (A, H, pk_))

        def boxes(b, cats=None):
            cats = pub_cats(b) if cats is None else cats
            if [c for c, _ in cats] == ["기타"]:   # 라벨 없는 글(서술형 보완)은 상자 이름 없이
                return mk(b)
            return "".join(f'<div class="cat"><h5>{esc(c)}</h5>'
                           f'{players_html(annotate_pos(t, full_, short_), A, H, pk_, hl_) if c == "선수" else (ref_html if c == "심판" else "") + mk(t)}</div>'
                           for c, t in cats)
        if d and (d["main"] or d["supp"]):
            body, mains, supp_html = "", d["main"], ""
            for l1, h1, b1 in d["supp"]:
                # 보완 머리 「**DEN@LAC** — LAC 오펜스 라인이 더 비어요」 의 뒷말도 보인다(10/11 11:35 보완 — 경기 코드만 떼고)
                h1r = re.sub(r"^(?:#{1,4}\s*)?(?:🏈\s*)?(?:\*\*)?[A-Z]{2,3}@[A-Z]{2,3}(?:\*\*)?\s*(?:[—·-]\s*)?", "", h1).strip()
                supp_html += (f'<div class="cat supp"><h5>보완 — {esc(l1)}</h5>'
                              + (f'<div class="pubh">{mk(h1r)}</div>' if h1r else "") + boxes(b1) + "</div>")
            if mains:
                l0, h0, b0 = mains[-1]
                h0r = re.sub(r"^(?:#{1,4}\s*)?(?:🏈\s*)?(?:\*\*)?[A-Z]{2,3}\s*@\s*[A-Z]{2,3}(?:\*\*)?\s*(?:[—·-]\s*)?", "", h0).strip()
                cats = pub_cats(b0)
                body += (f'<div class="pubh">{esc(l0)} 발행{(" · " + esc(h0r)) if h0r else ""}</div>'
                         + boxes(b0, [x for x in cats if x[0] == "결론"]) + supp_html + boxes(b0, [x for x in cats if x[0] != "결론"])
                         + (f'<div class="cat"><h5>심판</h5>{ref_html}</div>' if ref_html and not any(c == "심판" for c, _ in cats) else ""))
            else:
                body += supp_html
            if len(mains) > 1:
                body += ('<details class="prevv"><summary>이전 판 보기 — ' + esc(" · ".join(x[0] for x in mains[:-1])) + "</summary>"
                         + "".join(f'<div class="pubv"><div class="pubh">{esc(l2)} 발행</div>{mk(h2)}{mk(b2)}</div>' for l2, h2, b2 in reversed(mains[:-1]))
                         + "</details>")
            cnt = f"발행 {len(mains)}판" + (f" · 보완 {len(d['supp'])}" if d["supp"] else "")
        else:
            body, cnt = '<p class="muted">아직 이 경기 발행문이 없어요.</p>', "발행문 없음"
        pub_secs.append(f'<details class="pubd" data-p="{esc(gk)}"><summary>{mini(A)} <span class="{"pk" if A == pk_ else ""}">{esc(name_kr(A))}</span> <small class="muted">{esc(g.get("away_rec", ""))}</small> @ <span class="{"pk" if H == pk_ else ""}">{esc(name_kr(H))}</span> <small class="muted">{esc(g.get("home_rec", ""))}</small> {mini(H)} {(f'<span class="star">{PR.star_str(star_of[gk])}</span> <span class="num">{esc(pk_)} {pct(star_of[gk])}</span> ') if pk_ and star_of.get(gk) is not None else ""}'
                        f'<span class="muted">{esc(g["kickoff_et"].split(" ", 1)[0])} {esc(g["kickoff_pt"])} PT · {cnt}</span></summary><div class="md">{body}</div></details>')
    logo_css = (".mini{display:inline-block;width:22px;height:22px;background-size:contain;background-repeat:no-repeat;vertical-align:middle}"
                + ".tlogo{display:inline-block;width:36px;height:36px;flex:none;background-size:contain;background-repeat:no-repeat}"
                + "".join(f'.lg-{t}{{background-image:url("{logo_uri(t)}")}}' for t in sorted(mini_used)))
    now = datetime.now().strftime("%m/%d %H:%M")
    # ── 이번 주 한 줄 결론
    wm = wsum.get("시장", {})
    verdicts = [verdict_word(pubs.get(f'{g["away"]}@{g["home"]}', {}).get("판단", "")) for g in games
                if live.get(f'{g["away"]}@{g["home"]}', {}).get("state") != "STATUS_FINAL"]
    cand = sum(1 for v in verdicts if v in ("관심", "소액 관심"))
    headline = f'남은 경기 <b>{remaining}</b>(발행 {len(pre_cards)} · 발행 전 {remaining - len(pre_cards)}) · 발행 후보 <b>{cand}</b>'
    ms = psum.get("시장", {})
    star_rows = "".join(
        f'<tr><td class="star">{"★" * k}</td><td class="num">{w}-{l}</td><td class="num">{(f"{100 * w / (w + l):.0f}%") if w + l else "—"}</td><td class="num muted">{PR.STAR_HIT[k]}</td></tr>'
        for k, (w, l) in ms.get("stars", {}).items())
    page = f'''<meta charset="utf-8"><title>NFL {a.week}주차 보드</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Saira+Extra+Condensed:wght@600;800&family=Noto+Sans+KR:wght@400;500;700&family=IBM+Plex+Mono:wght@500&display=swap" rel="stylesheet">
<style>
/* 구장 라인 감성 — 잔디 기운의 중립색 위에 흰 분필선 · 10/22 Paul 「깔끔하게 — 팀명 색 빼」: 강조색(주황)은 진행 중·정렬 표시만, 색은 맞힘/틀림 칩 · 소제목(파랑) */
:root{{--bg:#eef2ec;--panel:#ffffff;--ink:#14231b;--muted:#5d6b62;--line:#d4ddd3;--acc:#e8590c;--ok:#1f8a4c;--bad:#c2362b;--push:#8a7a1f;--term:#6b3fb5;--soft:#f6f8f4;--acc2:#2b5ea7;--wait:#8a7b5a;
  --display:"Saira Extra Condensed","Arial Narrow",sans-serif;--body:"Noto Sans KR","Apple SD Gothic Neo","Malgun Gothic",sans-serif;--mono:"IBM Plex Mono",ui-monospace,monospace}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#0f1712;--panel:#16211a;--ink:#e6efe7;--muted:#97a69b;--line:#26352b;--acc:#ff7a2e;--ok:#4cc27a;--bad:#ef6a5f;--push:#cdbb52;--term:#b99af0;--soft:#1b281f;--acc2:#8cb4ef;--wait:#b7a67c;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#0f1712;--panel:#16211a;--ink:#e6efe7;--muted:#97a69b;--line:#26352b;--acc:#ff7a2e;--ok:#4cc27a;--bad:#ef6a5f;--push:#cdbb52;--term:#b99af0;--soft:#1b281f;--acc2:#8cb4ef;--wait:#b7a67c;color-scheme:dark}}
body{{background:var(--bg);color:var(--ink);font-family:var(--body);font-size:14px;line-height:1.55}}
.wrap{{max-width:1320px;margin:0 auto;padding-inline:16px;padding-block:20px 40px;display:grid;gap:18px}}
h1{{font-family:var(--display);font-weight:800;font-size:2.4rem;letter-spacing:.02em;margin:0;line-height:1}}
h2{{font-family:var(--display);font-weight:600;font-size:1.35rem;letter-spacing:.03em;margin:0}}
.top{{display:flex;flex-wrap:wrap;gap:8px 24px;align-items:end;justify-content:space-between;border-bottom:2px solid var(--ink);padding-bottom:10px}}
.muted{{color:var(--muted)}}
.num{{font-family:var(--mono);font-variant-numeric:tabular-nums}}
.chips{{display:flex;flex-wrap:wrap;gap:8px}}
.stat{{background:var(--panel);border:1px solid var(--line);padding:6px 12px;display:flex;gap:8px;align-items:baseline}}
.stat .k{{font-size:.75rem;color:var(--muted)}}
.stat .v{{font-family:var(--display);font-size:1.4rem;font-weight:600;font-variant-numeric:tabular-nums}}
.headline{{background:var(--panel);border-left:4px solid var(--line);padding:10px 14px;font-size:1rem}}
.legend{{background:var(--soft);border:1px solid var(--line);padding:12px 14px;display:grid;gap:4px;font-size:.86rem}}
.legend b{{font-weight:700}}
.term{{color:inherit;text-decoration:none;border-bottom:1px dotted var(--muted);cursor:help}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}}
.card{{background:var(--panel);border:1px solid var(--line);padding:14px;display:grid;gap:10px;min-width:0;align-content:start}}
.match{{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:8px}}
.match2{{display:grid;gap:6px}}
.ha{{display:inline-block;min-width:2.6em;margin-right:6px;padding:0 4px;font-size:.66rem;line-height:1.5;text-align:center;border:1px solid var(--line);color:var(--muted);vertical-align:middle}}
.ha.h{{border-color:var(--ink);color:var(--ink);font-weight:700}}
.trow{{display:flex;align-items:center;gap:8px;min-width:0}}
.trow .tlogo{{width:28px;height:28px}}
.trow .tname{{font-weight:700;font-size:1rem;line-height:1.2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.trow .tinfo{{display:flex;flex-direction:column;min-width:0;line-height:1.25}}
.trow .trec{{font-size:.74rem;color:var(--muted);white-space:nowrap}}
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
.pred{{display:grid;gap:2px;font-size:.92rem;background:var(--soft);padding:8px 10px}}
.pred .sub,.sub{{color:var(--muted);font-size:.8rem}}
.star{{color:var(--ink);letter-spacing:.05em}}
.quick{{font-size:.86rem}}
details.px summary{{font-size:.76rem;color:var(--muted);cursor:pointer}}
details.px table{{border-collapse:collapse;width:100%;font-size:.8rem;margin-top:4px}}
details.px td{{padding:3px 6px 3px 0;border-bottom:1px dashed var(--line);vertical-align:top}}
.lines{{list-style:none;margin:0;padding:0;display:grid;gap:5px;border-top:1px dashed var(--line);padding-top:8px;font-size:.86rem}}
.tag{{font-size:.68rem;padding:1px 6px;margin-right:4px;border:1px solid var(--line)}}
.tag.obs{{border-style:dashed}}
.hit{{font-size:.7rem;padding:0 5px;margin-left:2px;border:1px solid}}
.hit.w{{color:var(--ok)}}.hit.l{{color:var(--bad)}}.hit.p{{color:var(--push)}}
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
nav.weeks{{display:flex;flex-wrap:wrap;gap:4px 8px;align-items:baseline;font-size:.92rem}}
nav.weeks a{{color:var(--ink)}}nav.weeks b.cur{{color:var(--ink);text-decoration:underline;text-underline-offset:3px}}nav.weeks a.hub{{margin-left:8px;color:var(--ink);font-weight:700}}
@media (max-width:420px){{h1{{font-size:2rem}}.grid{{grid-template-columns:1fr}}}}
{EXTRA_CSS}
{logo_css}
</style>
<div class="wrap">
  <div class="top"><h1>NFL {a.week}주차 보드</h1><div class="muted">갱신 {now} PT · 표시 전용(정본: 다이제스트·발행문) · 시간은 PT(캘리포니아)</div></div>
  {week_nav(a.week)}
  <div class="chips">
    <div class="stat"><span class="k">승자 예측 시즌</span><span class="v">{ms.get("w", 0) - wm.get("w", 0) + live_wl[0]}-{ms.get("l", 0) - wm.get("l", 0) + live_wl[1]}</span></div>
    <div class="stat"><span class="k">승자 예측 이번 주</span><span class="v">{live_wl[0]}-{live_wl[1]}</span></div>
  </div>
  <div class="headline">{headline}</div>
  <h2>{a.week}주차 전체 경기 <span class="muted" style="font-size:.9rem">— 머리 누르면 정렬 · 줄 누르면 발행문</span></h2>
  {cmp_tbl}
  <section class="legend">
    <div><b>읽는 법</b> — 점선 밑줄 낱말에 손가락·마우스를 대면 뜻이 나와요.</div>
    <div><span class="star">★</span> = <b>이길 확률이 높은 정도</b>(2018~25 실제 적중 ★ 50% · ★★ 61% · ★★★ 71% · ★★★★ 82%). <b>돈 버는 신호가 아니에요</b> — 별이 많은 팀일수록 ML 배당이 비싸서, 맞혀도 남는 돈이 적어요.</div>
    <div>{term("ML")} = 그냥 이길 팀 — 10/16부터 보드는 <b>이길 팀 예측(ML)만</b> 보여 줘요(점수 차·총점·방향은 뺐어요).</div>
    <div>{term("관찰", "관찰만")} = 돈 안 건 기록(라인 뒤 새 정보 · 각도 A3·A4) · 맞힘/틀림 = 예측·관찰 결과</div>
    <div><b>발행문 글자</b> — <b style="color:var(--acc2)">파란 굵은 팀</b> = 우리 예측 팀 · <b style="color:var(--acc)">주황 굵은 팀</b> = 상대 · <b>굵은 검정</b> = 선수(처음 나올 때 「팀 · 포지션 · 역할 · 상태」) · <b style="color:var(--muted)">회색 굵은 낱말</b> = 스탯 이름(EPA·CPOE·야드/캐리 …) · 긴 줄은 묶음·문장마다 줄을 바꾸고, 「NE 값 vs CHI 값」 줄은 비교표로 · 선수 표는 왼쪽 원정 / 오른쪽 홈, 색이 진할수록 큰 값(표 아래 풀이). 상자 순서: 결론 → 보완 → 시장 → 팀 상태 → 선수 → 팀 비교 → 심판.</div>
    {gloss_all()}
    <div><b>카드나 표 줄을 누르면</b> 그 경기의 발행문·보완 전문이 아래에서 펼쳐져요. 표 머리(예측 승자·★·발행 예측 …)를 누르면 그 기준으로 정렬돼요.</div>
  </section>
  {f'<h2>끝난 경기 <span class="muted" style="font-size:.9rem">— 눌러서 펼치기</span></h2><section class="donelist">{"".join(done_rows)}</section>' if done_rows else ""}
  <h2>아직 안 한 경기 — 발행된 경기 <span class="muted" style="font-size:.9rem">(발행 전 경기는 위 표에만)</span></h2>
  {f'<section class="grid">{"".join(c for _, c in pre_cards)}</section>' if pre_cards else ('<p class="muted">이번 주 경기가 모두 끝났어요.</p>' if not remaining else '<p class="muted">아직 발행문이 나온 경기가 없어요.</p>')}
  <h2>발행문·보완 전문 — 경기별 <span class="muted" style="font-size:.9rem">(카드·표 줄을 누르면 여기서 펼쳐져요)</span></h2>
  <section class="publist">{"".join(pub_secs)}</section>
  <h2>별점별 승자 적중 — 시즌(시장 예측)</h2>
  <div><table class="tiers"><thead><tr><th>별</th><th>W-L</th><th>올해</th><th>2018~25 기대</th></tr></thead><tbody>{star_rows}</tbody></table>
  <p class="note">1~4주차 일부는 마감 배당으로 소급한 기록이에요. 표본이 작아 몇 주는 기대와 어긋나는 게 정상이에요.</p></div>
  <details class="more"><summary>숫자 자세히</summary>
    <p>승자 예측 시즌 · 시장 {ms.get("w", 0)}-{ms.get("l", 0)} · 발행 {psum.get("발행", {}).get("w", 0)}-{psum.get("발행", {}).get("l", 0)} · 우리 모델 {psum.get("모델", {}).get("w", 0)}-{psum.get("모델", {}).get("l", 0)}</p>
  </details>
  {prev_week_link(a.week)}
  <p class="note">표시 전용 — 재계산 없음 · 정본은 다이제스트(DIGEST.md)·발행문·picks.csv · 배당은 DraftKings(ESPN), 경기가 시작되면 ESPN 에서 사라져 끝난 경기엔 표시하지 않아요.</p>
</div>''' + BOARD_JS
    out = a.out or os.path.join(os.path.dirname(HERE), "board", f"board-w{a.week:02d}.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write(page)
    print("wrote", out, f"{len(page):,} bytes")
    if a.hub_out:
        open(a.hub_out, "w", encoding="utf-8").write(hub_html(live={a.week: live_wl}))
        print("wrote", a.hub_out)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
