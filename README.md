# NFL 주간 스프레드·총점 시스템 (2026 시즌 4주차부터)

MLB 데일리 파이프라인의 축소판. 무료 데이터(ESPN 공개 API · nflverse)만 쓰고, 점수는 「모델 − 시장」 하나다.
운용 규칙 N1~N8 은 매 주 `data/2026-wNN/DIGEST.md` 머리에 실린다(정본).

## 주간 절차 (PT 기준)
| 때 | 명령 | 하는 일 |
|---|---|---|
| 화 | `python scripts/weekly.py --grade 3` | 지난 주 결과 받기 → 픽 채점 → 성적(`picks.py stats`) |
| 수 | `python scripts/weekly.py --week 4` | 이번 주 수집(라인·부상·EPA·날씨) → 모델 → DIGEST → 후보·참고를 `data/picks.csv` 에 `suggested` 로 적재 |
| 목 저녁 | (목요일 경기 있으면) `python scripts/weekly.py --week 4 --refresh` | 킥오프 전 라인·부상 최신화 |
| 토 저녁 / 일 아침 | `python scripts/weekly.py --week 4 --refresh` | **일요일 아침 리프레시가 정본**(부상 보고 최종·QB 확정) |
| 베팅 뒤 | `python scripts/picks.py place --week 4 --id 2026_04_NE_BUF:spread --line 7 --odds -110` | 실제 베팅한 행만 `placed` — 성적은 placed 만 센다 |

`python scripts/picks.py place --week 4 --all-candidates` 는 후보 등급 전부를 placed 로 바꾼다.

## 파일
- `scripts/nfl_pull.py` — 단계: sources(캐시) → ratings(EPA 레이팅, `data/ratings.csv`) → slate(`games.csv`) → injuries(`injuries.csv`) → model(`model.csv`) → digest(`DIGEST.md` + 시각 스냅샷). `--phase results` 는 최종 점수.
- `scripts/picks.py` — suggest / place / grade / stats. 픽로그 `data/picks.csv`(한 행 = 경기 × 시장).
- `scripts/weekly.py` — 위 절차 묶음.
- `scripts/pending_rules.md` — 규칙 개정 기록(N8: 화요일에만).
- `data/cache/` — nflverse 원본(수십 MB, git 제외). `data/2026-wNN/` — 주간 산출물(git 포함).

## 모델(N1)
EPA/플레이 팀 레이팅: 2026 주차 감쇠 0.9 가중 + 2025 시즌 사전확률(600플레이 환산, 30% 회귀).
홈 기대 마진 = 62 × [(홈 공격 + 원정 수비허용) − (원정 공격 + 홈 수비허용)] + 홈 1.5점(중립 구장 0) − QB 벌점(백업 선발·QB Out/Doubtful 4.5점).
총점 = 2 × 리그 평균 득점 + 62 × (네 항 합). 커버 확률 = Φ(|엣지| / 13.0), 총점은 / 10.5.

## 판정(N2·N3)
| 시장 | 시장 동조(비집행) | 참고 | 후보 |
|---|---|---|---|
| 스프레드 | \|엣지\| < 2.0점 | 2.0~3.5 | ≥ 3.5(커버 확률 ≈ 60.6%) |
| 총점 | < 3.0점 | 3.0~5.0 | ≥ 5.0 |

한 팀이라도 2026 플레이 150 미만이면 ※ — 후보 대신 참고.

## 정직한 기대치
NFL 스프레드 시장은 가장 날카롭다. 손익분기 52.4%. 첫 시즌 목표는 이기기보다 **기록·검증**(남은 약 240경기). 문턱·상수는 주 1회(화요일) 결과를 보고만 바꾼다.
