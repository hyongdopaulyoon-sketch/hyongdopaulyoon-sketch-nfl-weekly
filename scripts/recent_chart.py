# -*- coding: utf-8 -*-
"""recent_chart.py (NFL) — 경기 펼침 줄 안 「두 팀 최근 10경기 점수 차 막대」.
2026-11-19 Paul(NBA 보드 세션 경유) 「nfl보드도 똑같이 하도록」 · 「가장 최근주만 적용하고 앞으로」 · 경기 수 = 최근 10경기 · 막대 색 = 초록·빨강(NBA 와 같게).
NBA scripts/recent_chart.py(4b66e37 · 4db5c48 · 1db8d55) 이식:
  위 = 이긴 점수 차(초록) · 아래 = 진 점수 차(빨강) · 모든 막대에 점수 차 숫자(최고·최저는 굵고 크게) ·
  막대 밑 = 상대 로고(페이지에 <symbol> 한 번 · <use> 재사용) + 굵은 상대 약자(@ = 원정) ·
  점 = 마감 스프레드 커버(채움 = 커버 · 빈 원 = 못함 · 가로줄 = 푸시/라인 없음) · 두 팀 같은 눈금 · 왼쪽 = 오래된 주 → 오른쪽 = 가장 최근.
값만 — 확률·★·픽에 안 쓴다. 데이터 = data/2026-wNN/predictions.csv 시장 행(final 점수 · line_home) · 마감 라인은 같은 주 closing.csv spread_home 우선."""
import csv, glob, html, os, re

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
N = 10
FROM_WEEK = 11   # 이 주차 보드부터(지난 주차는 재생성하지 않는다)
CSS = """<style>
.rcw{margin:4px 0 6px}.rct{color:var(--muted);font-size:.76rem;margin:0 0 4px}
.rcg{display:flex;flex-wrap:wrap;gap:8px 26px}.rcb{flex:1 1 300px;min-width:0;max-width:460px}
.rch{font-size:.82rem;margin:0 0 2px;font-variant-numeric:tabular-nums;color:var(--ink)}.rch .sub{color:var(--muted)}.rch .pk{color:var(--acc2)}
.rcs{display:block;width:100%;height:auto}.rcw-b{fill:var(--ok)}.rcl-b{fill:var(--bad)}
.rcax{stroke:var(--muted);stroke-width:1}
.rcopp{fill:var(--ink);font-size:10px;font-weight:700}.rcwk{fill:var(--muted);font-size:8.5px}.rcv{fill:var(--ink);font-size:9px;font-weight:600}.rcvx{fill:var(--ink);font-size:11px;font-weight:800}
.rccv{fill:var(--ink)}.rcno{fill:none;stroke:var(--ink);stroke-width:1.2}.rcna{stroke:var(--muted);stroke-width:1.4}
.rchit{fill:transparent}.rchit:hover{fill:var(--soft);fill-opacity:.6}
</style>"""

USED = set()   # 이 페이지 차트에 나온 상대 팀 — logo_defs 가 로고를 한 번씩만 넣는다
_G = {}


def _e(s):
    return html.escape(str(s))


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def logo_defs(logo_fn):
    """상대 로고 심볼(페이지에 한 번 · 차트는 <use href="#rclg-팀">) — 로고를 못 받으면 그 팀은 약자만 보인다."""
    syms = []
    for t in sorted(USED):
        u = logo_fn(t)
        if u:
            syms.append(f'<symbol id="rclg-{_e(t)}" viewBox="0 0 64 64"><image href="{u}" width="64" height="64"/></symbol>')
    return ('<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>' + "".join(syms) + "</defs></svg>") if syms else ""


def season_games():
    """올 시즌 끝난 경기 [{week, a, h, sa, sh, sp_home}] — predictions.csv 시장 행 final 이 있는 것만(주차·경기당 한 번)."""
    if "v" in _G:
        return _G["v"]
    out, seen = [], set()
    for p in sorted(glob.glob(os.path.join(DATA, "2026-w*", "predictions.csv"))):
        wd = os.path.dirname(p)
        wk = int(os.path.basename(wd).split("-w")[1])
        close = {}
        cp = os.path.join(wd, "closing.csv")
        if os.path.exists(cp):
            for x in csv.DictReader(open(cp, encoding="utf-8-sig", newline="")):
                if x.get("game") and _f(x.get("spread_home")) is not None:
                    close[x["game"]] = _f(x["spread_home"])
        for x in csv.DictReader(open(p, encoding="utf-8-sig", newline="")):
            if x.get("src") != "시장" or (wk, x.get("game")) in seen:
                continue
            m = re.match(r"\S+ (\d+)-(\d+) \S+$", (x.get("final") or "").strip())
            if not m or "@" not in x.get("game", ""):
                continue
            seen.add((wk, x["game"]))
            a, h = x["game"].split("@")
            out.append({"week": wk, "a": a, "h": h, "sa": int(m.group(1)), "sh": int(m.group(2)),
                        "sp_home": close.get(x["game"], _f(x.get("line_home")))})
    _G["v"] = out
    return out


