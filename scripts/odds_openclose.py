"""ESPN 코어 odds 개장·마감(스프레드·총점·ML) 역사 수집 — 2026-10-17 Paul 「시장 미반영·엣지 찾기」(가격·타이밍 재료).
  python scripts/odds_openclose.py --seasons 2023 2024 2025   → data/cache/odds_openclose.csv (정규시즌, 첫 제공자)
NBA 와 같은 엔드포인트: sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{e}/competitions/{c}/odds (open/close 는 2023~)."""
import argparse, csv, json, os, sys, time, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); CACHE = os.path.join(os.path.dirname(HERE), "data", "cache")
SB = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={s}&seasontype=2&week={w}"
OD = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{e}/competitions/{c}/odds"
HDR = ["season", "week", "espn_id", "date", "away", "home", "provider", "open_spread_home", "close_spread_home", "open_total", "close_total",
       "open_ml_away", "open_ml_home", "close_ml_away", "close_ml_home", "away_score", "home_score"]


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            if i == tries - 1:
                print("  fail", url[-60:], type(e).__name__); return None
            time.sleep(1.5)


def am(x):
    """open/close 안의 moneyLine/pointSpread 값 → 미국식 문자열."""
    if not isinstance(x, dict):
        return ""
    return str(x.get("american") or x.get("alternateDisplayValue") or "")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--seasons", nargs="+", type=int, default=[2023, 2024, 2025]); ap.add_argument("--weeks", type=int, default=18)
    a = ap.parse_args()
    out = os.path.join(CACHE, "odds_openclose.csv")
    rows = {}
    if os.path.exists(out):
        for r in csv.DictReader(open(out, encoding="utf-8-sig")):
            rows[r["espn_id"]] = r
    n = 0
    for s in a.seasons:
        for w in range(1, a.weeks + 1):
            sb = get(SB.format(s=s, w=w))
            for ev in (sb or {}).get("events", []):
                eid = ev["id"]
                if eid in rows and rows[eid].get("close_ml_home"):
                    continue
                comp = ev["competitions"][0]; cid = comp["id"]
                tm = {c["homeAway"]: c for c in comp["competitors"]}
                od = get(OD.format(e=eid, c=cid)); it = ((od or {}).get("items") or [None])[0]
                if not it:
                    continue
                ho, ao = it.get("homeTeamOdds") or {}, it.get("awayTeamOdds") or {}
                oc, cc = it.get("open") or {}, it.get("close") or {}
                rows[eid] = dict(season=s, week=w, espn_id=eid, date=ev["date"], away=tm["away"]["team"]["abbreviation"], home=tm["home"]["team"]["abbreviation"],
                                 provider=(it.get("provider") or {}).get("name", ""),
                                 open_spread_home=am((ho.get("open") or {}).get("pointSpread")), close_spread_home=am((ho.get("close") or {}).get("pointSpread")),
                                 open_total=am((oc.get("total") or {}) if isinstance(oc.get("total"), dict) else {}) or oc.get("overUnder", "") if isinstance(oc, dict) else "",
                                 close_total=am((cc.get("total") or {}) if isinstance(cc.get("total"), dict) else {}) or cc.get("overUnder", "") if isinstance(cc, dict) else "",
                                 open_ml_away=am((ao.get("open") or {}).get("moneyLine")), open_ml_home=am((ho.get("open") or {}).get("moneyLine")),
                                 close_ml_away=am((ao.get("close") or {}).get("moneyLine")), close_ml_home=am((ho.get("close") or {}).get("moneyLine")),
                                 away_score=tm["away"].get("score", ""), home_score=tm["home"].get("score", ""))
                n += 1
                time.sleep(0.25)
            print(f"  {s} w{w}: 누적 {len(rows)}")
            with open(out, "w", newline="", encoding="utf-8-sig") as fh:
                wr = csv.DictWriter(fh, fieldnames=HDR); wr.writeheader(); wr.writerows(rows.values())
    print(f"wrote {out} ({len(rows)} rows, new {n})")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
