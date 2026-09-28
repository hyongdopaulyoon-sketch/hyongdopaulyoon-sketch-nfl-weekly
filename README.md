# NFL 주간 스프레드·총점 시스템 (2026 시즌 4주차부터)

MLB 데일리 파이프라인의 축소판. 무료 데이터(ESPN 공개 API · nflverse)만 쓴다.
운용 규칙 N0~N8 은 매 주 `data/2026-wNN/DIGEST.md` 머리에 실린다(정본).

## 먼저 알아야 할 것 — 모델은 베팅 신호가 아니다(N0)
2024·2025 정규시즌 약 450경기 백테스트(`scripts/backtest.py`): EPA 레이팅 모델의 마감 라인 대비 오차가 시장보다 크고(MAE 11.3 vs 10.1),
모델 방향으로 걸었을 때 ATS ≈ 45%, 모델−시장 괴리 3.5점 이상 구간은 시장이 맞았다(2025 15-33). 단순 각도 19개(`scripts/angles.py`, 2015~25 2,895경기)도 전부 50~54%.
그래서 이 시스템은 **정보(라인·QB·부상·휴식·날씨·레이팅)를 한 장에 모으고, 페이퍼(모델)와 실베팅(Paul)을 따로 기록해 무엇이 시장을 이기는지 재는 도구**다.

## 주간 절차 (PT 기준)
| 때 | 명령 | 하는 일 |
|---|---|---|
| 화 | `python scripts/weekly.py --grade 3` | 지난 주 결과 받기 → 픽 채점 → 성적(`picks.py stats`, placed·suggested 따로) |
| 수 | `python scripts/weekly.py --week 4` | 이번 주 수집(라인·부상·EPA·날씨) → 모델 → DIGEST → 관찰·참고를 `data/picks.csv` 에 `suggested`(페이퍼)로 적재 |
| 목 저녁 | (목요일 경기 있으면) `python scripts/weekly.py --week 4 --refresh` | 킥오프 전 라인·부상 최신화(라인 이동은 `line_history.csv` 에 쌓인다) |
| 토 저녁 / 일 아침 | `python scripts/weekly.py --week 4 --refresh` | **일요일 아침 리프레시가 정본**(부상 보고 최종·QB 확정) |
| 베팅 뒤 | `python scripts/picks.py place --week 4 --id 2026_04_NE_BUF:spread --line 7 --odds -110` | 실제 베팅한 행만 `placed`(모델 제안이 아닌 경기도 id 형식 `game_id:spread|total` 로 가능) |

## 파일
- `scripts/nfl_pull.py` — sources(캐시) → ratings(`data/ratings.csv`) → slate(`games.csv` + `line_history.csv`) → injuries(`injuries.csv`) → model(`model.csv`) → digest(`DIGEST.md` + 시각 스냅샷). `--phase results` 는 최종 점수.
- `scripts/picks.py` — suggest / place / grade / stats. 픽로그 `data/picks.csv`(한 행 = 경기 × 시장).
- `scripts/weekly.py` — 위 절차 묶음. `scripts/backtest.py`·`scripts/angles.py` — 캘리브레이션·각도 백테스트.
- `scripts/pending_rules.md` — 규칙 개정 기록(N8: 화요일에만).
- `data/cache/` — nflverse 원본(수십 MB, git 제외). `data/2026-wNN/` — 주간 산출물(git 포함).

## 모델(N1 — 페이퍼용)
EPA/플레이 팀 레이팅: 2026 주차 감쇠 0.9 가중 + 2025 시즌 사전확률(600플레이 환산, 30% 회귀).
홈 기대 마진 = 62 × [(홈 공격 + 원정 수비허용) − (원정 공격 + 홈 수비허용)] + 홈 1.5점(중립 구장 0) − QB 벌점(백업 선발·QB Out/Doubtful 4.5점).
총점 = 2 × 리그 평균 득점 + 62 × (네 항 합).

## 등급(N2)
| 시장 | 시장 동조 | 참고 | 관찰(큰 괴리 — 페이퍼) |
|---|---|---|---|
| 스프레드 | \|모델−시장\| < 2.0점 | 2.0~3.5 | ≥ 3.5 |
| 총점 | < 3.0점 | 3.0~5.0 | ≥ 5.0 |

「후보」 등급은 없다. ※ = 한 팀이라도 2026 플레이 150 미만. 손익분기 52.4%(−110).