def team_recent(team, week, n=N):
    """week 주 전에 끝난 team 의 최근 n 경기 → [{week, opp, home, pf, pa, margin, spread, cover}] (오래된 것 → 최근)."""
    out = []
    for g in season_games():
        if g["week"] >= week or team not in (g["a"], g["h"]):
            continue
        home = team == g["h"]
        pf, pa = (g["sh"], g["sa"]) if home else (g["sa"], g["sh"])
        sp = None if g["sp_home"] is None else (g["sp_home"] if home else -g["sp_home"])
        mg = pf - pa
        cv = None if sp is None else ("P" if mg + sp == 0 else ("W" if mg + sp > 0 else "L"))
        out.append({"week": g["week"], "opp": g["a"] if home else g["h"], "home": home, "pf": pf, "pa": pa,
                    "margin": mg, "spread": sp, "cover": cv})
    out.sort(key=lambda x: x["week"])
    return out[-n:]


def _bar(x, w, y0, y1, r=3):
    """기준선(y0)에서 값(y1)까지 막대 — 값 쪽 끝만 둥글게."""
    if abs(y1 - y0) < 1:
        y1 = y0 - 1 if y1 <= y0 else y0 + 1
    r = min(r, abs(y1 - y0), w / 2)
    if y1 < y0:   # 위로(이김)
        return (f"M{x:.1f},{y0:.1f}V{y1 + r:.1f}Q{x:.1f},{y1:.1f} {x + r:.1f},{y1:.1f}H{x + w - r:.1f}"
                f"Q{x + w:.1f},{y1:.1f} {x + w:.1f},{y1 + r:.1f}V{y0:.1f}Z")
    return (f"M{x:.1f},{y0:.1f}V{y1 - r:.1f}Q{x:.1f},{y1:.1f} {x + r:.1f},{y1:.1f}H{x + w - r:.1f}"
            f"Q{x + w:.1f},{y1:.1f} {x + w:.1f},{y1 - r:.1f}V{y0:.1f}Z")


def _sp(v):
    return "—" if v is None else ("PK" if v == 0 else f"{v:+g}")


def team_svg(team, rows, M):
    W, HH, top, mid_h = 320, 168, 14, 40   # 막대 반높이 40 · 위 글씨 14 · 아래: 진 점수 글씨 → 상대 로고·약자 → 커버 점 → 주차
    y0 = top + mid_h
    hi = max(range(len(rows)), key=lambda j: rows[j]["margin"]) if rows else -1   # 최고·최저 = 굵게
    lo = min(range(len(rows)), key=lambda j: rows[j]["margin"]) if rows else -1
    slot = W / N
    bw = min(18.0, slot * 0.56)
    o = [f'<svg class="rcs" viewBox="0 0 {W} {HH}" role="img" aria-label="{_e(team)} 최근 {len(rows)}경기 점수 차 막대">',
         f'<line x1="0" y1="{y0}" x2="{W}" y2="{y0}" class="rcax"/>']
    pad = N - len(rows)   # 10경기 미만이면 왼쪽을 비운다(최근 경기는 늘 오른쪽 끝)
    for i, g in enumerate(rows):
        cx = (pad + i) * slot + slot / 2
        if g["margin"] == 0:
            y1, cls, res = y0 - 1, "rcax", "무"
        else:
            hgt = min(abs(g["margin"]), M) / M * mid_h
            y1 = y0 - hgt if g["margin"] > 0 else y0 + hgt
            cls, res = ("rcw-b", "승") if g["margin"] > 0 else ("rcl-b", "패")
        cvt = {"W": "커버", "L": "커버 못함", "P": "푸시"}.get(g["cover"], "라인 없음")
        tip = (f'{g["week"]}주차 · {"홈" if g["home"] else "원정"} {"vs" if g["home"] else "@"} {g["opp"]} · {g["pf"]}-{g["pa"]} {res} {g["margin"]:+d}'
               f' · 마감 스프레드 {team} {_sp(g["spread"])} → {cvt}')
        o.append(f'<g><title>{_e(tip)}</title><rect x="{cx - slot / 2:.1f}" y="0" width="{slot:.1f}" height="{HH}" class="rchit"/>'
                 f'<path d="{_bar(cx - bw / 2, bw, y0, y1)}" class="{cls}"/>')
        ty = y1 - 3 if g["margin"] > 0 else y1 + 10
        o.append(f'<text x="{cx:.1f}" y="{ty:.1f}" text-anchor="middle" class="{"rcvx" if i in (hi, lo) else "rcv"}">{g["margin"]:+d}</text>')
        USED.add(g["opp"])
        o.append(f'<use href="#rclg-{_e(g["opp"])}" x="{cx - 9:.1f}" y="{y0 + mid_h + 13:.1f}" width="18" height="18"/>')
        o.append(f'<text x="{cx:.1f}" y="{y0 + mid_h + 43:.1f}" text-anchor="middle" class="rcopp">{"" if g["home"] else "@"}{_e(g["opp"])}</text>')
        cy = y0 + mid_h + 55
        if g["cover"] == "W":
            o.append(f'<circle cx="{cx:.1f}" cy="{cy}" r="3.6" class="rccv"/>')
        elif g["cover"] == "L":
            o.append(f'<circle cx="{cx:.1f}" cy="{cy}" r="3.2" class="rcno"/>')
        else:
            o.append(f'<line x1="{cx - 3.5:.1f}" y1="{cy}" x2="{cx + 3.5:.1f}" y2="{cy}" class="rcna"/>')
        o.append(f'<text x="{cx:.1f}" y="{cy + 13}" text-anchor="middle" class="rcwk">{g["week"]}주</text></g>')
    o.append("</svg>")
    return "".join(o)


