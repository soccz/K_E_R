# K_E_R — Korea Equity Reports

> DART 1순위 출처에 기반한 한국 상장사 자동 진단 시스템 — 페르소나 톤 + 출처 엄격주의 + 4단 검증 (V1·V2·V3·V4) + 트리거 기반 일간 관찰 메모.

**라이브 사이트**: https://soccz.github.io/projects/k-e-r/
**일간 관찰**: https://soccz.github.io/projects/k-e-r/daily/

[![tests](https://img.shields.io/badge/tests-186%2F186-brightgreen)](pipeline/tests)
[![validators](https://img.shields.io/badge/validators-V1%E2%80%A2V2%E2%80%A2V3%E2%80%A2V4-blue)](#검증-4단)
[![data](https://img.shields.io/badge/data-DART%20%2B%20KRX%20OHLCV%20%2B%20yfinance-lightgrey)](#데이터-소스)

---

## 무엇을 만드는가

코스피 24종목 워치리스트 + KOSPI200 큰 동향 종목 → 4가지 트랙으로 자동 출력:

| 트랙 | 빈도 | 분량 | 톤 | 슬롯 |
|---|---|---|---|---|
| **사업보고서 풀 진단** | 주 1편 | 20~30 페이지 (11섹션) | 페르소나 owner mindset | 화 22:00 KST |
| **일간 관찰 메모** | 주 2~3편 | 1면 (350~500단어) | 학술/연구 톤 | 매 평일 16:00 KST 트리거 검사 |
| **매크로 캐시** | 매일 | KOSPI/USD-KRW/WTI 60일 | — | 18:00 KST |
| **주말판 (산업노트)** | 주 1편 | 5~8페이지 | 페어 비교 | 일 21:00 KST (generator 미구현 → 평일판 대체) |

비전문가도 읽을 수 있도록 설계된 접근성 5규칙. 결론보다 *기업 자체의 상태*를 진단하는 의사 풀바디 체크업 형태. 매수·매도 권고 / 목표주가 / 단기 % 예측 *모두 금지*.

## 두 톤·하나의 데이터 레이어

```
              [공유 데이터 레이어]
   DART API (XBRL · 사업보고서 · 잠정실적 · majorstock)
   KRX OHLCV (pykrx) · macro (yfinance KOSPI/USDKRW/WTI)
                       │
        ┌──────────────┴──────────────┐
        ▼                             ▼
[내부 트랙]                    [외부 트랙]
사업보고서 풀 진단 (11섹션)   일간 관찰 메모
페르소나 owner mindset 100%   페르소나 + 학술 톤
companies/<>/2025-annual/    daily_notes/<YYYY-MM-DD>.md
주 1편 화 22:00              주 2-3편 평일 16:00 트리거
```

같은 사실을 두 톤에 *다른 분량·구조*로 출력. 페르소나 출처 엄격주의는 둘 다 100% 적용.

## 핵심 문서

| | 설명 |
|---|---|
| [`_persona.md`](_persona.md) | 사용자 투자 철학 — 비관 편향, 미국 시장 검증, 자금흐름 진실, 3년 단위 트랙, 외인 자금 ★★★, 압도적 기술 IP 양면성. owner mindset *"3년 후에도 매력 있는 회사인가, 시총 X조원에 통째로 살 만한가"* |
| [`_frame.md`](_frame.md) | 분석 프레임 + 출처·추론 절대 규칙 (sub-agent의 spec) |
| [`_daily_note_spec.md`](_daily_note_spec.md) | 일간 메모 외부 트랙 spec — 학술 톤·트리거·1면 구조 |
| [`_watchlist.md`](_watchlist.md) | 코스피 24종목 + 13섹터 + corp_code |

## 검증 4단

| | 검증 | 위반 처리 |
|---|---|---|
| **V1** (`validator.py`) | 출처 모호 (`보도에 따르면`)·추론 마커 누락·구조 | hard fail → 재시도 |
| **V2** (`validator_v2_numeric.py`) | XBRL ground truth 자릿수 (조↔억) | hard fail → 재시도 |
| **V3** (`validator_v3_arithmetic.py`) | 표 칼럼 합계·비중 100% | hard fail → 재시도 |
| **V4** (`cross_section_consistency.py`) | 11개 섹션 *권위 사실* (시총·매출·영업이익·1Q 잠정실적) 일관 인용 | hard fail → 재시도 |
| 보조 | `report_quality.find_inconsistencies` — 미래 키워드 분리 + 추론 마커 인식 | warn |

`run_dart`는 V1+V2+V3+V4 통합 피드백을 LLM에 전달하며 최대 3회 재시도. 끝까지 fail이면 합본 차단.

## 일간 메모 트리거 4종

| | 임계치 | 데이터 |
|---|---|---|
| 가격 변동 | 일별 ±5% | KRX OHLCV (pykrx, 비로그인) |
| DART 공시 | 잠정실적·M&A·정정·자사주 등 | DART list.json |
| 외인 수급 | 3일 누적 ±500억 | KRX 계정 필요 (placeholder, v0.4) |
| 외인-국내 디커플링 | 가격 ±2% + 외인 반대방향 ±300억 | 외인 데이터 의존, v0.4 |

매 평일 16:00 KST (KRX 장마감 +30분) 검사. 어느 하나라도 통과하면 LLM 호출 → 학술 톤 메모 → 사이트 push.

## 폴더 구조

```
report/
├── _persona.md _frame.md _daily_note_spec.md _watchlist.md _index.md _glossary.md
├── companies/<기업명>/<period>/   # 사업보고서 풀 진단
│   ├── 00_종합진단.md             # 합본 (최종 deliverable, 20~30페이지)
│   ├── 01_사업구조진단.md ~ 10_용어사전.md
│   ├── sections_raw/  sections_final/
│   └── raw_inputs/{dart_filings,xbrl,prompts}/
├── daily_notes/                   # 일간 메모 시계열 누적
│   ├── 2026-05-09.md
│   └── _raw/2026-05-09.txt        # LLM raw 응답 (디버그)
├── pipeline/                      # 자동화 코드 (모델 중립)
├── bin/                           # wrapper 스크립트
│   ├── run_weekly.sh run_weekend.sh run_daily.sh
│   ├── publish_site.sh push_results.sh healthcheck.sh
│   └── install_systemd.sh
├── systemd/                       # user timer / service 4종
└── logs/                          # 자동 실행 로그
```

## 자동화 (systemd user timer)

```
NEXT                           UNIT                     역할
Mon..Fri 16:00 KST             k_e_r-daily.timer        일간 트리거 검사
매일 18:00 KST                 k_e_r-daily-refresh.timer 매크로 캐시
일 21:00 KST                   k_e_r-weekend.timer      주말판 (현재 평일 대체)
화 22:00 KST                   k_e_r-weekday.timer      사업보고서 풀 진단 1편
```

`Persistent=true` — 컴퓨터 꺼져있다 켜지면 놓친 슬롯 즉시 catch-up.
`loginctl enable-linger` — 사용자 로그아웃해도 timer 동작.

## 셋업 (1회)

```bash
git clone https://github.com/soccz/K_E_R.git
cd K_E_R
python3 -m venv .venv && .venv/bin/pip install -e .

# DART 키 (.env)
echo "DART_API_KEY=발급받은_40자리_키" > .env && chmod 600 .env

# 워치리스트 corp_code 매핑 (1회)
.venv/bin/python -m pipeline.run_dart map-corps

# 자동화 활성화
sudo loginctl enable-linger $(whoami)
bash bin/install_systemd.sh

# 헬스체크
bash bin/healthcheck.sh
```

## 운영

```bash
# 한 종목 보고서 즉시 생성
.venv/bin/python -m pipeline.run_dart generate \
  --ticker 000660 --bsns-year 2025 --reprt-code 11011 --period 2025-annual

# 이미 받은 데이터로 LLM만 재실행
.venv/bin/python -m pipeline.run_dart generate ... --skip-fetch

# 단일 섹션 재생성 (stale 합본 방지)
.venv/bin/python -m pipeline.run_dart generate ... --section 02_재무건강진단

# 합본 다시
.venv/bin/python -m pipeline.run_dart assemble --ticker 000660 --period 2025-annual

# 일간 메모 dry-run (트리거만)
bash bin/run_daily.sh --check

# 일간 메모 강제 실행 (트리거 통과 시)
bash bin/run_daily.sh

# 사이트 렌더 + push
bash bin/publish_site.sh
```

## 데이터 소스

페르소나 §11 정책 — *종목 단위 데이터는 1순위 출처만*.

| 항목 | 출처 |
|---|---|
| 재무제표 (XBRL) | DART `fnlttXbrl.xml` (1순위) |
| 발행주식수·자기주식 | DART `stockTotqySttus.json` (1순위) |
| 5%↑ 보유공시 | DART `majorstock.json` (1순위) |
| 사업보고서 본문 | DART `document.xml` → `business_report_extractor` (12개 섹션 자동 절단) |
| 잠정실적·분기보고서 | DART `list.json` + `quarterly_disclosure._fetch_filing_body_excerpt` |
| 종가·거래량 | KRX OHLCV (pykrx, 비로그인) |
| 시가총액 | DART 발행주식수 × KRX 종가 (computed, 1순위) |
| 매크로 (KOSPI·USD-KRW·WTI) | yfinance — 시장 전체 영역, 종목 단위 X |
| 외인 일별잔고 | KRX 계정 필요 (placeholder, v0.4) |

## LLM

`claude -p` CLI subprocess (구독 인증, API 키 불필요). `LLM_PROVIDER=anthropic`로 환경변수 변경 시 Anthropic SDK 직접 호출.

```python
# pipeline/llm_client.py
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "claude_code")
CLAUDE_CODE_TIMEOUT_SEC = 1800  # 큰 사업보고서 안전 마진
```

프롬프트 사이즈 200KB 초과 시 `section_builder`가 경고 (timeout 사전 방지).

## 테스트

```bash
.venv/bin/python -m pytest pipeline/tests/ -q
```

**186 tests**:
- validator V1·V2·V3 (구조·자릿수·산술)
- cross-section consistency V4 (시총·매출·영업이익 일관)
- 데이터 fetcher (ticker_market·foreign_holdings·quarterly·business_report)
- 일간 메모 트리거 + 빌더 + SVG 스파크라인
- site 렌더링 + 보고서 합본 + 헤드라인-본문 일관성

## 페르소나 핵심

- **수출국 한국**: 매출 해외 비중·미국 시장 검증을 모든 종목 분석의 중심축
- **자금이 진실**: 영업이익은 가공할 수 있지만 영업CF는 거짓말 못 한다
- **3년 단위 (AI 시대)**: 5년→3년으로 좁힘. 1년 부진은 무시, 3년 트랙이 흔들리면 적신호
- **외인이 실세** ★★★: 외인 비중 추세적 하락 + 국내 인기 상승 = 강한 적신호
- **압도적 기술 양면성**: (a) 미국 자본 인수 호재 vs (b) IP·핵심 인력 빠지고 빈 껍데기
- **owner mindset**: 주가 시세가 아닌 *사업체*. *"3년 후에도 안 망하고 매력 있을 회사인가, 시총 X조원에 통째로 살 만한가"*

## reprt_code

| 코드 | 보고서 | 법정 제출기한 |
|---|---|---|
| 11011 | 사업보고서 | 다음해 3월 31일 |
| 11012 | 반기보고서 | 8월 14일 |
| 11013 | 1분기보고서 | 5월 15일 |
| 11014 | 3분기보고서 | 11월 14일 |

## 라이선스·기여

- 본 시스템은 매수·매도 권고가 아닌 *공개 관찰·진단 기록*
- DART 데이터는 금융감독원 OpenAPI 이용약관에 따름
- 시스템 코드 자체에 대한 라이선스 정책은 추가 예정

## 변경 이력

- **2026-05-09**: Phase A~E — 일간 관찰 메모 시스템 (트리거·빌더·사이트·자동화) + V4 cross-section consistency 검증 + DART+KRX OHLCV 통합 + 사업보고서 본문 12섹션 추출 + 잠정실적 본문 자동 다운로드 + 매크로 종목 프롬프트 주입
- **2026-05-07**: Phase 3.5 — V4 cross-section + 환각 차단 + ticker_market·foreign_holdings·quarterly_disclosure·business_report_extractor 모듈 신규
- **2026-05-02**: Phase 2-3 — 3단 validator + DART API 클라이언트 + corp_code 매퍼 + 자동 entry
