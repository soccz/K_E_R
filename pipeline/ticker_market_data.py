"""종목 단위 시장 데이터 fetcher.

운영 정책 (페르소나 §11 표):
  - 발행주식수·자기주식: DART OpenAPI `stockTotqySttus.json` (1순위)
  - 종가 시계열: pykrx OHLCV (KRX 공식 페이지, 비로그인 비스크래핑) — 1순위
  - 시가총액: 두 값을 곱해서 자동 계산 (DART 발행주식수 × KRX 최신 종가)
  - 외인 일별잔고·투자자유형별 매매: KRX 계정 필요 → 본 모듈에서 미통합

페르소나·프레임 의무 항목:
  - 시가총액: owner-valuation의 'X조원' 인용용
  - 발행주식수: 자기주식 비중·EPS 분모 검증용
  - 종가 추이: 사이클 위치 진단·외인 매도 패턴 분석 보조

캐시: 1일 TTL. 종가는 일별 갱신, 발행주식수는 사업보고서 기준이라 변동 빈도 낮음.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class TickerMarketSnapshot:
    ticker: str  # KRX 6자리 (e.g. "000660")
    company_name: str
    issued_shares_common: int | None  # 보통주 발행주식수 (DART)
    issued_shares_preferred: int | None  # 우선주 발행주식수 (있으면)
    treasury_shares: int | None  # 자기주식
    distributed_shares: int | None  # 유통주식수
    latest_close_krw: float | None  # 최신 종가 (KRX)
    latest_close_date: str | None  # 종가 기준일
    market_cap_krw: float | None  # 시가총액 (computed)
    market_cap_trillion_krw: float | None
    close_60d_pct_change: float | None  # 최근 60일 등락률
    close_1y_pct_change: float | None  # 최근 1년 등락률
    sources: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_prompt_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "company": self.company_name,
            "issued_shares_common": self.issued_shares_common,
            "issued_shares_preferred": self.issued_shares_preferred,
            "treasury_shares": self.treasury_shares,
            "distributed_shares": self.distributed_shares,
            "latest_close_krw": self.latest_close_krw,
            "latest_close_date": self.latest_close_date,
            "market_cap_krw": self.market_cap_krw,
            "market_cap_trillion_krw": self.market_cap_trillion_krw,
            "close_60d_pct_change": self.close_60d_pct_change,
            "close_1y_pct_change": self.close_1y_pct_change,
            "sources": self.sources,
            "notes": self.notes,
            "usage_rule": (
                "owner-valuation에서 '시총 ~조원에 통째로 살 만한가' 질문에 "
                "market_cap_trillion_krw를 반드시 인용. "
                "발행주식수=DART(1순위), 종가=KRX(1순위), 시총=두 값의 곱(파생). "
                "60일·1년 등락률은 페르소나 §1.7(국내 환호 역지표) + 외인 매도 동향과 "
                "교차 검증할 때 보조. 단, 차트·이평선·기술적 분석 톤은 금지(페르소나 §8). "
                "값이 None이면 '확인되지 않음'으로 정직히 처리하고 추정으로 채우지 마라."
            ),
        }


def _fetch_dart_stock_totqy(corp_code: str, bsns_year: int, reprt_code: str) -> list[dict]:
    """DART stockTotqySttus.json — 주식 총수 현황 raw items."""
    try:
        from pipeline import config
        from pipeline.dart_client import DartClient, DartApiError
    except ImportError:
        return []
    if not config.DART_API_KEY:
        return []
    try:
        client = DartClient()
        r = client._get(
            "stockTotqySttus.json",
            {"corp_code": corp_code, "bsns_year": str(bsns_year), "reprt_code": reprt_code},
        )
        data = r.json()
    except Exception:
        return []
    if data.get("status") not in ("000", None):
        return []
    return list(data.get("list") or [])


def _to_int(s: str | None) -> int | None:
    if s is None:
        return None
    try:
        return int(str(s).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _parse_stock_totqy(items: list[dict]) -> dict[str, int | None]:
    """stockTotqySttus 응답에서 보통주/우선주/자기주식/유통주식 추출.

    DART 응답 필드:
      - se: 구분 ("보통주", "우선주" 등)
      - istc_totqy: 발행주식의 총수
      - tesstk_co: 자기주식수
      - distb_stock_co: 유통주식수 (= 발행 - 자기)
    """
    out: dict[str, int | None] = {
        "issued_shares_common": None,
        "issued_shares_preferred": None,
        "treasury_shares": None,
        "distributed_shares": None,
    }
    for row in items:
        se = (row.get("se") or "").strip()
        total = _to_int(row.get("istc_totqy") or row.get("istc_totqy_co"))
        if "보통주" in se or "통상주" in se:
            out["issued_shares_common"] = total
            out["treasury_shares"] = _to_int(row.get("tesstk_co"))
            out["distributed_shares"] = _to_int(row.get("distb_stock_co"))
        elif "우선주" in se:
            out["issued_shares_preferred"] = total
    return out


def _fetch_krx_ohlcv(ticker_krx: str, days: int = 400) -> dict:
    """pykrx OHLCV — 최신 종가 + 60일/1년 변화율 best-effort.

    pykrx의 get_market_ohlcv_by_date는 비로그인으로 작동.
    실패 시 빈 dict 반환.
    """
    try:
        from pykrx import stock
    except ImportError:
        return {"error": "pykrx not installed"}
    from datetime import datetime, timedelta

    try:
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        df = stock.get_market_ohlcv_by_date(start, end, ticker_krx)
    except Exception as e:
        return {"error": f"pykrx fetch failed: {e}"}
    if df is None or df.empty:
        return {"error": "pykrx empty result"}

    closes = df["종가"].dropna()
    if closes.empty:
        return {"error": "no close prices"}

    latest_close = float(closes.iloc[-1])
    latest_date = closes.index[-1].strftime("%Y-%m-%d")

    out: dict = {
        "latest_close_krw": latest_close,
        "latest_close_date": latest_date,
    }
    # 60일 등락률
    if len(closes) >= 60:
        c60 = float(closes.iloc[-60])
        if c60:
            out["close_60d_pct_change"] = round((latest_close / c60 - 1) * 100, 2)
    # 1년 등락률 (영업일 ~250)
    if len(closes) >= 240:
        c1y = float(closes.iloc[-240])
        if c1y:
            out["close_1y_pct_change"] = round((latest_close / c1y - 1) * 100, 2)
    elif len(closes) >= 2:
        c_first = float(closes.iloc[0])
        if c_first:
            out["close_1y_pct_change"] = round((latest_close / c_first - 1) * 100, 2)
    return out


def fetch_ticker_snapshot(
    ticker_krx: str,
    company_name: str,
    corp_code: str | None,
    bsns_year: int,
    reprt_code: str = "11011",
) -> TickerMarketSnapshot:
    sources: dict[str, str] = {}
    notes: list[str] = []
    parsed: dict[str, int | None] = {
        "issued_shares_common": None,
        "issued_shares_preferred": None,
        "treasury_shares": None,
        "distributed_shares": None,
    }

    if corp_code:
        items = _fetch_dart_stock_totqy(corp_code, bsns_year, reprt_code)
        if items:
            parsed = _parse_stock_totqy(items)
            sources["issued_shares_common"] = "DART stockTotqySttus.json"
            if parsed["treasury_shares"] is not None:
                sources["treasury_shares"] = "DART stockTotqySttus.json"
        else:
            notes.append("DART stockTotqySttus.json 응답 없음 (status≠000 또는 데이터 0건)")
    else:
        notes.append("corp_code 미제공 — DART fetch skip")

    krx_ohlcv = _fetch_krx_ohlcv(ticker_krx)
    latest_close = krx_ohlcv.get("latest_close_krw")
    latest_date = krx_ohlcv.get("latest_close_date")
    if latest_close is not None:
        sources["latest_close_krw"] = "pykrx KRX OHLCV"
    elif "error" in krx_ohlcv:
        notes.append(f"pykrx fetch 실패: {krx_ohlcv['error']}")

    market_cap = None
    market_cap_t = None
    if latest_close is not None and parsed["issued_shares_common"]:
        market_cap = float(latest_close) * float(parsed["issued_shares_common"])
        market_cap_t = round(market_cap / 1e12, 4)
        sources["market_cap_krw"] = "computed: KRX 종가 × DART 발행주식수"

    notes.append(
        "외인 일별잔고·투자자유형별 매매는 KRX 계정(KRX_ID/KRX_PW) 필요 — "
        "본 v0.2에서 미통합. 페르소나 ★★★ 외인 추세는 '확인되지 않음'으로 처리."
    )

    return TickerMarketSnapshot(
        ticker=ticker_krx,
        company_name=company_name,
        issued_shares_common=parsed["issued_shares_common"],
        issued_shares_preferred=parsed["issued_shares_preferred"],
        treasury_shares=parsed["treasury_shares"],
        distributed_shares=parsed["distributed_shares"],
        latest_close_krw=latest_close,
        latest_close_date=latest_date,
        market_cap_krw=market_cap,
        market_cap_trillion_krw=market_cap_t,
        close_60d_pct_change=krx_ohlcv.get("close_60d_pct_change"),
        close_1y_pct_change=krx_ohlcv.get("close_1y_pct_change"),
        sources=sources,
        notes=notes,
    )


def load_ticker_snapshot(
    cache_path: Path,
    ticker_krx: str,
    company_name: str,
    corp_code: str | None,
    bsns_year: int,
    reprt_code: str = "11011",
    max_age_hours: int = 24,
) -> TickerMarketSnapshot:
    if cache_path.exists():
        age_h = (
            datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
        ).total_seconds() / 3600
        if age_h < max_age_hours:
            try:
                data = json.loads(cache_path.read_text(encoding="utf-8"))
                return TickerMarketSnapshot(**data)
            except (json.JSONDecodeError, TypeError):
                pass

    snap = fetch_ticker_snapshot(
        ticker_krx=ticker_krx,
        company_name=company_name,
        corp_code=corp_code,
        bsns_year=bsns_year,
        reprt_code=reprt_code,
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(asdict(snap), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return snap
