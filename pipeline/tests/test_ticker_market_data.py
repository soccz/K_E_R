"""ticker_market_data 단위 테스트 — DART(발행주식수) + KRX OHLCV(종가) 통합."""
from dataclasses import asdict

from pipeline import ticker_market_data


def test_snapshot_dataclass_serializable():
    snap = ticker_market_data.TickerMarketSnapshot(
        ticker="000660",
        company_name="SK하이닉스",
        issued_shares_common=728_002_365,
        issued_shares_preferred=None,
        treasury_shares=26_310_845,
        distributed_shares=701_691_520,
        latest_close_krw=1_654_000.0,
        latest_close_date="2026-05-07",
        market_cap_krw=1_654_000.0 * 728_002_365,
        market_cap_trillion_krw=round(1_654_000.0 * 728_002_365 / 1e12, 4),
        close_60d_pct_change=12.5,
        close_1y_pct_change=85.0,
        sources={"issued_shares_common": "DART", "latest_close_krw": "pykrx"},
        notes=[],
    )
    d = asdict(snap)
    assert d["market_cap_trillion_krw"] is not None
    prompt = snap.to_prompt_dict()
    assert prompt["latest_close_krw"] == 1_654_000.0
    assert "market_cap_trillion_krw" in prompt
    assert "차트·이평선·기술적 분석 톤은 금지" in prompt["usage_rule"]


def test_parse_stock_totqy_picks_common_and_treasury():
    items = [
        {
            "se": "보통주",
            "istc_totqy": "728,002,365",
            "tesstk_co": "26,310,845",
            "distb_stock_co": "701,691,520",
        },
        {"se": "우선주", "istc_totqy": "0"},
    ]
    parsed = ticker_market_data._parse_stock_totqy(items)
    assert parsed["issued_shares_common"] == 728_002_365
    assert parsed["treasury_shares"] == 26_310_845


def test_parse_stock_totqy_handles_missing_fields():
    items = [{"se": "보통주", "istc_totqy": "x"}]
    parsed = ticker_market_data._parse_stock_totqy(items)
    assert parsed["issued_shares_common"] is None


def test_fetch_with_mocks_computes_market_cap(monkeypatch):
    """DART 발행주식수 + KRX 종가 → 시가총액 자동 계산."""
    raw = [
        {
            "se": "보통주",
            "istc_totqy": "728,002,365",
            "tesstk_co": "26,310,845",
            "distb_stock_co": "701,691,520",
        }
    ]
    monkeypatch.setattr(ticker_market_data, "_fetch_dart_stock_totqy", lambda *a, **kw: raw)
    monkeypatch.setattr(
        ticker_market_data,
        "_fetch_krx_ohlcv",
        lambda t: {
            "latest_close_krw": 200_000.0,
            "latest_close_date": "2026-05-07",
            "close_60d_pct_change": 12.5,
            "close_1y_pct_change": 85.0,
        },
    )

    snap = ticker_market_data.fetch_ticker_snapshot(
        ticker_krx="000660",
        company_name="SK하이닉스",
        corp_code="00164779",
        bsns_year=2025,
    )
    assert snap.issued_shares_common == 728_002_365
    assert snap.latest_close_krw == 200_000.0
    expected_cap = 200_000.0 * 728_002_365
    assert abs(snap.market_cap_krw - expected_cap) < 1.0
    assert 140 < snap.market_cap_trillion_krw < 150
    assert snap.sources["market_cap_krw"].startswith("computed")
    assert snap.close_60d_pct_change == 12.5


def test_fetch_handles_krx_failure_keeps_dart(monkeypatch):
    """KRX 실패해도 DART 발행주식수는 살림. 시총만 None."""
    raw = [{"se": "보통주", "istc_totqy": "728,002,365", "tesstk_co": "0", "distb_stock_co": "0"}]
    monkeypatch.setattr(ticker_market_data, "_fetch_dart_stock_totqy", lambda *a, **kw: raw)
    monkeypatch.setattr(
        ticker_market_data, "_fetch_krx_ohlcv", lambda t: {"error": "no network"}
    )

    snap = ticker_market_data.fetch_ticker_snapshot(
        ticker_krx="000660",
        company_name="SK하이닉스",
        corp_code="00164779",
        bsns_year=2025,
    )
    assert snap.issued_shares_common == 728_002_365
    assert snap.latest_close_krw is None
    assert snap.market_cap_krw is None
    assert any("pykrx" in n for n in snap.notes)


def test_fetch_handles_dart_failure_keeps_krx(monkeypatch):
    """DART 실패해도 KRX 종가만 채우고 시총 None."""
    monkeypatch.setattr(ticker_market_data, "_fetch_dart_stock_totqy", lambda *a, **kw: [])
    monkeypatch.setattr(
        ticker_market_data,
        "_fetch_krx_ohlcv",
        lambda t: {"latest_close_krw": 200_000.0, "latest_close_date": "2026-05-07"},
    )

    snap = ticker_market_data.fetch_ticker_snapshot(
        ticker_krx="000660",
        company_name="SK하이닉스",
        corp_code="00164779",
        bsns_year=2025,
    )
    assert snap.issued_shares_common is None
    assert snap.latest_close_krw == 200_000.0
    assert snap.market_cap_krw is None  # 발행주식수 없으면 계산 불가


def test_foreign_holdings_placeholder_note():
    """외인 일별잔고는 KRX 계정 필요 — note로 명시."""
    import unittest.mock as mock

    with mock.patch.object(ticker_market_data, "_fetch_dart_stock_totqy", return_value=[]):
        with mock.patch.object(ticker_market_data, "_fetch_krx_ohlcv", return_value={"error": "n/a"}):
            snap = ticker_market_data.fetch_ticker_snapshot(
                "000660", "SK하이닉스", "00164779", 2025
            )
    assert any("외인 일별잔고" in n and "KRX" in n for n in snap.notes)
