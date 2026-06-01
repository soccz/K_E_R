"""DART 검색 매치 로직 회귀 방지 — 2026-q1 0건 fail 같은 사고 차단."""
from __future__ import annotations

from pipeline.dart_client import DartClient, FilingMeta


class _MockDart(DartClient):
    """list_filings를 mock해서 매치 로직만 테스트."""

    def __init__(self, mock_items: list[dict]):
        # DartClient.__init__ 호출 안 함 (DART_API_KEY 불필요)
        self._mock_items = mock_items

    def list_filings(self, **kwargs):
        return {"list": self._mock_items, "total_page": 1}


# DART 실제 등록 보고서 이름 샘플 (2025~2026 confirmed)
SAMPLE_FILINGS = [
    {"rcept_no": "20260310000001", "rcept_dt": "20260310", "report_nm": "사업보고서 (2025.12)"},
    {"rcept_no": "20260515002181", "rcept_dt": "20260515", "report_nm": "분기보고서 (2026.03)"},
    {"rcept_no": "20260814000001", "rcept_dt": "20260814", "report_nm": "반기보고서 (2026.06)"},
    {"rcept_no": "20261114000001", "rcept_dt": "20261114", "report_nm": "분기보고서 (2026.09)"},
    {"rcept_no": "20260313001226", "rcept_dt": "20260313", "report_nm": "[첨부정정]사업보고서 (2025.12)"},
    {"rcept_no": "99999", "rcept_dt": "20260601", "report_nm": "기타공시"},  # noise
]


def test_annual_matches_사업보고서():
    """REPRT_CODE_ANNUAL=11011 → '사업보고서' 매치."""
    client = _MockDart(SAMPLE_FILINGS)
    results = client.find_periodic_reports("00126380", 2025, "11011")
    names = [r.report_nm for r in results]
    assert "사업보고서 (2025.12)" in names
    assert "[첨부정정]사업보고서 (2025.12)" in names  # 정정공시도 매치
    assert "분기보고서 (2026.03)" not in names  # 분기는 안 잡힘
    assert "반기보고서 (2026.06)" not in names


def test_q1_matches_분기보고서_03():
    """REPRT_CODE_Q1=11013 → '분기보고서 (YYYY.03)' 매치.

    REGRESSION GUARD: 이전엔 '1분기보고서' 검색해서 매치 0건.
    """
    client = _MockDart(SAMPLE_FILINGS)
    results = client.find_periodic_reports("00126380", 2026, "11013")
    names = [r.report_nm for r in results]
    assert "분기보고서 (2026.03)" in names, f"1Q26 매치 실패! names={names}"
    assert "분기보고서 (2026.09)" not in names  # 3Q 안 잡힘
    assert "반기보고서 (2026.06)" not in names


def test_h1_matches_반기보고서():
    """REPRT_CODE_H1=11012 → '반기보고서' 매치."""
    client = _MockDart(SAMPLE_FILINGS)
    results = client.find_periodic_reports("00126380", 2026, "11012")
    names = [r.report_nm for r in results]
    assert "반기보고서 (2026.06)" in names
    assert "분기보고서 (2026.03)" not in names  # 분기는 안 잡힘


def test_q3_matches_분기보고서_09():
    """REPRT_CODE_Q3=11014 → '분기보고서 (YYYY.09)' 매치."""
    client = _MockDart(SAMPLE_FILINGS)
    results = client.find_periodic_reports("00126380", 2026, "11014")
    names = [r.report_nm for r in results]
    assert "분기보고서 (2026.09)" in names
    assert "분기보고서 (2026.03)" not in names  # 1Q 안 잡힘


def test_year_filter_excludes_other_years():
    """bsns_year=2026이면 2025 분기보고서는 매치 안 됨."""
    mixed = SAMPLE_FILINGS + [
        {"rcept_no": "20250515", "rcept_dt": "20250515", "report_nm": "분기보고서 (2025.03)"},
    ]
    client = _MockDart(mixed)
    results = client.find_periodic_reports("00126380", 2026, "11013")
    names = [r.report_nm for r in results]
    assert "분기보고서 (2026.03)" in names
    assert "분기보고서 (2025.03)" not in names  # 다른 연도 X


def test_empty_when_no_match():
    """일치하는 보고서 없으면 빈 리스트."""
    client = _MockDart([
        {"rcept_no": "1", "rcept_dt": "20260101", "report_nm": "기타공시"},
    ])
    results = client.find_periodic_reports("00126380", 2025, "11011")
    assert results == []
