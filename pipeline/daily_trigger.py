"""일간 메모 임계치 검사기.

`_daily_note_spec.md` §3에 정의된 4종 임계치를 검사.
어느 하나라도 충족하면 일간 메모 발행 트리거.

매일 16:00 KST(장마감 +30분) 자동 실행:
  $ python -m pipeline.daily_trigger --check

트리거 4종 (모두 활성):
  3.1 가격 변동: 워치리스트 24종목 일별 등락률 ±5% (KRX OHLCV)
  3.2 외인 수급: 3일 누적 외인 ±500억 (KRX 매매대금 → Naver fallback)
  3.3 DART 공시: 잠정실적·M&A·정정공시·자사주 소각·주요사항 (DART list.json)
  3.4 디커플링: 가격 ±2% + 외인 반대방향 ±300억 (페르소나 §1.7 핵심 ★★★)

점수화:
  score = 20·|등락률| + 0.5·|외인 누적| + 30·공시 임팩트 + 50·디커플링 강도
  (디커플링이 페르소나 ★★★ 핵심이라 가장 무거움)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from pathlib import Path


# 트리거 타입
TRIGGER_PRICE_MOVE = "price_move"
TRIGGER_FOREIGN_FLOW = "foreign_flow"
TRIGGER_DART_DISCLOSURE = "dart_disclosure"
TRIGGER_DECOUPLING = "decoupling"

# 임계치 (spec §3)
PRICE_MOVE_PCT = 5.0  # 일별 ±5%
FOREIGN_FLOW_KRW = 500e8  # 3일 누적 ±500억
FOREIGN_FLOW_DAYS = 3
DECOUPLING_PRICE_PCT = 2.0  # 가격 ±2%
DECOUPLING_FOREIGN_KRW = 300e8  # 외인 반대방향 ±300억
KOSPI200_PRICE_PCT = 7.0  # 워치리스트 외 KOSPI200은 더 빡빡

# DART 공시 키워드 (페르소나 ★★ 이상 임팩트)
_DART_TRIGGER_KEYWORDS = (
    "잠정실적",
    "영업(잠정)실적",
    "주요사항",
    "M&A",
    "합병",
    "분할",
    "주식양수도",
    "유상증자",
    "무상증자",
    "전환사채",
    "신주인수권부",
    "교환사채",
    "자기주식",
    "자사주",
    "정정",  # 정정공시 (수치 변경)
)


@dataclass(frozen=True)
class TriggerHit:
    ticker: str  # KRX 6자리
    company_name: str
    trigger_type: str
    severity: float  # 임계치 대비 강도 (1.0 = 임계치 정확, 1.5 = 50% 초과)
    detail: dict  # 트리거 raw 데이터

    def score(self) -> float:
        """일간 메모 종목 카드 선정용 점수."""
        coeffs = {
            TRIGGER_PRICE_MOVE: 20,
            TRIGGER_FOREIGN_FLOW: 0.5,  # 0.5는 |외인 누적|/억 단위 가중치
            TRIGGER_DART_DISCLOSURE: 30,
            TRIGGER_DECOUPLING: 50,  # ★★★ 페르소나 핵심
        }
        return coeffs.get(self.trigger_type, 10) * self.severity


@dataclass(frozen=True)
class TriggerReport:
    fetch_date: str  # YYYY-MM-DD
    hits: list[TriggerHit] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)

    def should_publish(self) -> bool:
        return len(self.hits) > 0

    def top_n_tickers(self, n: int = 3) -> list[str]:
        """점수 상위 N개 티커 (중복 제거 — 한 종목이 여러 트리거 맞으면 합산)."""
        from collections import defaultdict

        ticker_scores: dict[str, float] = defaultdict(float)
        ticker_company: dict[str, str] = {}
        for h in self.hits:
            ticker_scores[h.ticker] += h.score()
            ticker_company[h.ticker] = h.company_name
        sorted_tickers = sorted(
            ticker_scores.items(), key=lambda x: x[1], reverse=True
        )
        return [t for t, _ in sorted_tickers[:n]]

    def hits_for_ticker(self, ticker: str) -> list[TriggerHit]:
        return [h for h in self.hits if h.ticker == ticker]


# ────────────────────────────────────────────────────────────────────
# 3.1 가격 변동
# ────────────────────────────────────────────────────────────────────


def _fetch_recent_ohlcv(ticker_krx: str, days: int = 5) -> dict | None:
    """KRX OHLCV 최근 N일. 어제·오늘 종가 + 거래량."""
    try:
        from pykrx import stock
    except ImportError:
        return None
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days * 2 + 5)).strftime("%Y%m%d")
    try:
        df = stock.get_market_ohlcv_by_date(start, end, ticker_krx)
    except Exception:
        return None
    if df is None or df.empty or len(df) < 2:
        return None
    closes = df["종가"].dropna()
    volumes = df["거래량"].dropna()
    if len(closes) < 2:
        return None
    today = float(closes.iloc[-1])
    yesterday = float(closes.iloc[-2])
    pct_change = (today / yesterday - 1) * 100 if yesterday else 0.0
    return {
        "today_close": today,
        "yesterday_close": yesterday,
        "today_pct_change": pct_change,
        "today_volume": float(volumes.iloc[-1]) if len(volumes) > 0 else None,
        "avg_volume_60d": (
            float(volumes.tail(60).mean()) if len(volumes) >= 10 else None
        ),
        "today_date": closes.index[-1].strftime("%Y-%m-%d"),
    }


def check_price_movement(
    ticker_krx: str,
    company_name: str,
    threshold_pct: float = PRICE_MOVE_PCT,
) -> TriggerHit | None:
    """일별 등락률 ±threshold_pct 이상이면 트리거."""
    data = _fetch_recent_ohlcv(ticker_krx, days=3)
    if data is None:
        return None
    pct = data["today_pct_change"]
    if abs(pct) < threshold_pct:
        return None
    return TriggerHit(
        ticker=ticker_krx,
        company_name=company_name,
        trigger_type=TRIGGER_PRICE_MOVE,
        severity=abs(pct) / threshold_pct,
        detail={
            "pct_change": round(pct, 2),
            "today_close": data["today_close"],
            "today_date": data["today_date"],
            "threshold_pct": threshold_pct,
        },
    )


# ────────────────────────────────────────────────────────────────────
# 3.2 외인 수급 (placeholder — KRX 계정 발급 후 v0.4)
# ────────────────────────────────────────────────────────────────────


def check_foreign_flow(
    ticker_krx: str,
    company_name: str,
    threshold_krw: float = FOREIGN_FLOW_KRW,
    days: int = FOREIGN_FLOW_DAYS,
) -> TriggerHit | None:
    """N영업일 누적 외인 순매매 ±threshold_krw 이상이면 트리거.

    출처: KRX 정식 매매대금 (1순위) → Naver Finance fallback.
    KRX_ID/KRX_PW 미설정 시 자동으로 Naver로 폴백.
    """
    from pipeline.foreign_flow import cumulative_foreign_krw, fetch_foreign_flow

    flow = fetch_foreign_flow(ticker_krx, days=days)
    if len(flow) < days:
        return None
    cumulative = cumulative_foreign_krw(flow, n=days)
    if abs(cumulative) < threshold_krw:
        return None
    direction = "매수" if cumulative > 0 else "매도"
    sources = sorted({d.source for d in flow[:days]})
    return TriggerHit(
        ticker=ticker_krx,
        company_name=company_name,
        trigger_type=TRIGGER_FOREIGN_FLOW,
        severity=abs(cumulative) / threshold_krw,
        detail={
            "cumulative_krw": cumulative,
            "cumulative_eok": round(cumulative / 1e8, 1),
            "direction": direction,
            "days_count": days,
            "first_date": flow[days - 1].date,
            "last_date": flow[0].date,
            "data_source": "+".join(sources),
        },
    )


# ────────────────────────────────────────────────────────────────────
# 3.3 DART 신규 공시
# ────────────────────────────────────────────────────────────────────


def _fetch_recent_dart_filings(corp_code: str, days_back: int = 1) -> list[dict]:
    """DART list.json에서 최근 N일 공시."""
    try:
        from pipeline import config
        from pipeline.dart_client import DartClient
    except ImportError:
        return []
    if not config.DART_API_KEY:
        return []

    today = datetime.now()
    bgn = (today - timedelta(days=days_back)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    try:
        client = DartClient()
        data = client.list_filings(
            corp_code=corp_code,
            bgn_de=bgn,
            end_de=end,
            page_count=50,
            last_reprt_at="Y",
        )
    except Exception:
        return []
    return data.get("list", []) or []


def _disclosure_impact_score(report_nm: str) -> float:
    """공시명에서 임팩트 점수 산출. 잠정실적·M&A는 강함."""
    name = report_nm or ""
    if "잠정실적" in name or "영업(잠정)실적" in name:
        return 1.5
    if "주요사항보고" in name or "M&A" in name or "합병" in name:
        return 1.3
    if "정정" in name:
        return 1.2
    if "자기주식" in name or "자사주" in name:
        return 1.1
    if any(kw in name for kw in _DART_TRIGGER_KEYWORDS):
        return 1.0
    return 0.0  # 매치 없음 → 트리거 X


def check_dart_disclosure(
    ticker_krx: str,
    company_name: str,
    corp_code: str,
    days_back: int = 1,
) -> TriggerHit | None:
    """DART 신규 공시 (페르소나 ★★ 이상 임팩트)에 매치되면 트리거."""
    filings = _fetch_recent_dart_filings(corp_code, days_back=days_back)
    if not filings:
        return None
    matched: list[tuple[float, dict]] = []
    for item in filings:
        score = _disclosure_impact_score(item.get("report_nm", ""))
        if score > 0:
            matched.append((score, item))
    if not matched:
        return None
    matched.sort(key=lambda x: x[0], reverse=True)
    best_score, best_filing = matched[0]
    return TriggerHit(
        ticker=ticker_krx,
        company_name=company_name,
        trigger_type=TRIGGER_DART_DISCLOSURE,
        severity=best_score,
        detail={
            "report_nm": best_filing.get("report_nm"),
            "rcept_no": best_filing.get("rcept_no"),
            "rcept_dt": best_filing.get("rcept_dt"),
            "matched_count": len(matched),
        },
    )


# ────────────────────────────────────────────────────────────────────
# 3.4 외인-국내 디커플링 (placeholder — 외인 통합 후 활성)
# ────────────────────────────────────────────────────────────────────


def check_decoupling(
    ticker_krx: str,
    company_name: str,
    price_threshold_pct: float = DECOUPLING_PRICE_PCT,
    foreign_threshold_krw: float = DECOUPLING_FOREIGN_KRW,
) -> TriggerHit | None:
    """가격 ±price_threshold_pct AND 외인 반대방향 ±foreign_threshold_krw → 트리거.

    페르소나 §1.7 "국내 환호 vs 외인 디커플링" 자동 감지.
    예: 가격 +5% 인데 외인 -800억 매도 → "국내 환호 / 외인 거부" 시그널.
    출처: KRX (1순위) → Naver fallback.
    """
    from pipeline.foreign_flow import fetch_foreign_flow

    flow = fetch_foreign_flow(ticker_krx, days=1)
    if not flow:
        return None
    today = flow[0]

    if abs(today.pct_change) < price_threshold_pct:
        return None
    if abs(today.foreign_net_krw) < foreign_threshold_krw:
        return None

    price_up = today.pct_change > 0
    foreign_buy = today.foreign_net_krw > 0
    if price_up == foreign_buy:
        return None  # 같은 방향 → 디커플링 아님

    label = "국내 환호 / 외인 매도" if price_up else "국내 패닉 / 외인 매수"
    # severity = 가격 over-threshold × 외인 over-threshold (둘 다 가산 시 강도 큼)
    sev_price = abs(today.pct_change) / price_threshold_pct
    sev_foreign = abs(today.foreign_net_krw) / foreign_threshold_krw
    return TriggerHit(
        ticker=ticker_krx,
        company_name=company_name,
        trigger_type=TRIGGER_DECOUPLING,
        severity=(sev_price + sev_foreign) / 2,
        detail={
            "date": today.date,
            "pct_change": round(today.pct_change, 2),
            "foreign_krw": today.foreign_net_krw,
            "foreign_eok": round(today.foreign_net_krw / 1e8, 1),
            "label": label,
            "data_source": today.source,
        },
    )


# ────────────────────────────────────────────────────────────────────
# 종합 평가
# ────────────────────────────────────────────────────────────────────


def evaluate_all_triggers(
    watchlist_entries: list,  # list[WatchlistEntry] — pipeline.watchlist_parser
    fetch_date: str | None = None,
) -> TriggerReport:
    """워치리스트 24종목에 대해 4종 임계치 검사."""
    fetch_date = fetch_date or datetime.now().strftime("%Y-%m-%d")
    hits: list[TriggerHit] = []
    notes: list[str] = []
    sources: dict[str, str] = {}

    sources["price"] = "pykrx KRX OHLCV"
    sources["dart"] = "DART list.json"
    sources["foreign"] = "KRX 매매대금 (1순위) → Naver Finance fallback"
    notes.append("4종 트리거 모두 활성: 가격(3.1)·외인 수급(3.2)·DART 공시(3.3)·디커플링(3.4).")

    for entry in watchlist_entries:
        ticker = entry.ticker
        company = entry.name
        corp_code = getattr(entry, "corp_code", None)

        # 3.1 가격
        h_price = check_price_movement(ticker, company)
        if h_price:
            hits.append(h_price)

        # 3.2 외인 수급 (3일 누적 ±500억)
        h_foreign = check_foreign_flow(ticker, company)
        if h_foreign:
            hits.append(h_foreign)

        # 3.3 DART
        if corp_code:
            h_dart = check_dart_disclosure(ticker, company, corp_code)
            if h_dart:
                hits.append(h_dart)

        # 3.4 디커플링 (가격±2% AND 외인 반대방향±300억)
        h_decouple = check_decoupling(ticker, company)
        if h_decouple:
            hits.append(h_decouple)

    # 점수 내림차순 정렬
    hits.sort(key=lambda h: h.score(), reverse=True)
    return TriggerReport(
        fetch_date=fetch_date,
        hits=hits,
        notes=notes,
        sources=sources,
    )


def render_report(report: TriggerReport) -> str:
    """CLI 출력용 사람 읽기 형태."""
    out = [f"=== 일간 트리거 검사 결과 — {report.fetch_date} ==="]
    if not report.hits:
        out.append("트리거된 종목 없음 — 일간 메모 미발행.")
    else:
        out.append(f"트리거 {len(report.hits)}건 / 종목 풀 {len(set(h.ticker for h in report.hits))}개")
        for h in report.hits:
            out.append(
                f"  [{h.trigger_type}] {h.company_name} ({h.ticker}) "
                f"severity={h.severity:.2f} score={h.score():.1f}"
            )
            for k, v in h.detail.items():
                out.append(f"      {k}: {v}")
        out.append("")
        out.append("종목 카드 후보 (상위 3): " + ", ".join(report.top_n_tickers(3)))

    if report.notes:
        out.append("")
        out.append("--- notes ---")
        for n in report.notes:
            out.append(f"  · {n}")
    return "\n".join(out)


def main() -> int:
    """CLI: python -m pipeline.daily_trigger --check"""
    import argparse

    p = argparse.ArgumentParser(description="일간 메모 임계치 검사")
    p.add_argument("--check", action="store_true", help="트리거 검사만 (발행 X)")
    p.add_argument("--save", type=str, help="결과 JSON 저장 경로")
    args = p.parse_args()

    from pipeline.config import WATCHLIST_PATH
    from pipeline.watchlist_parser import parse_watchlist

    watchlist = parse_watchlist(WATCHLIST_PATH.read_text(encoding="utf-8"))
    report = evaluate_all_triggers(watchlist)
    print(render_report(report))

    if args.save:
        target = Path(args.save)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "fetch_date": report.fetch_date,
            "should_publish": report.should_publish(),
            "hits": [asdict(h) for h in report.hits],
            "top_3_tickers": report.top_n_tickers(3),
            "notes": report.notes,
            "sources": report.sources,
        }
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nsaved: {target}")

    return 0 if report.should_publish() else 0  # 트리거 없어도 정상 종료


if __name__ == "__main__":
    raise SystemExit(main())
