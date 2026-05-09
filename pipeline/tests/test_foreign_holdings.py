"""foreign_holdings 단위 테스트 — DART API 호출은 mock."""
from pipeline import foreign_holdings


def test_classify_korean_corporate():
    # 한글 법인명 → KR
    assert foreign_holdings._classify_nationality("SK스퀘어㈜") == "KR"
    assert foreign_holdings._classify_nationality("국민연금공단") == "KR"


def test_classify_foreign_pattern():
    assert foreign_holdings._classify_nationality("BlackRock, Inc.") == "FOREIGN"
    assert foreign_holdings._classify_nationality("Vanguard Group") == "FOREIGN"
    assert foreign_holdings._classify_nationality("Norges Bank") == "FOREIGN"


def test_classify_unknown():
    assert foreign_holdings._classify_nationality("") == "UNKNOWN"


def test_fetch_with_mock_majorstock(monkeypatch):
    """mock raw → 외국인/국내 분류 확인."""
    raw_items = [
        {
            "repror": "SK스퀘어㈜",
            "stkrt": "20.07",
            "rcept_dt": "2026-03-17",
            "repror_nm_cd_nm": "단순투자",
        },
        {
            "repror": "BlackRock, Inc.",
            "stkrt": "5.42",
            "rcept_dt": "2026-02-01",
            "repror_nm_cd_nm": "단순투자",
        },
        # 같은 holder의 더 오래된 보고 — 무시되어야 함
        {
            "repror": "BlackRock, Inc.",
            "stkrt": "4.99",
            "rcept_dt": "2025-08-01",
            "repror_nm_cd_nm": "단순투자",
        },
    ]
    monkeypatch.setattr(
        foreign_holdings, "_fetch_dart_majorstock", lambda corp_code: raw_items
    )
    # KRX 일별 외인 비중도 mock (실제 호출 차단 — 테스트 격리)
    monkeypatch.setattr(
        foreign_holdings, "_fetch_krx_foreign_holdings", lambda ticker, days=30: []
    )

    snap = foreign_holdings.fetch_foreign_holding_snapshot(
        ticker_krx="000660",
        company_name="SK하이닉스",
        corp_code="00164779",
    )
    assert len(snap.major_holders) == 2  # dedup by holder_name
    foreign = [h for h in snap.major_holders if h.nationality == "FOREIGN"]
    assert len(foreign) == 1
    assert foreign[0].holder_name == "BlackRock, Inc."
    assert foreign[0].holding_pct == 5.42
    assert snap.foreign_major_holders_count == 1
    assert snap.foreign_major_holders_pct_sum == 5.42
    # KRX 호출 모킹으로 빈 리스트 → krx_daily_foreign_pct None
    assert snap.krx_daily_foreign_pct is None
    # KRX 미수집 note 확인
    assert any("KRX" in n for n in snap.notes)


def test_fetch_handles_no_major_holders(monkeypatch):
    monkeypatch.setattr(foreign_holdings, "_fetch_dart_majorstock", lambda c: [])
    monkeypatch.setattr(
        foreign_holdings, "_fetch_krx_foreign_holdings", lambda ticker, days=30: []
    )
    snap = foreign_holdings.fetch_foreign_holding_snapshot(
        ticker_krx="000660",
        company_name="SK하이닉스",
        corp_code="00164779",
    )
    assert snap.major_holders == []
    assert snap.foreign_major_holders_pct_sum is None
    assert any("0건" in n or "5% 미만" in n for n in snap.notes)


def test_to_prompt_dict_contains_persona_marker(monkeypatch):
    monkeypatch.setattr(
        foreign_holdings, "_fetch_krx_foreign_holdings", lambda ticker, days=30: []
    )
    snap = foreign_holdings.fetch_foreign_holding_snapshot(
        ticker_krx="000660",
        company_name="SK하이닉스",
        corp_code=None,
    )
    p = snap.to_prompt_dict()
    assert "★★★" in p["usage_rule"]
    assert "확인되지 않음" in p["usage_rule"]


def test_krx_daily_foreign_holdings_integration(monkeypatch):
    """KRX mock으로 일별 추이 + 5d 변동 산출 검증."""
    krx_history = [
        {"date": "2026-05-08", "holding_pct": 49.40, "holding_shares": 100,
         "listed_shares": 200, "exhaustion_pct": 49.40},
        {"date": "2026-05-07", "holding_pct": 49.62, "holding_shares": 100,
         "listed_shares": 200, "exhaustion_pct": 49.62},
        {"date": "2026-05-06", "holding_pct": 49.37, "holding_shares": 100,
         "listed_shares": 200, "exhaustion_pct": 49.37},
        {"date": "2026-05-04", "holding_pct": 49.25, "holding_shares": 100,
         "listed_shares": 200, "exhaustion_pct": 49.25},
        {"date": "2026-04-30", "holding_pct": 49.28, "holding_shares": 100,
         "listed_shares": 200, "exhaustion_pct": 49.28},
        {"date": "2026-04-29", "holding_pct": 49.18, "holding_shares": 100,
         "listed_shares": 200, "exhaustion_pct": 49.18},
    ]
    monkeypatch.setattr(foreign_holdings, "_fetch_dart_majorstock", lambda c: [])
    monkeypatch.setattr(
        foreign_holdings, "_fetch_krx_foreign_holdings",
        lambda ticker, days=30: krx_history,
    )
    snap = foreign_holdings.fetch_foreign_holding_snapshot(
        "005930", "삼성전자", "00126380"
    )
    assert snap.krx_daily_foreign_pct == 49.40
    # 5영업일 전(=index 5, 49.18) 대비 변동
    assert snap.krx_foreign_pct_change_5d == round(49.40 - 49.18, 3)
    assert len(snap.krx_daily_foreign_history) == 6
    assert "krx_foreign_pct" in snap.sources
