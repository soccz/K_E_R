"""다음 티커 선정 테스트."""
import sys

from pipeline import config
from pipeline.pick_next_ticker import main


WATCHLIST = """| # | 기업명 | 티커 (KRX) | corp_code (DART) | 섹터 | 비고 |
|---|---|---|---|---|---|
| 1 | A회사 | 000001 | 00000001 | 테스트 | 첫째 |
| 2 | B회사 | 000002 | 00000002 | 테스트 | 둘째 |
"""


def test_pick_next_ignores_failed_existing_report(tmp_path, monkeypatch, capsys):
    watchlist = tmp_path / "_watchlist.md"
    watchlist.write_text(WATCHLIST, encoding="utf-8")
    companies = tmp_path / "companies"
    failed = companies / "A회사" / "2025-annual" / "00_종합진단.md"
    failed.parent.mkdir(parents=True)
    failed.write_text("DART API가 공시 데이터를 반환하지 않았습니다 (`filings: []`).", encoding="utf-8")

    monkeypatch.setattr(config, "WATCHLIST_PATH", watchlist)
    monkeypatch.setattr(config, "COMPANIES_DIR", companies)
    monkeypatch.setattr(sys, "argv", ["pick_next_ticker", "--period", "2025-annual"])

    assert main() == 0
    assert capsys.readouterr().out.strip() == "000001"


def test_pick_next_skips_usable_report(tmp_path, monkeypatch, capsys):
    watchlist = tmp_path / "_watchlist.md"
    watchlist.write_text(WATCHLIST, encoding="utf-8")
    companies = tmp_path / "companies"
    usable = companies / "A회사" / "2025-annual" / "00_종합진단.md"
    usable.parent.mkdir(parents=True)
    usable.write_text("2025 사업보고서와 XBRL 기준으로 작성된 보고서입니다.", encoding="utf-8")

    monkeypatch.setattr(config, "WATCHLIST_PATH", watchlist)
    monkeypatch.setattr(config, "COMPANIES_DIR", companies)
    monkeypatch.setattr(sys, "argv", ["pick_next_ticker", "--period", "2025-annual"])

    assert main() == 0
    assert capsys.readouterr().out.strip() == "000002"