def _summary(team, rows, pick):
    w = sum(1 for g in rows if g["margin"] > 0)
    t_ = sum(1 for g in rows if g["margin"] == 0)
    avg = sum(g["margin"] for g in rows) / len(rows)
    cw = sum(1 for g in rows if g["cover"] == "W"); cl = sum(1 for g in rows if g["cover"] == "L"); cp = sum(1 for g in rows if g["cover"] == "P")
    streak, last = 0, None
    for g in reversed(rows):
        if g["margin"] == 0:
            break
        r_ = g["margin"] > 0
        if last is None or r_ == last:
            streak += 1; last = r_
        else:
            break
    stk = f'{streak}연승' if streak >= 2 and last else (f'{streak}연패' if streak >= 2 else "")
    hi = max(rows, key=lambda g: g["margin"]); lo = min(rows, key=lambda g: g["margin"])
    rec = f"{w}승 {len(rows) - w - t_}패" + (f" {t_}무" if t_ else "")
    return (f'<div class="rch"><b class="{"pk" if team == pick else ""}">{_e(team)}</b> 최근 {len(rows)}경기 <b>{rec}</b>'
            f' · 평균 점수차 {avg:+.1f}' + (f" · {stk}" if stk else "")
            + f' · 최고 {hi["margin"]:+d}({"" if hi["home"] else "@"}{_e(hi["opp"])}) · 최저 {lo["margin"]:+d}({"" if lo["home"] else "@"}{_e(lo["opp"])})'
            + f' <span class="sub">· 스프레드 커버 {cw}-{cl}' + (f"-{cp}" if cp else "") + "</span></div>")


def team_block(week, A, H, pick=""):
    if int(week) < FROM_WEEK:
        return ""
    ra, rh = team_recent(A, int(week)), team_recent(H, int(week))
    if not ra and not rh:
        return ""
    M = min(max([10] + [abs(g["margin"]) for g in ra + rh]), 40)
    cells = "".join(f'<div class="rcb">{_summary(t, rows, pick)}{team_svg(t, rows, M)}</div>' for t, rows in ((A, ra), (H, rh)) if rows)
    return ('<div class="rcw"><p class="rct"><b>최근 10경기</b>(올 시즌 · 왼쪽 = 오래된 주 → 오른쪽 = 가장 최근) · 막대 위 초록 = 이긴 점수 차 · 아래 빨강 = 진 점수 차(숫자 = 점수 차 · 굵은 숫자 = 최고·최저) · '
            '두 팀 같은 눈금 · 막대 밑 = 상대 로고와 이름(@ = 원정 · 없으면 홈) · 점 = 마감 스프레드 커버(채움 = 커버 · 빈 원 = 못함 · 가로줄 = 푸시/라인 없음) · 마우스를 대면 점수 · 값만(확률·픽 무영향)</p>'
            f'<div class="rcg">{cells}</div></div>')


if __name__ == "__main__":
    import sys
    wk, a, h = int(sys.argv[1]), sys.argv[2], sys.argv[3]
    for t in (a, h):
        print(t, [(g["week"], ("" if g["home"] else "@") + g["opp"], g["margin"], g["cover"]) for g in team_recent(t, wk)])
