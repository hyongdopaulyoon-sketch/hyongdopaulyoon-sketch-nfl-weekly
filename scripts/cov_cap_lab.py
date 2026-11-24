# -*- coding: utf-8 -*-
"""cov_cap_lab.py — 육각형 커버리지 점수에 「결장으로는 못 오르게」 상한을 두면 승패 설명력이 좋아지나(2026-11-24 Paul 「4번은 일단 점검 먼저」).

    python scripts/cov_cap_lab.py     → data/cov_cap_lab_<오늘>.md   (hex_baseline.json 은 읽기만 · 약 15분)

배경: 커버리지 = 「뛰는」 커버리지 선수 타깃 상위 4명의 타깃당 허용 야드. 주전(타깃을 많이 받는 CB1)이 빠지면 타깃당 허용이 낮은 후보가 넷에 들어와 점수가 오르는 일이 있다(11주차 8칸).
세 가지 값을 같은 경기에서 견준다(2018~2025 정규시즌 2주차~ · 출전 판정은 스냅 기록 · 점수 기준선은 지금 쓰는 hex_baseline.json 그대로):
  · 현행      = 실제 뛴 선수 넷의 점수.
  · 상한      = min(현행, 전원 가용 가정 점수) — 결장으로는 내려가기만 한다.
  · 전원 가용 = 결장을 아예 안 본 점수.
읽는 기준(실행 전 고정): 「상한」 의 승패 상관이 현행보다 높고 커버(스프레드 대비) 상관이 현행보다 낮지 않으면 표시를 상한으로 바꿀 근거 · 아니면 현행 유지(회색 「결장으로 오름」 표시만).
표시용 꼭짓점이라 예측·★·각도·스프레드 픽과 무관.
"""
import datetime as dt, io, json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfl_pull as N  # noqa: E402
import team_hex as TH  # noqa: E402

V = "커버리지"


def build(seasons=range(2018, 2026)):
    games = [g for g in N.rd(os.path.join(N.CACHE, "games.csv")) if g["game_type"] == "REG" and g.get("result") and g.get("spread_line")]
    PREV = TH.prev_tot(TH.season_tables(min(seasons) - 1)); rows = []
    for season in seasons:
        S = TH.season_tables(season)
        for g in games:
            if int(g["season"]) != season or int(g["week"]) < 2:
                continue
            wk = int(g["week"]); gid = g["game_id"]; mats = {}
            for t, q in ((g["home_team"], g.get("home_qb_name")), (g["away_team"], g.get("away_qb_name"))):
                def plays(kind, nm, t=t):   # team_hex.backtest 와 같은 출전 판정(스냅 기록)
                    key = (gid, t)
                    if kind == "ol":
                        return nm in S["olplay"][key]
                    if kind == "def":
                        return (N._norm_name(nm) in S["snap_def"][key]) if S["snap_def"][key] else (nm in S["dplay"][key])
                    if not S["snap_offk"][key]:
                        return nm in S["use"][key]
                    _w = [x for x in N._norm_name(nm.split(".", 1)[1] if "." in nm else nm).split() if x]
                    return bool(_w) and (nm[0].lower(), _w[-1]) in S["snap_offk"][key]
                mats[t] = TH.materials(S, PREV, t, wk, q, plays)
                mats[t + "_full"] = TH.materials(S, PREV, t, wk, q, lambda kind, nm: True)
            rows.append(dict(season=season, res=N.fnum(g["result"]), mk=N.fnum(g["spread_line"]), h=mats[g["home_team"]], a=mats[g["away_team"]],
                             hf=mats[g["home_team"] + "_full"], af=mats[g["away_team"] + "_full"]))
        PREV = TH.prev_tot(S); print(f"  {season}: 누적 {len(rows)}경기", flush=True)
    return rows


def corr(xs, ys):
    n = len(xs)
    if n < 30:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs)); sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy) if sx and sy else float("nan")


