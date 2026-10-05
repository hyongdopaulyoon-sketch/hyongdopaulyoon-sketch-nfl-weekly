"""발행 전달문 자동 생성 + Google Drive 동기화 사본(2026-10-04 Paul 「전달문을 계속 다운받아야 해?」).
  python transmittal.py --week 4
아직 시작 안 한 경기만 킥오프 순으로 담는다. data/2026-wNN/전달문-MMDD-HHMM.md 로 남기고,
~/My Drive/NFL/ 에 「NFL_전달문_최신.md」(고정 이름 — 발행 세션이 Drive 커넥터로 이 파일을 읽는다)와 「DIGEST_2026-wNN.md」 사본을 둔다.
Drive 폴더가 없는 PC 에서는 조용히 건너뛴다(MLB mlb_pull 과 같은 방식)."""
import argparse, os, re, shutil, sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nfl_pull as N   # noqa: E402

DRIVE = os.path.expanduser("~/My Drive/NFL")


def build(week):
    D = N.week_dir(week)
    txt = open(os.path.join(D, "DIGEST.md"), encoding="utf-8").read()
    stamp = txt.split("\n", 1)[0].split("(생성 ")[1].split(" PT")[0]
    now = datetime.now(timezone.utc)
    games = {f'{g["away"]}@{g["home"]}': g for g in N.rd(os.path.join(D, "games.csv"))}
    keep = []
    for g, h, b in re.findall(r"(?ms)^## ([A-Z]{2,3}@[A-Z]{2,3})  ([^\n]*)\n(.*?)(?=^## |\Z)", txt):
        gg = games.get(g)
        if gg and datetime.strptime(gg["kickoff_utc"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc) > now:
            keep.append((gg["kickoff_utc"], g, h, b))
    keep.sort()
    picks = N.rd(os.path.join(N.DATA, "picks.csv"))
    names = [k[1] for k in keep]
    wind = [r for r in picks if r["grade"] == "바람 언더(관찰)" and r["week"] == str(week) and r["game"] in names]
    bets = [r for r in picks if r.get("status") == "placed" and r["week"] == str(week) and r["game"] in names]
    tz = [r for r in picks if r["grade"] == "티저 다리(관찰)" and r["week"] == str(week) and r["game"] in names]
    sched = " · ".join(f'{g} {games[g]["kickoff_pt"]} PT({games[g]["kickoff_et"].split(" ")[0]})' for g in names)
    out = [f"NFL 발행 — {week}주차 아직 시작 안 한 {len(keep)}경기 · 다이제스트 {stamp} PT판 · 전달문 생성 {datetime.now():%m-%d %H:%M} PT", "",
           "※ nfl-weekly-publish 스킬대로: 경기마다 둘째 줄 「- 예측: 승자 팀 NN% · 점수 원정 x – 홈 y · 근거」(출발점 = 다이제스트 🔮 시장 예측, 새 사실 있으면 조정), 방향, 근거, 맨 아래 판단·굳이 하나만, 📘 ①~⑥.",
           f"※ 킥오프 순서: {sched} — 이미 시작한 경기는 건너뛴다.",
           "※ 웹 확인: 최종 비활성 명단(킥오프 90분 전) · 라인 이동 · 날씨 — 마지막 라인 뒤에 나온 사실이면 「- 새 정보:」 줄(발표 시각 PT 필수), 없으면 「- 새 정보: 없음」.",
           "※ ⚖️ 저울질 표는 값만 인용(점수 0 항목을 「유리/불리」로 쓰지 않음) · 예측은 시장 ±5%p 이내(QB 교체·라인 뒤 확정 결장만 예외) · 「- 결론: ①②③」.",
           "※ 바람 언더 관찰 경기: " + (" · ".join(f'{r["game"]} {r["side"]}({r["note"].split(" · ")[0]})' for r in wind) or "없음") + ".",
           "※ 티저 다리(검증 전략 — 다리 2개를 묶어야 함): " + (" · ".join(f'{r["game"]} {r["side"]}' for r in tz) or "없음") + ".",
           "※ 이 경기들에 걸린 Paul 실베팅: " + (" · ".join(f'{r["game"]} {r["side"]} {r["odds"]} {r.get("stake") or 1}u' for r in bets) or "없음") + ".", ""]
    for _k, g, h, b in keep:
        out += [f"## {g}  {h}", b.rstrip() + "\n"]
    body = "\n".join(out)
    p = os.path.join(D, f"전달문-{datetime.now():%m%d-%H%M}.md")
    open(p, "w", encoding="utf-8").write(body)
    print(f"전달문 {len(keep)}경기 → {os.path.relpath(p, N.ROOT) if hasattr(N, 'ROOT') else p}")
    if os.path.isdir(os.path.dirname(DRIVE)):
        try:
            os.makedirs(DRIVE, exist_ok=True)
            open(os.path.join(DRIVE, "NFL_전달문_최신.md"), "w", encoding="utf-8").write(body)
            shutil.copyfile(os.path.join(D, "DIGEST.md"), os.path.join(DRIVE, f"DIGEST_{N.SEASON}-w{week:02d}.md"))
            print(f"  → Drive 동기화: {DRIVE}\\NFL_전달문_최신.md · DIGEST_{N.SEASON}-w{week:02d}.md")
        except Exception as e:
            print(f"  (Drive 사본 실패: {type(e).__name__} — 로컬 전달문은 정상)")
    return p


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(); ap.add_argument("--week", type=int, required=True)
    build(ap.parse_args().week)
