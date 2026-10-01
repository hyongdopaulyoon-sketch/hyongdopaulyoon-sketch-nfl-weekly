# NFL 주간 스프레드·총점 시스템 (2026 시즌 4주차부터)

MLB 데일리 파이프라인의 축소판. 무료 데이터(ESPN 공개 API · nflverse)만 쓴다.
운용 규칙 N0~N8 은 매 주 `data/2026-wNN/DIGEST.md` 머리에 실린다(정본).

## 먼저 알아야 할 것 — 모델은 베팅 신호가 아니다(N0)
2024·2025 정규시즌 약 450경기 백테스트(`scripts/backtest.py`): EPA 레이팅 모델의 마감 라인 대비 오차가 시장보다 크고(MAE 11.3 vs 10.1),
모델 방향으로 걸었을 때 ATS ≈ 45%, 모델−시장 괴리 3.5점 이상 구간은 시장이 맞았다(2025 15-33). 단순 각도 19개(`scripts/angles.py`, 2015~25 2,895경기)도 전부 50~54%.
그래서 이 시스템은 **정보(라인·QB·부상·휴식·날씨·레이팅)를 한 장에 모으고, 페이퍼(모델)와 실베팅(Paul)을 따로 기록해 무엇이 시장을 이기는지 재는 도구**다.

**시장은 공개 정보를 이미 반영한다(2026-10-01 상황별 백테스트, `scripts/situations.py` — 기준 사전 등록 커밋 1b09edd)**:
2006~2025 정규시즌 5,199경기. 백업 QB 1·2·3번째 선발(n 475·356·266) ATS 49.9·47.5·50.8% · 주전 복귀 50.7% · 총점도 49~52% — 전부 우연 범위.
주전(직전 3경기 스냅 60%+) 결장 3명+ 팀 46.2%(n 316) · 5명+ 50.0% · 결장 차 3명+ 47.9% · OL 2명+ 45.2% · CB 2명+ 42.9%(n 35) · WR 2명+ 50.0% — 결장 팀이 약간 덜 커버하는 방향이지만 전부 우연 범위(|z|<1.4).
목요일 원정 48.9%. 팀 단위 지속성(전반기→후반기 ATS 상관 +0.04, 팀간 편차 = 우연 기대치)도 없음.
→ QB 교체·부상 결장 같은 **확인된 공개 사실만으로는 시장을 못 이긴다** — 발행 지침의 「소액 관심(시장 반영 가능성 큼)」·「관심 = 라인이 아직 덜 반영」 조건의 근거.
유일한 약한 신호: **실외 바람 15mph+ 언더 55.3%(240-194, z +2.21, 20시즌 중 11시즌 52.4%↑)** — 전·후반 10년 55.8%/54.7%로 같은 방향이지만 20mph+ 는 54.1%로 더 세지지 않고, games.csv 바람은 실측값(베팅 시점 예보 아님)이라 과대평가 가능 → 전향 페이퍼 관찰 후보(Paul 결정).
큰 라인 이동(오픈→마감)은 무료 오픈 라인 자료가 없어 미측정 — `line_history.csv` 4주차부터 전향 적립.

## 발행 방식(2026-09-29 결정)
로컬 다이제스트 → **claude.ai NFL 발행 세션**(지침: `복붙용_NFL_발행_인스트럭션_2026-10-01.md`)이 경기별 발행문·판단(패스/소액 관심/관심)·방향(스프레드·총점 쪽, 패스여도 필수)을 씀 → 발행문을 로컬에 붙여넣으면 `python scripts/check_nfl.py --week N --file 발행문.md --record` 로 숫자·형식 검사 + 판단 페이퍼 기록 → 실제 베팅은 「경기 · 시장 · 라인 · 배당」 한 줄로 `picks.py place`.

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
- `scripts/tracker_xlsx.py` — 보기용 추적기 `data/NFL_픽_추적기.xlsx`(픽로그·적중률·주별). **정본은 picks.csv** — xlsx 는 채점 때마다 다시 만들어지니 손으로 고치지 말 것.
- `scripts/weekly.py` — 위 절차 묶음(--grade 뒤 추적기 xlsx 자동 갱신). `scripts/backtest.py`·`scripts/angles.py` — 캘리브레이션·각도 백테스트.
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
