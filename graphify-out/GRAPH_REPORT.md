# Graph Report - graphify_src  (2026-10-21)

## Corpus Check
- 101 files · ~131,083 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 631 nodes · 1571 edges · 29 communities
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 84 edges (avg confidence: 0.83)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- 5주차 발행·스킬 판 이력·감사
- 6주차 발행·10판 ML 각도
- picks 채점·CLV·페이퍼 관찰
- 특징 백테스트 F1~F6·개장/마감
- 운용 규칙 N0·N8·주간 절차
- NFL 보드(nfl_board.py)
- 스탯 비교·격차 등급(stat_compare)
- 결과 예측·드라이브 모델(predictions)
- 다이제스트 머리·N2 개정·최근 3시즌 탐색
- 맥락 블록(맞대결·키커·심판)
- 선수 고급 기록·OL 연속성·IR
- 부상·비활성 명단·레이팅 수집
- 발행문 검사기(check_nfl)
- 발행 형식·선수/수비 표
- 선수 기반 득점 모델
- 수집 파이프라인 단계(nfl_pull)
- 4주차 발행·방향 동전·N1/N4/N9
- QB 수준·선발 QB 정본
- 패스 매치업·실제 수치(nfl_pull)
- 다이제스트 렌더·관찰 각도 줄
- 4주차 전달문·포지션 매치업
- 새 정보·±5%p 상한·별점
- 1~3주차 소급 백테스트
- 키커 엣지 착시·10/17 탐색
- 가격 블록·무비그·Polymarket
- 시장 반영 백테스트 근거
- ESPN 스코어보드·라인 파싱
- DAL@GB·가격 출처·기준판 차이
- MLB 교훈·값만 원칙

## God Nodes (most connected - your core abstractions)
1. `전달문(발행 세션 입력)` - 46 edges
2. `nfl-weekly-publish 스킬(발행 세션 · 10판 ML 전용)` - 35 edges
3. `📊 시즌 성적 블록` - 28 edges
4. `BUF@LA (5주차 MNF)` - 24 edges
5. `2026 NFL 5주차` - 22 edges
6. `📌 결론 재료(자동)` - 19 edges
7. `ph_digest()` - 18 edges
8. `nfl-weekly 스킬(로컬 주간 운용)` - 18 edges
9. `LAC@KC (6주차)` - 18 edges
10. `전달문 10/14 21:18 (6주차 · 남은 14경기 · 10-14 21:14판)` - 18 edges

## Surprising Connections (you probably didn't know these)
- `ESPN API UA 헤더 403 함정` --conceptually_related_to--> `fetch()`  [INFERRED]
  skills/nfl-weekly_SKILL.md → scripts/nfl_pull.py
- `NFL 보드(nfl_board.py → Artifact 게시·unwatch)` --implements--> `main()`  [INFERRED]
  skills/nfl-weekly_SKILL.md → scripts/nfl_board.py
- `무료 데이터(ESPN 공개 API·nflverse)` --implements--> `ph_sources()`  [INFERRED]
  README.md → scripts/nfl_pull.py
- `화요일 채점(weekly.py --grade)` --implements--> `grade()`  [INFERRED]
  skills/nfl-weekly_SKILL.md → scripts/predictions.py
- `전달문 Drive 자동 갱신(NFL_전달문_최신.md)` --implements--> `build()`  [INFERRED]
  skills/nfl-weekly_SKILL.md → scripts/transmittal.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **각도 페이퍼 관찰 A1~A10** — nfl_rules_a1_road_fav7_home_dog, nfl_rules_a2_drive_edge_dog_fade, nfl_rules_a3_injury_line_move, nfl_rules_a4_lastyear_playoff_dog, nfl_rules_a5_third_down_luck_opponent, nfl_rules_a6_key_number_reverse, nfl_rules_a7_home_dog7_ats, nfl_rules_a8_close_game_750_team, nfl_rules_a9_december_outdoor_over, nfl_rules_a10_sack_rate_opponent [EXTRACTED 1.00]