def main():
    base = json.load(io.open(TH.BASE, encoding="utf-8"))
    import pickle
    cp = os.path.join(N.CACHE, "cov_cap_rows.pkl")
    if os.path.exists(cp):
        rows = pickle.load(open(cp, "rb"))
    else:
        rows = build()
        with open(cp + ".tmp", "wb") as f:
            pickle.dump(rows, f)
        os.replace(cp + ".tmp", cp)
    sc = []
    for r in rows:
        sh, sa, fh, fa = TH.scores(base, r["h"]), TH.scores(base, r["a"]), TH.scores(base, r["hf"]), TH.scores(base, r["af"])
        if sh and sa and fh and fa:
            sc.append((r, sh, sa, fh, fa))
    win = [1.0 if r["res"] > 0 else 0.0 for r, *_ in sc]; mar = [r["res"] for r, *_ in sc]; cov = [r["res"] - r["mk"] for r, *_ in sc]
    var = {"현행(실제 뛴 선수)": lambda s, f: s[V], "상한(결장으로는 못 오름)": lambda s, f: min(s[V], f[V]), "전원 가용(결장 안 봄)": lambda s, f: f[V]}
    L = [f"# 커버리지 점수 상한 검정 — {dt.date.today()} · 2018~2025 정규시즌(2주차~) {len(sc)}경기", "",
         "Paul 「4번은 일단 점검 먼저」(11/24) · 정의·읽는 기준은 scripts/cov_cap_lab.py 머리 · 표시용 꼭짓점(예측·★ 무관).", "",
         "## ① 커버리지 차(홈 − 원정)와 결과의 상관", "",
         "| 값 | 승패 상관 | 점수차 상관 | 커버 상관 | 차 15+ 인 쪽 승률 | 차 15+ 인 쪽 스프레드 | 여섯 합 승패 상관 | 여섯 합 점수차 상관 |", "|---|---|---|---|---|---|---|---|"]
    res = {}
    for lab, fn in var.items():
        xs = [fn(sh, fh) - fn(sa, fa) for r, sh, sa, fh, fa in sc]
        big = [(r, x) for (r, *_), x in zip(sc, xs) if abs(x) >= 15]
        w = sum(1 for r, x in big if r["res"] != 0 and (r["res"] > 0) == (x > 0)); n = sum(1 for r, x in big if r["res"] != 0)
        cw = sum(1 for r, x in big if r["res"] != r["mk"] and ((r["res"] - r["mk"]) > 0) == (x > 0)); cn = sum(1 for r, x in big if r["res"] != r["mk"])
        tot = [sum(sh[v] - sa[v] for v in TH.VERTS if v != V) + x for (r, sh, sa, fh, fa), x in zip(sc, xs)]
        res[lab] = (corr(xs, win), corr(xs, mar), corr(xs, cov))
        L.append(f"| {lab} | {res[lab][0]:+.4f} | {res[lab][1]:+.4f} | {res[lab][2]:+.4f} | {w}-{n - w} {100 * w / max(1, n):.1f}% | {cw}-{cn - cw} {100 * cw / max(1, cn):.1f}% | {corr(tot, win):+.4f} | {corr(tot, mar):+.4f} |")
    # ② 결장으로 오른 팀
    up = []   # (r, 홈이면 +1, 오른 폭)
    for r, sh, sa, fh, fa in sc:
        for s_, f_, sign in ((sh, fh, 1), (sa, fa, -1)):
            if s_[V] > f_[V]:
                up.append((r, sign, s_[V] - f_[V]))
    n_team = 2 * len(sc)
    L += ["", f"## ② 결장으로 커버리지 점수가 오른 팀: {len(up)} / {n_team}팀·경기({100 * len(up) / n_team:.1f}%)", "",
          "| 오른 폭 | 팀·경기 | 그 팀 승-패 | 승률 | 그 팀 스프레드 승-패 | 스프레드 적중 |", "|---|---|---|---|---|---|"]
    for lab, a, b in (("1~4", 1, 5), ("5~14", 5, 15), ("15 이상", 15, 999), ("전체", 1, 999)):
        x = [(r, s) for r, s, d in up if a <= d < b]
        w = sum(1 for r, s in x if r["res"] != 0 and (r["res"] > 0) == (s > 0)); n = sum(1 for r, s in x if r["res"] != 0)
        cw = sum(1 for r, s in x if r["res"] != r["mk"] and ((r["res"] - r["mk"]) > 0) == (s > 0)); cn = sum(1 for r, s in x if r["res"] != r["mk"])
        L.append(f"| {lab} | {len(x)} | {w}-{n - w} | {100 * w / max(1, n):.1f}% | {cw}-{cn - cw} | {100 * cw / max(1, cn):.1f}% |")
    dn = [(r, sign) for r, sh, sa, fh, fa in sc for s_, f_, sign in ((sh, fh, 1), (sa, fa, -1)) if f_[V] - s_[V] >= 15]
    w = sum(1 for r, s in dn if r["res"] != 0 and (r["res"] > 0) == (s > 0)); n = sum(1 for r, s in dn if r["res"] != 0)
    cw = sum(1 for r, s in dn if r["res"] != r["mk"] and ((r["res"] - r["mk"]) > 0) == (s > 0)); cn = sum(1 for r, s in dn if r["res"] != r["mk"])
    by = {}
    for r, s, d in up:
        if d >= 15:
            b = by.setdefault(r["season"], [0, 0, 0, 0])
            if r["res"] != 0:
                b[0 if (r["res"] > 0) == (s > 0) else 1] += 1
            if r["res"] != r["mk"]:
                b[2 if ((r["res"] - r["mk"]) > 0) == (s > 0) else 3] += 1
    L += ["", "15 이상 오른 팀 시즌별(그 팀 승-패 · 스프레드 승-패): " + " / ".join(f"{str(y)[2:]}: {b[0]}-{b[1]} · {b[2]}-{b[3]}" for y, b in sorted(by.items()))
          + f" · 스프레드 50% 미만 시즌 {sum(1 for b in by.values() if b[2] < b[3])}/{len(by)}"]
    L += ["", f"견줄 값 — 결장으로 15 이상 내려간 팀: {len(dn)}팀·경기 · 그 팀 {w}-{n - w}({100 * w / max(1, n):.1f}%) · 스프레드 {cw}-{cn - cw}({100 * cw / max(1, cn):.1f}%)"]
    cur, cap = res["현행(실제 뛴 선수)"], res["상한(결장으로는 못 오름)"]
    ok = cap[0] > cur[0] and cap[2] >= cur[2]
    L += ["", "## ③ 읽는 기준 대조", "",
          f"- 승패 상관: 현행 {cur[0]:+.4f} → 상한 {cap[0]:+.4f}({cap[0] - cur[0]:+.4f}) · 커버 상관: 현행 {cur[2]:+.4f} → 상한 {cap[2]:+.4f}({cap[2] - cur[2]:+.4f})",
          f"- 기준(승패 상관 ↑ & 커버 상관 낮아지지 않음): **{'충족' if ok else '미충족'}**"]
    out = os.path.join(N.DATA, f"cov_cap_lab_{dt.date.today()}.md")
    with io.open(out + ".tmp", "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(L) + "\n")
    os.replace(out + ".tmp", out)
    print("\n".join(L)); print("→", out)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
