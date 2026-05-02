# K_E_R — Korea Equity Report

DART 기반 한국 상장사 종합 진단 시스템.

코스피 24종목 (섹터별 분산) 추적 → 매주 2편 보고서 자동 생성 → GitHub 레포 누적.

- **평일판 (화 22:00 KST)**: 그 주 공시 기반 종목 종합 진단 (8섹션 분할 → 합본, 20~30페이지)
- **주말판 (일 21:00 KST)**: 산업노트 1편 (5~8페이지)

비전문가도 읽을 수 있도록 설계된 접근성 5규칙. 결론보다 *기업 자체의 상태*를 진단하는 의사 풀바디 체크업 형태. **출처 엄격주의 + 추론 명시 + 표 산술 자동 검증.**

## 폴더 구조

```
report/
├── _frame.md           # 분석 프레임 + 출처·추론 규칙 (sub-agent의 spec)
├── _persona.md         # 사용자 투자 철학 (frame과 함께 sub-agent에게 주입)
├── _watchlist.md       # 코스피 24종목 + 섹터 + corp_code
├── _index.md           # 보고서 인덱스 (자동 갱신)
├── _glossary.md        # 누적 용어사전 (자동 갱신)
├── companies/          # 평일판 — 종목별 종합 진단
│   └── <기업명>/<period>/
│       ├── 00_종합진단.md   ← 합본 (최종 deliverable)
│       ├── 01_사업구조진단.md ~ 10_용어사전.md
│       ├── sections_raw/    # LLM 1차 출력 (validator 전)
│       ├── sections_final/  # validator 통과 후
│       └── raw_inputs/
│           ├── dart_filings/  # 공시 원문 ZIP 압축 해제
│           ├── xbrl/          # XBRL 패키지
│           └── prompts/       # 시스템·유저 프롬프트 스냅샷
├── industry_notes/     # 주말판 — 산업노트
│   └── <YYYY-WNN>-<섹터>.md
└── pipeline/           # 자동화 코드 (모델 중립, 어떤 회사든 동일 작동)
```

## 아키텍처

```
[로컬 cron — 22tb 서버 (24/7)]
   ↓ 화 22 / 일 21 KST
[python -m pipeline.run_dart generate ...]
   ↓
[DART OpenAPI: 공시 + XBRL fetch] → raw_inputs/
   ↓
[xbrl_parser → source_pack (ground truth 숫자)]
   ↓
[8개 섹션 순차 생성 (claude -p, 구독 인증)]
   ↓
[Validator V1 (출처·추론) + V3 (표 산술) — hard fail 시 재시도 (최대 3회)]
   ↓
[Validator V2 (XBRL 매칭) — warn-only, 분석가 도우미]
   ↓
[report_assembler → 00_종합진단.md (TOC + 본문 + Owner valuation)]
   ↓
[git commit & push → soccz/K_E_R]
```

**LLM 호출:** `claude -p` CLI (구독 인증, API 키 불필요). `LLM_PROVIDER=anthropic`로 환경변수 바꾸면 Anthropic API로 전환 가능.

## 시작 (1회 셋업)

### 1. DART OpenAPI 키 발급
opendart.fss.or.kr 가입 → 인증키 신청 → 거의 즉시 발급.

`.env` 파일 (`/home/soccz/22tb/report/.env`)에 한 줄:
```
DART_API_KEY=발급받은_40자리_키
```

### 2. 워치리스트 corp_code 일괄 매핑 (1회)
```bash
cd /home/soccz/22tb/report
.venv/bin/python -m pipeline.run_dart map-corps
```
→ DART corpCode.xml 다운로드 → `_watchlist.md`의 24종목 TBD 칼럼 자동 채움.

### 3. 첫 보고서 자동 생성
```bash
.venv/bin/python -m pipeline.run_dart generate \
  --ticker 005930 \
  --bsns-year 2025 \
  --reprt-code 11011 \
  --period 2025-annual
```
→ DART 공시 fetch → 8섹션 생성 → validator 통과 → 합본 → `companies/삼성전자/2025-annual/00_종합진단.md`