- **시장 반영 확인 백테스트 묶음** — nfl_concept_situations_backtest, nfl_concept_feature_backtest_f1_f6, nfl_concept_player_model_backtest, nfl_concept_explore_recent, nfl_concept_edge_search_1017 [INFERRED 0.85]
- **다이제스트 경기 절 서술 블록** — nfl_concept_stat_compare_words, nfl_concept_player_table, nfl_concept_defense_player_table, nfl_concept_context_blocks, nfl_concept_conclusion_material, nfl_concept_inactives_list, nfl_concept_price_block [INFERRED 0.85]
- **수집→전달문→발행→검사·기록→채점 흐름** — nfl_concept_weekly_procedure, nfl_concept_transmittal_drive, skills_nfl_weekly_publish_skill, nfl_concept_publish_check_record, nfl_concept_tuesday_grading [INFERRED 0.85]
- **6주차 ML 각도 소액 관심 발행** — nfl_game_2026_w06_no_nyg, nfl_game_2026_w06_pit_tb, nfl_game_2026_w06_buf_lv, nfl_concept_ml_angle_small_interest [EXTRACTED 1.00]

## Communities (29 total, 0 thin omitted)

### Community 0 - "5주차 발행·스킬 판 이력·감사"
Cohesion: 0.13
Nodes (54): MLB 보드 세션 감사(🔧 감사 줄), 📘 쉽게 말하면(6판에서 삭제), nfl-weekly-publish 스킬 판 이력(3~10판), Q·Doubtful ★주전 QB·OL 이 판 뒤 결장 확정되면 새 정보, 스킬 6판 최종 형식(필수 줄 6개), 스킬 7판 방향 줄 삭제·자동 유도, 스킬 8판 선수 표(🧑‍🤝‍🧑) 필수, 웡 티저 다리 페이퍼 관찰 (+46 more)

### Community 1 - "6주차 발행·10판 ML 각도"
Cohesion: 0.22
Nodes (48): 📌 결론 재료(자동), 🌍 국제·중립 경기 줄(토요일 발행), 판단 줄 세 토막 형식(「소액 관심 · ML · NYG ML -112」), ML 각도 같은 쪽이면 소액 관심 · ML, 📊 시즌 성적 블록, 스킬 10판 ML 전용, 스킬 9판 예측 점수는 라인과 0.5점+ 다르게·📌 결론 재료, ARI@LA (6주차) (+40 more)

### Community 2 - "picks 채점·CLV·페이퍼 관찰"
Cohesion: 0.11
Nodes (41): CLV(마감 라인 대비 점·가격 CLV), 화요일 채점(weekly.py --grade), 바람 15mph+ 언더 페이퍼 관찰, A4 작년 플옵팀 ML 언더독 1~8주, N7 기록(10판) — predictions·picks 페이퍼, angles(), _closing(), _closing_dk() (+33 more)

### Community 3 - "특징 백테스트 F1~F6·개장/마감"
Cohesion: 0.09
Nodes (37): 개장→마감 구조적 타이밍, ats_side(), backup_first(), build(), cpoe_asof(), home_margin(), main(), pressure_asof() (+29 more)

### Community 4 - "운용 규칙 N0·N8·주간 절차"
Cohesion: 0.08
Nodes (27): 7주차 다이제스트 머리(10-21 21:34판), ESPN API UA 헤더 403 함정, 파일 쓰기 read→ast→.tmp→os.replace, 전달문 Drive 자동 갱신(NFL_전달문_최신.md), 주간 절차(수 초판·일 아침 최종 리프레시·화 채점), N0 모델은 베팅 신호가 아니다, N8 판정 개정은 주 1회(화요일), README — NFL 주간 시스템 (+19 more)

### Community 5 - "NFL 보드(nfl_board.py)"
Cohesion: 0.09
Nodes (33): NFL 보드(nfl_board.py → Artifact 게시·unwatch), games_fallback(), hub_html(), hub_url(), logo_uri(), main(), mark_teams(), md_html() (+25 more)

### Community 6 - "스탯 비교·격차 등급(stat_compare)"
Cohesion: 0.10
Nodes (32): 격차(서술 전용) 열·실측 퍼센트, 작년(2025) 스탯 열, f(), main(), pimp(), 📊 스탯 비교 「격차」 등급별 실측 — 2026-10-17 Paul 「서술 옆에 퍼센트」. 항목마다 그 주 전까지(as-of) 시즌 값으로…, val(), build() (+24 more)

### Community 7 - "결과 예측·드라이브 모델(predictions)"
Cohesion: 0.11
Nodes (29): 드라이브 기반 예상 득점 모델, 5주차 BUF@LA 발행(10/12 12:12), add_pub(), all_rows(), backfill(), _cache_games(), compute(), _drive_model() (+21 more)

