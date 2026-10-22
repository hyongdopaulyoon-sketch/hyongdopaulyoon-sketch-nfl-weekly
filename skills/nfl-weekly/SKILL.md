---
name: nfl-weekly
description: >
  NFL 주간 ML(이길 팀) 파이프라인(Downloads/NFL) 운용 — 수집(weekly.py), 일요일 아침 최종 리프레시,
  claude.ai 발행 세션 전달문 만들기, 발행문 검사·기록(check_nfl.py --record),
  화요일 채점(weekly.py --grade). Paul 이 「NFL 수집」「NFL 리프레시」「NFL 전달문」「NFL 발행문 검사」
  「NFL 채점」「/nfl-weekly」라고 하거나 NFL 발행문을 붙여넣으면 쓴다.
---

# NFL 주간 운용 (Downloads/NFL)

정본 기록: `scripts/pending_rules.md`(규칙·개정) · `data/picks.csv`(픽 정본) · 메모리 `nfl-weekly-system.md`.
**지어내지 않는다** — 숫자는 다이제스트·스크립트 출력·웹 검색 결과 그대로. 모델(EPA)은 베팅 신호가 아니다(N0).

## 1. 수집 / 리프레시
```
cd C:\Users\PC\Downloads\NFL\scripts
python weekly.py --week N            # 수요일 초판 (sources→ratings→slate→injuries→model→digest + suggest·wind·angles·predictions·board·transmittal)
python weekly.py --week N --refresh  # 일요일 아침 최종판 · 목/월 경기는 그날 한 번 더(바람 언더 판정은 경기 당일 판만)
```
- 산출: `data/2026-wNN/DIGEST.md`(+ DIGEST-MMDD-HHMM 스냅샷) · games/injuries/model/line_history.csv.
- 출력 끝 확인: `suggest`(모델 페이퍼) · `wind`(오늘 경기 예보 풍속·기록 수) · `angles`(A1/A2) · `predictions record` · 보드 · 전달문(Drive). **티저는 2026-10-10 폐지**(weekly 가 부르지 않음, 기록만 남음).
- 다이제스트 머리 「📋 수집 점검」 표에 ⚠️ 가 있으면 발행 전에 리프레시 또는 웹 확인(10/10). 경기 절엔 🆕 직전 판 변동 · 🤝 맞대결 · 🏟️ 팀 비교(순위·흐름) · 🦵 키커 · 🧑‍⚖️ 심판 블록(값만 — context_blocks.py).
- 수집 뒤 `data/` 변경을 커밋(「N주차 다이제스트 MM/DD HH:MM판」).

## 2. 발행 세션 전달문 (발행 세션이 Drive 에서 직접 읽는다 — Paul 이 붙이지 않는다)
- **⛔ 전달문·다이제스트 파일을 Paul 에게 첨부(SendUserFile)·전송·「다운로드해 붙여 넣으라」고 안내하지 않는다(10/10 Paul 「아직 전달문 다운로드하라고 하는데?」).** 알림은 「NFL Drive 갱신됨 · MM-DD HH:MM판 · 남은 N경기 → 발행 세션에 'NFL 발행'」 한 줄만. 시간대별로 나눠 보낼 필요 없음(전달문은 아직 시작 안 한 경기만 담는다). 발행 세션이 Drive 를 못 읽을 때만 Paul 요청으로 전문을 채팅에 쓴다(파일 아님).
- 발행 세션 정본은 계정 스킬 nfl-weekly-publish(10/10 3판: 답은 채팅 본문·필수 줄 6개(맞대결·팀 비교·QB 비교·선수 비교·키커·심판)·ML 판단 허용·티저 폐지). 스킬을 바꾸면 `skills/nfl-weekly-publish.zip` 을 다시 묶고 **Paul 에게 재업로드 요청**(Paul 몫).
- 전달문 = 머리(「발행 — NFL N주차 {요일} {경기들} (다이제스트 MM/DD HH:MM판)」) + 확인할 것(최종 비활성 명단 시각·라인 이동·NWS 바람) + 다이제스트 해당 경기 절 전문(코드 블록). 전 경기면 DIGEST.md 전문.
- Paul 은 NFL 초보 — 전달문·설명 모두 초등학생 수준으로.
- **자동 전달문(10/4~)**: weekly.py 끝에 `transmittal.py --week N` 이 돈다 → `data/2026-wNN/전달문-MMDD-HHMM.md` + `~/My Drive/NFL/NFL_전달문_최신.md`(남은 경기만) · `DIGEST_2026-wNN.md`. 발행 세션은 Drive 커넥터로 읽으니 Paul 에게 파일을 보낼 필요 없다 — 「Drive 갱신됨, 발행 세션에 'NFL 발행'」이라고만 알린다. 리프레시 없이 전달문만 다시: `python scripts/transmittal.py --week N`.