### 4. GitHub 레포 push
```bash
git init
git add .
git commit -m "initial: K_E_R system + first report"
git remote add origin https://github.com/soccz/K_E_R.git
git branch -M main
git push -u origin main
```

### 5. 자동화 등록 — systemd timer (cron보다 강력)

cron 대신 systemd user timer 사용 — 컴퓨터가 슬롯 시간에 꺼져있었으면 *부팅 즉시 catch-up*하고 (`Persistent=true`), 네트워크 준비 후 실행하며 (`After=network-online.target`), 사용자 로그아웃 시에도 동작한다 (`loginctl enable-linger`).

```bash
# 1. user lingering 활성화 (1회만, root 필요) — 로그아웃해도 timer 동작
sudo loginctl enable-linger $(whoami)

# 2. 설치 + 활성화
bin/install_systemd.sh

# 3. 다음 실행 시간 확인
systemctl --user list-timers k_e_r-*.timer
```

**부팅 복구 흐름:**
```
[컴퓨터 종료] → 슬롯 시간(화 22:00 KST) 지남 → [부팅]
                                            ↓
                                    network-online.target 도달
                                            ↓
                                    systemd가 missed run 감지
                                            ↓
                                    k_e_r-weekday.service 자동 실행
```

**수동 실행도 항상 가능:**
```bash
bin/run_weekly.sh   # 평일판 즉시 실행
```

**주말판 (산업노트)는 stub 상태** — generator 구현 후 활성화:
```bash
systemctl --user enable --now k_e_r-weekend.timer
```

### 6. 헬스체크
```bash
bin/healthcheck.sh
```

7개 영역 (파일·.env·Python·Claude CLI·systemd·네트워크·git) 자동 점검.

## 일상 운영

### 한 회사 보고서 다시 생성
```bash
.venv/bin/python -m pipeline.run_dart generate \
  --ticker 000660 --bsns-year 2025 --reprt-code 11011 --period 2025-annual
```

### 이미 다운된 데이터로 재생성 (LLM만 다시)
```bash
.venv/bin/python -m pipeline.run_dart generate \
  --ticker 005930 --bsns-year 2025 --reprt-code 11011 --period 2025-annual \
  --skip-fetch
```

### 단일 섹션만
```bash
.venv/bin/python -m pipeline.run_dart generate \
  --ticker 005930 --bsns-year 2025 --reprt-code 11011 --period 2025-annual \
  --section 02_재무건강진단
```

### 결과물 보기
```bash
# Obsidian / VS Code / 웹 GitHub UI
open companies/삼성전자/2025-annual/00_종합진단.md
```

## Validator 3단

| | 검증 대상 | 위반 처리 |
|---|---|---|
| **V1** (validator.py) | 출처 모호 표현·추론 마커·구조 | hard fail → 재시도 |
| **V3** (validator_v3_arithmetic.py) | 표 칼럼 합계·비중 합 100% | hard fail → 재시도 |
| **V2** (validator_v2_numeric.py) | XBRL ground truth 매칭 (자릿수 오류) | warn-only → 분석가 검토 |

## 테스트

```bash
.venv/bin/pytest pipeline/tests/ -q
```

70+ unit tests. validator 정확성, XBRL 파싱, 합본 구조 등.

## reprt_code 코드표

| 코드 | 보고서 | 법정 제출기한 |
|---|---|---|
| 11011 | 사업보고서 (annual) | 다음해 3월 31일 |
| 11012 | 반기보고서 (H1) | 8월 14일 |
| 11013 | 1분기보고서 (Q1) | 5월 15일 |
| 11014 | 3분기보고서 (Q3) | 11월 14일 |

## 변경 이력

- 2026-05-02: 시스템 설계 + Phase 2 (스캐폴딩 + 3단 validator + 삼성전자 1회 시범 통과)
- 2026-05-02: Phase 3 — DART API 클라이언트 + corp_code 매퍼 + 자동 entry + 합본
