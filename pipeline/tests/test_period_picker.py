"""period_picker.py 단위 테스트."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from pipeline import period_picker


@pytest.fixture
def mock_watchlist(monkeypatch, tmp_path):
    """간단한 3종목 워치리스트 + companies dir 모킹."""
    wl = tmp_path / "_watchlist.md"
    wl.write_text(
        "| # | 기업명 | 티커 (KRX) | corp_code (DART) | 섹터 | 비고 |\n"
        "|---|---|---|---|---|---|\n"
        "| 1 | 삼성전자 | 005930 | 00126380 | 반도체 | x |\n"
        "| 2 | SK하이닉스 | 000660 | 00164779 | 반도체 | x |\n"
        "| 3 | LG화학 | 051910 | 00356361 | 화학 | x |\n",
        encoding="utf-8",
    )
    companies = tmp_path / "companies"
    companies.mkdir()
    monkeypatch.setattr(period_picker.config, "WATCHLIST_PATH", wl)
    monkeypatch.setattr(period_picker.config, "COMPANIES_DIR", companies)
    return companies


def _make_report(companies: Path, name: str, period: str):
    p = companies / name / period
    p.mkdir(parents=True, exist_ok=True)
    (p / "00_종합진단.md").write_text("# 충분한 길이 보고서 더미 텍스트 " * 100, encoding="utf-8")


def test_pick_returns_oldest_unfinished_period(mock_watchlist):
    """2025-annual 마감 지났고 0/3 → 첫 ticker 반환."""
    today = datetime(2026, 5, 9)
    result = period_picker.pick_active_period(today=today)
    assert result is not None
    spec, ticker = result
    assert spec.period_label == "2025-annual"
    assert spec.bsns_year == 2025
    assert spec.reprt_code == "11011"
    assert ticker == "005930"  # 첫 종목


def test_pick_advances_to_next_period_when_current_done(mock_watchlist):
    """2025-annual 3/3 완료 + 5/15 지나면 → 2026-q1 활성."""
    for name in ["삼성전자", "SK하이닉스", "LG화학"]:
        _make_report(mock_watchlist, name, "2025-annual")
    today = datetime(2026, 5, 16)  # 5/15 마감 + 1일
    result = period_picker.pick_active_period(today=today)
    assert result is not None
    spec, ticker = result
    assert spec.period_label == "2026-q1"
    assert spec.bsns_year == 2026
    assert spec.reprt_code == "11013"


def test_pick_skips_period_before_deadline(mock_watchlist):
    """2025-annual 3/3 완료 + 5/15 마감 전 → skip 2026-q1, 다른 PERIOD도 마감 전 → all-done."""
    for name in ["삼성전자", "SK하이닉스", "LG화학"]:
        _make_report(mock_watchlist, name, "2025-annual")
    today = datetime(2026, 5, 9)  # 5/15 마감 전
    result = period_picker.pick_active_period(today=today)
    assert result is None  # 다음 활성 PERIOD까지 대기


def test_pick_returns_none_when_all_periods_done(mock_watchlist):
    """모든 PERIOD 24/24 완료 → None."""
    for spec in period_picker._PERIODS:
        for name in ["삼성전자", "SK하이닉스", "LG화학"]:
            _make_report(mock_watchlist, name, spec.period_label)
    today = datetime(2030, 1, 1)
    result = period_picker.pick_active_period(today=today)
    assert result is None


def test_pick_within_period_returns_first_unfinished(mock_watchlist):
    """2025-annual에서 삼전만 완료 → 두번째 종목 반환."""
    _make_report(mock_watchlist, "삼성전자", "2025-annual")
    today = datetime(2026, 5, 9)
    result = period_picker.pick_active_period(today=today)
    assert result is not None
    spec, ticker = result
    assert spec.period_label == "2025-annual"
    assert ticker == "000660"  # SK하이닉스 (두번째)