### Community 8 - "다이제스트 머리·N2 개정·최근 3시즌 탐색"
Cohesion: 0.10
Nodes (27): 5주차 다이제스트 머리(10-12 15:48판), 6주차 다이제스트 머리(10-19 17:19판), AS-OF 누수 차단, 최근 3시즌 탐색 후보 0/38, 모델 관찰(큰 괴리) 페이퍼 이상치 60픽 판정, A1 원정 −7+ 페이버릿 → 홈 언더독(페이퍼, 폐지), A2 드라이브 득점 우위 언더독 반대(페이퍼, 폐지), N2(구판) 등급 3종 시장 동조/참고/관찰 (+19 more)

### Community 9 - "맥락 블록(맞대결·키커·심판)"
Cohesion: 0.16
Nodes (27): 맥락 블록(🤝 맞대결·🏟️ 팀 비교·🦵 키커·🧑‍⚖️ 심판), _ats(), changes_line(), _cnt(), collection_check(), _depth_kicker(), _f(), games() (+19 more)

### Community 10 - "선수 고급 기록·OL 연속성·IR"
Cohesion: 0.13
Nodes (23): IR 결장 보강(weekly_rosters), OL 연속성 행, _corr(), _find(), load_stability(), ol_continuity(), 리시버·러셔 고급 기록(2026-10-10 Paul 「넣어」 — nflverse 미러: PFR advstats rec/rush + NGS…, → {"rec": {name: dict}, "rush": {name: dict}} 2026 정규시즌 누적(PFR 주별 합 + NGS week… (+15 more)

### Community 11 - "부상·비활성 명단·레이팅 수집"
Cohesion: 0.13
Nodes (24): 🏥 결장 명단(ESPN 공식 비활성 ∪ 주간 보고), _asof_ok(), _inactives_line(), _last_starter_by_team(), _norm_name(), ph_inactives(), ph_injuries(), ph_ratings() (+16 more)

### Community 12 - "발행문 검사기(check_nfl)"
Cohesion: 0.15
Nodes (22): 귀속 대조(팀 바꿔 씀 검출), check_nfl --record 킥오프 가드·기록용 flag, 발행문 검사·기록(check_nfl --record), --record 출력 자르지 말 것(BrokenPipe 사고), 기준판 다이제스트 대조, N10 발행은 claude.ai NFL 발행 세션, attribution(), digest_sections() (+14 more)

### Community 13 - "발행 형식·선수/수비 표"
Cohesion: 0.15
Nodes (21): 발행문 상투구·커버 설명 금지(COVER_TALK), 🛡️ 수비 선수 표, 쉬운 라벨(시장보다 높게/낮게 봄·비슷 ±3%p), 선수 표로 결장 크기 재기(QB −5%p·타깃/캐리 1위 −2~−3%p), 🧑‍🤝‍🧑 선수 표, 예측시장 전/후 분할 재검, 경기별 발행 형식(예측·시장·판단·새 정보·명단·맞대결·팀 비교·선수 비교·선수 표·수비 표·변수·정리), REC 기록용 줄·요약표 (+13 more)

### Community 14 - "선수 기반 득점 모델"
Cohesion: 0.18
Nodes (19): adjust(), ats(), compact(), f(), main(), outs_of(), player_ratings(), ratings_asof() (+11 more)

### Community 15 - "수집 파이프라인 단계(nfl_pull)"
Cohesion: 0.13
Nodes (17): 무료 데이터(ESPN 공개 API·nflverse), current_week(), fetch(), main(), norm_cdf(), ph_model(), ph_results(), ph_sources() (+9 more)

### Community 16 - "4주차 발행·방향 동전·N1/N4/N9"
Cohesion: 0.18
Nodes (13): EPA/플레이 팀 레이팅 모델, 키 넘버 3·7, 킥오프 전 마지막 발행 = 정본, 발행 방향 = 동전(돈 아님), GB@TB (4주차), NYJ@CHI (4주차), 복붙용 NFL 발행 지침 10/01판(방향·판단 두 결정), 4주차 일요일 13경기 발행(10/4 08:45판 — 판단·방향 형식) (+5 more)

### Community 17 - "QB 수준·선발 QB 정본"
Cohesion: 0.15
Nodes (13): 예상 선발 QB 정본 = 최근 선발, _balance_table(), _prior_and_h2h(), _qb_of(), _qb_shrunk(), pbp 'J.Love' 와 뎁스차트 'Jordan Love' 대조 — 성 일치 + 이니셜., QB 한 명 합계 x → 리그 평균 쪽으로 수축한 EPA/드롭백., (이름, 드롭백, 원 EPA/드롭백, 보정 EPA) — 예상 선발 QB(없으면 드롭백 최다). (+5 more)

### Community 18 - "패스 매치업·실제 수치(nfl_pull)"
Cohesion: 0.22
Nodes (12): _cents_to_us(), _ftn_text(), _ngs_qb(), _pass_matchup_lines(), _rank(), NFL 주간 수집·모델·다이제스트 (2026-09-28 Paul 결정: 스프레드+총점 · 별도 레포 · 무료 데이터 · 이번 주부터).…, 예측시장 가격(0~1) → 미국식 배당 문자열., NGS 시즌 합계(week 0) — 예상 선발 QB 의 2026 값, 없으면 2025. (시즌, 투구 시간, CPOE, 공격성%, 시도) (+4 more)

### Community 19 - "다이제스트 렌더·관찰 각도 줄"
Cohesion: 0.18
Nodes (12): _angles_line(), _espn_names(), _ftn_by_team(), log(), ph_digest(), _predict_line(), 경기 절 「- 🔎 관찰 각도」 — 이 경기의 각도 페이퍼(picks.csv, 미채점)와 실측 한 줄. 돈 아님 · 발행 세션은 ML 각도가…, 🔮 예측(2026-10-04 Paul 「결과 예측을 하라」) — 경기 절 맨 위. 시장(가장 정확) + 우리 드라이브 모델(두 번째 의견). (+4 more)

### Community 20 - "4주차 전달문·포지션 매치업"
Cohesion: 0.22
Nodes (11): 📈 실제 수치 표, 최종 비활성 명단(킥오프 90분 전), 런던 경기(IND@WAS 06:30 PT), 📊 포지션 매치업 표, 실베팅 기록(picks.py place), 실력 vs 운 안정성 r(홀/짝 상관), 전달문 10/04 13:07(남은 5경기), 전달문 10/04 남은 6경기(새 형식 10/4판) (+3 more)

### Community 21 - "새 정보·±5%p 상한·별점"
Cohesion: 0.29
Nodes (10): 발행 예측 조정 상한 ±5%p, MLB 실측: 시장 반대 48% vs 같은 방향 63%, 라인 뒤 새 정보 페이퍼 관찰, 결장이 「새로운」지 먼저 본다(Porter 시즌 0경기), 결과 예측이 먼저(🔮 예측), ★주전급(스냅 60%+) 결장 표시, ⭐ 승자 자신감 별점(75/65/57 컷), 4주차 ATL@NO 발행(10/5 16:15 — 예측 줄 첫 형식) (+2 more)

### Community 22 - "1~3주차 소급 백테스트"
Cohesion: 0.29
Nodes (9): grade_row(), lines(), main(), model_preds(), paper(), 1~3주차 소급 백테스트(2026-10-05 Paul 「1~3주차도 백테스트해서 기록용으로 합치자」 — 수집 세션과 분담). python…, {A@H: dict(hl, tot, mla, mlh, src, gid, fa, fh, roof, neutral)} — DK 마감 우선., 스프레드·총점 쪽 W/L/P + 유닛. (+1 more)

### Community 23 - "키커 엣지 착시·10/17 탐색"
Cohesion: 0.42
Nodes (8): 10/17 엣지 탐색(가설 A~D·선수·팀), 키커 엣지 착시(P6 139-140), dec(), extract(), f(), main(), pimp(), 키커 엣지 백테스트(2026-10-17 Paul 「선수·팀 위주로 다시 찾아」 — P6 후보 확장): pbp 에서 FG 시도를 뽑아 팀-시즌…

### Community 24 - "가격 블록·무비그·Polymarket"
Cohesion: 0.33
Nodes (9): fnum(), _implied(), _novig(), _poly_lines(), _press_by_team(), _price_block(), 💵 블록 아래 「가격 비교」 — DK 와 같은 라인의 Polymarket 사는 가격, 쪽별로 더 싼 곳., 💵 가격 — DK 양쪽 배당 · 무비그 확률 · 손익분기 · 개장 → 지금 · 라인 이력(시각별). 서술·기록용(판단 근거는 발행 규칙대로). (+1 more)

### Community 25 - "시장 반영 백테스트 근거"
Cohesion: 0.25
Nodes (8): 특징 백테스트 F1~F6(사전 등록), FTN 차팅 서술(플레이액션·블리츠), 판단 3단계(패스·소액 관심 0.5u·관심 1u), 시장은 공개 정보를 이미 반영한다, 패스 매치업 줄(NGS·PFR 압박), 선수 기반 득점 모델 백테스트, 상황별 백테스트 2006~2025, 검증 구간 2023~25 = 한 번만 쓸 수 있는 카드

### Community 26 - "ESPN 스코어보드·라인 파싱"
Cohesion: 0.25
Nodes (8): _espn_prices(), _parse_spread(), ph_slate(), ESPN UTC('2026-10-02T00:15Z') → (ET datetime, PT datetime). 서머타임은 11월 첫 일요일…, ESPN 'PIT -3' → 홈 기준 스프레드(홈이 3점 페이버릿이면 -3.0). 못 읽으면 None., ESPN odds 블록(스코어보드 odds[0] 또는 summary pickcenter[0]) → 양쪽 배당·개장 값(2026-10-04 가격…, ESPN 주간 스코어보드 + nflverse 일정 → data/2026-wNN/games.csv, utc_to_et()

### Community 27 - "DAL@GB·가격 출처·기준판 차이"
Cohesion: 0.33
Nodes (6): 수집 세션 vs 발행 세션 새 정보 기준판 차이, Kalshi 가격, Polymarket 가격(gamma API bestAsk), 💵 가격 블록(DK·Polymarket), 6주차 DAL@GB 발행(10/18 SNF), 6주차 DAL@GB 외부 자료 보완(17:05)

### Community 28 - "MLB 교훈·값만 원칙"
Cohesion: 0.50
Nodes (4): MLB 교훈 이식(C19-12·D13-8·B14·B10-1·A9), ⚖️ 저울질 표(값만·점수 0), N3 ※ 값 얇음(2026 플레이 150 미만 후보 제외), N5 리스크는 값만 적는다

## Ambiguous Edges - Review These
- `A3 결장 팀 반대 3점+ 이동 → 결장 팀 쪽` → `BAL@ATL (5주차 SNF)`  [AMBIGUOUS]
  weeks/2026-w05/발행-1011-1605-BALATL.md · relation: conceptually_related_to

## Knowledge Gaps
- **12 isolated node(s):** `6주차 다이제스트 머리(10-19 17:19판)`, `모델 관찰(큰 괴리) 페이퍼 이상치 60픽 판정`, `EPA/플레이 팀 레이팅 모델`, `작년(2025) 스탯 열`, `무료 데이터(ESPN 공개 API·nflverse)` (+7 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `A3 결장 팀 반대 3점+ 이동 → 결장 팀 쪽` and `BAL@ATL (5주차 SNF)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `nfl-weekly-publish 스킬(발행 세션 · 10판 ML 전용)` connect `발행 형식·선수/수비 표` to `5주차 발행·스킬 판 이력·감사`, `6주차 발행·10판 ML 각도`, `picks 채점·CLV·페이퍼 관찰`, `운용 규칙 N0·N8·주간 절차`, `맥락 블록(맞대결·키커·심판)`, `4주차 전달문·포지션 매치업`, `새 정보·±5%p 상한·별점`, `시장 반영 백테스트 근거`, `DAL@GB·가격 출처·기준판 차이`, `MLB 교훈·값만 원칙`?**
  _High betweenness centrality (0.124) - this node is a cross-community bridge._
- **Why does `nfl-weekly 스킬(로컬 주간 운용)` connect `운용 규칙 N0·N8·주간 절차` to `picks 채점·CLV·페이퍼 관찰`, `NFL 보드(nfl_board.py)`, `결과 예측·드라이브 모델(predictions)`, `발행문 검사기(check_nfl)`, `4주차 전달문·포지션 매치업`, `시장 반영 백테스트 근거`?**
  _High betweenness centrality (0.116) - this node is a cross-community bridge._
- **Why does `🌍 국제·중립 경기 줄(토요일 발행)` connect `6주차 발행·10판 ML 각도` to `5주차 발행·스킬 판 이력·감사`, `패스 매치업·실제 수치(nfl_pull)`, `4주차 전달문·포지션 매치업`, `발행 형식·선수/수비 표`?**
  _High betweenness centrality (0.084) - this node is a cross-community bridge._
- **What connects `6주차 다이제스트 머리(10-19 17:19판)`, `모델 관찰(큰 괴리) 페이퍼 이상치 60픽 판정`, `EPA/플레이 팀 레이팅 모델` to the rest of the system?**
  _12 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `5주차 발행·스킬 판 이력·감사` be split into smaller, more focused modules?**
  _Cohesion score 0.13277428371767994 - nodes in this community are weakly interconnected._
- **Should `picks 채점·CLV·페이퍼 관찰` be split into smaller, more focused modules?**
  _Cohesion score 0.11033681765389082 - nodes in this community are weakly interconnected._