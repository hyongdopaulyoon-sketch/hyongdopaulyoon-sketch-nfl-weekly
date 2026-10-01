"""주간 운용 진입점.
  python weekly.py                 현재 주차 전체(sources→digest) + picks suggest
  python weekly.py --week 5        지정 주차
  python weekly.py --grade 4       4주차 결과 받기 + 채점 + 성적
  python weekly.py --refresh       sources 강제 재수집(라인·부상·EPA 갱신) 후 전체
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(script, args):
    r = subprocess.run([sys.executable, os.path.join(HERE, script)] + args, cwd=HERE)
    if r.returncode:
        sys.exit(f"{script} 실패({r.returncode})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int)
    ap.add_argument("--grade", type=int, metavar="WEEK")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    if a.grade:
        run("nfl_pull.py", ["--week", str(a.grade), "--phase", "results"])
        run("picks.py", ["grade", "--week", str(a.grade)])
        run("picks.py", ["stats"])
        run("tracker_xlsx.py", [])          # 보기용 추적기 xlsx 재생성(정본은 picks.csv)
        return
    wk = ["--week", str(a.week)] if a.week else []
    run("nfl_pull.py", wk + (["--force"] if a.refresh else []))
    if a.week:
        w = str(a.week)
    else:
        import json, urllib.request
        j = json.load(urllib.request.urlopen("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard", timeout=20))
        w = str(j["week"]["number"])
    run("picks.py", ["suggest", "--week", w])
    run("picks.py", ["teaser", "--week", w])          # 웡 티저 다리 페이퍼(2026-10-01) — 실베팅 아님
    run("picks.py", ["wind", "--week", w])            # 바람 15mph+ 언더 페이퍼(2026-10-01) — 경기 당일 판만


if __name__ == "__main__":
    main()