## 3. 발행문 검사·기록
```
python scripts/check_nfl.py --week N --file <발행문.md> --record
```
- 검사: 시장 숫자 = 다이제스트 · 판단/방향 줄 형식 · 방향 라인 = 시장 · 판단 쪽 = 방향 쪽 · 관심 ≤3 · 캐시아웃 권유 금지 · **필수 줄 6개(10/10) · 티저 낱말 금지 · ML 판단(「관심 · ML · DAL ML -520」, 팀 = 예측 승자)**. 「커버리지」는 부분 발행이면 정상.
- 기록: 관심·소액 = `…:J`(관심(발행)) · 방향 = `…:D`(방향(발행)) — 모델 페이퍼 행은 덮어쓰지 않는다.
- 10/5~ 검사 추가: 「- 새 정보:」 줄(--record → 「새 정보(관찰)」 :N, 사전 등록 55b93ea) · 예측 ±5%p 상한·쉬운 라벨 · 「- 결론: ①②③」 · 귀속 대조(기준판 = 발행문 판 시각 스냅샷, 옛 발행문은 `--digest data/2026-wNN/DIGEST-MMDD-HHMM.md` 지정).
- 발행문 내용도 다이제스트·스냅 데이터와 대조(예: 「새 결장」이 스냅 기록 없는 선수면 지적 — 10/1 Porter 0경기).

## 4. 실베팅 기록 (Paul 이 「시장·라인·배당·금액」을 알려 줄 때)
```
python scripts/picks.py place --week N --id <game_id>:spread|total|ml --side "PIT -2.5" --line -2.5 --odds -108 --stake 0.5 --note "…"   # ML 은 --id …:ml --side "PIT ML" --odds -130
```
- Polymarket 등 센트 가격은 미국식으로 환산(52c → −108 · 73c → −270). 배당을 모르면 note 에 「배당 미확인」+ 확인되면 정정.
- `--stake` = 유닛(0.5 등) — 채점 손익이 그만큼 곱해진다. 기록 뒤 `python scripts/tracker_xlsx.py`.

## 4-1. 결과 예측(2026-10-04 Paul 「결과 예측이 먼저」)
- `python scripts/predictions.py record --week N`(weekly 자동) — 시장(DK 무비그·내재 점수)·우리 드라이브 모델 예측, 킥오프 지난 경기 동결. 발행문 「- 예측:」 줄은 check_nfl --record 가 src=발행으로 적는다.
- `python scripts/predictions.py report` — 승자 적중·점수 차/총점 오차·스프레드/총점 쪽 적중을 시장·모델·발행 나란히.
- 보드: `python scripts/nfl_board.py --week N` → board/board-wNN.html → 같은 URL 로 Artifact 게시(board/links.csv), 게시 뒤 unwatch.

## 5. 화요일 채점
```
python weekly.py --grade N
```
- 결과·W/L·유닛·**CLV(픽 라인 − 마감 라인, + = 우리가 더 좋은 숫자)** 를 채운다. stats·추적기에 평균 CLV — **실력 판정은 승패가 아니라 CLV**(수십 건이면 보인다).
- 바람 언더 행은 실측 wind 꼬리표가 붙는다.

## 6. 하지 말 것 / 함정
- 모델 엣지·「📊 포지션 매치업」 표·패스 매치업(압박·CPOE·FTN)을 **등급이나 관심 근거로 쓰지 않는다** — 2006~2025 백테스트(situations.py·backtest_features.py)에서 QB 교체·주전 결장·압박·CPOE 전부 시장이 반영(0/6 통과). 서술·방향 저울질 재료로만.
- 판정 문턱·상수 개정은 화요일(N8) — Paul 지시면 예외로 pending_rules 에 「N8 예외」 한 줄.
- ESPN API 는 UA 헤더를 붙이면 403 — urllib 기본 UA. 구글 검색은 CAPTCHA — 우회 금지(빙 뉴스 사용).
- 검증 구간(2023~25)은 특징 백테스트에서 미개봉·바람 가설에도 미개봉 — 한 번만 쓸 수 있는 카드.
- 파일 쓰기는 read → ast.parse → .tmp → os.replace. 패치는 heredoc 말고 Write 로 .py.
- 에이전트 팬아웃 금지 — 로컬 스크립트 단독.
