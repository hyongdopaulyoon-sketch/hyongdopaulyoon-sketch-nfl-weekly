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
        return
    wk = ["--week", str(a.week)] if a.week else []
    run("nfl_pull.py", wk + (["--force"] if a.refresh else []))
    if a.week:
        run("picks.py", ["suggest", "--week", str(a.week)])
    else:
        import json, urllib.request
        j = json.load(urllib.request.urlopen("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard", timeout=20))
        run("picks.py", ["suggest", "--week", str(j["week"]["number"])])


if __name__ == "__main__":
    main()
