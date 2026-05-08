"""분기 잠정실적 자동 수집 테스트 — DART list.json mock."""
from pipeline import quarterly_disclosure as qd


def test_guess_period_end_quarterly_reports():
    assert qd._guess_period_end("1분기보고서", "20260515") == "2026-03-31"
    assert qd._guess_period_end("반기보고서", "20260815") == "2026-06-30"
    assert qd._guess_period_end("3분기보고서", "20261115") == "2026-09-30"


def test_guess_period_end_interim_results():
    # 1월 발표 잠정실적 → 직전 4Q
    assert qd._guess_period_end("연결재무제표기준영업(잠정)실적(공정공시)", "20260128") == "2025-12-31"
    # 4월 발표 잠정실적 → 1Q
    assert qd._guess_period_end("영업(잠정)실적(공정공시)", "20260423") == "2026-03-31"


def test_guess_period_end_unknown():
    assert qd._guess_period_end("기타공시", "20260101") is None


def test_fetch_with_mock_list(monkeypatch):
    """사업보고서(2026-03-17) 이후 1Q 잠정실적·분기보고서 검출."""
    raw_response = {
        "status": "000",
        "total_page": 1,
        "list": [
            {
                "rcept_no": "20260423000001",
                "report_nm": "연결재무제표기준영업(잠정)실적(공정공시)",
                "rcept_dt": "20260423",
            },
            {
                "rcept_no": "20260515000001",
                "report_nm": "분기보고서 (2026.03)",
                "rcept_dt": "20260515",
            },
            {
                "rcept_no": "20260420000001",
                "report_nm": "기타공시",  # 잠정실적 키워드 없음 — skip
                "rcept_dt": "20260420",
            },
        ],
    }

    class _MockClient:
        def list_filings(self, **kwargs):
            return raw_response

    import pipeline.quarterly_disclosure as qdm

    class _MockConfig:
        DART_API_KEY = "test-key"

    monkeypatch.setattr(qdm, "config", _MockConfig, raising=False) if hasattr(qdm, "config") else None
    # 직접 모듈 내부의 import를 monkey patch는 어려우니 DartClient를 mock
    monkeypatch.setattr("pipeline.dart_client.DartClient", lambda: _MockClient())
    # config.DART_API_KEY 활성화
    import pipeline.config as cfg
    monkeypatch.setattr(cfg, "DART_API_KEY", "test-key")

    snap = qd.fetch_quarterly_disclosures(
        company="SK하이닉스",
        corp_code="00164779",
        annual_rcept_dt="20260317",
    )
    assert len(snap.interim_filings) == 2
    # 최신 순
    assert snap.interim_filings[0].rcept_dt == "20260515"
    assert snap.interim_filings[0].likely_period_end == "2026-03-31"
    assert snap.interim_filings[1].rcept_dt == "20260423"
    assert snap.interim_filings[1].likely_period_end == "2026-03-31"
    # days_after 계산 검증
    assert snap.interim_filings[0].days_after_annual > 50  # 03-17 → 05-15 ≈ 59일
    assert snap.sources["interim_filings"] == "DART list.json"


def test_fetch_returns_empty_when_no_interim(monkeypatch):
    class _MockClient:
        def list_filings(self, **kwargs):
            return {"status": "000", "total_page": 1, "list": []}

    monkeypatch.setattr("pipeline.dart_client.DartClient", lambda: _MockClient())
    import pipeline.config as cfg
    monkeypatch.setattr(cfg, "DART_API_KEY", "test-key")

    snap = qd.fetch_quarterly_disclosures(
        company="SK하이닉스",
        corp_code="00164779",
        annual_rcept_dt="20260317",
    )
    assert snap.interim_filings == []
    assert any("0건" in n for n in snap.notes)


def test_to_prompt_dict_carries_persona_marker():
    snap = qd.QuarterlyDisclosure(
        company="SK하이닉스",
        annual_rcept_dt="20260317",
        fetched_at="2026-05-07",
    )
    p = snap.to_prompt_dict()
    assert "08_이번분기변화" in p["usage_rule"]
    assert "owner-valuation" in p["usage_rule"]
    assert "stale" in p["usage_rule"]


def test_fetch_handles_no_api_key(monkeypatch):
    import pipeline.config as cfg
    monkeypatch.setattr(cfg, "DART_API_KEY", None)
    snap = qd.fetch_quarterly_disclosures(
        company="SK하이닉스",
        corp_code="00164779",
        annual_rcept_dt="20260317",
    )
    assert snap.interim_filings == []
    assert any("미설정" in n for n in snap.notes)
