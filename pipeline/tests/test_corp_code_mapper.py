"""corp_code_mapper 테스트 — DART API 호출 없이 XML 파싱 + watchlist 업데이트."""
from pathlib import Path

from pipeline.corp_code_mapper import parse_corp_code_xml, update_watchlist_md


SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<result>
  <list>
    <corp_code>00126380</corp_code>
    <corp_name>삼성전자</corp_name>
    <stock_code>005930</stock_code>
    <modify_date>20240101</modify_date>
  </list>
  <list>
    <corp_code>00164779</corp_code>
    <corp_name>SK하이닉스</corp_name>
    <stock_code>000660</stock_code>
    <modify_date>20240101</modify_date>
  </list>
  <list>
    <corp_code>00999999</corp_code>
    <corp_name>비상장법인</corp_name>
    <stock_code></stock_code>
    <modify_date>20240101</modify_date>
  </list>
</result>
"""


def test_parse_corp_code_xml(tmp_path: Path):
    xml = tmp_path / "CORPCODE.xml"
    xml.write_text(SAMPLE_XML, encoding="utf-8")
    mapping = parse_corp_code_xml(xml)
    assert mapping == {"005930": "00126380", "000660": "00164779"}
    # 비상장은 제외
    assert "" not in mapping


def test_update_watchlist_md(tmp_path: Path):
    wl = tmp_path / "_watchlist.md"
    wl.write_text(
        """---
name: test
---

# 워치리스트

| # | 기업명 | 티커 (KRX) | corp_code (DART) | 섹터 | 비고 |
|---|---|---|---|---|---|
| 1 | 삼성전자 | 005930 | TBD | 반도체 | 시총 1위 |
| 2 | SK하이닉스 | 000660 | TBD | 반도체 | 메모리 |
| 3 | 알수없는주식 | 999999 | TBD | 기타 | 매핑 실패 케이스 |
""",
        encoding="utf-8",
    )

    mapping = {"005930": "00126380", "000660": "00164779"}
    updated, missing = update_watchlist_md(wl, mapping)
    assert updated == 2
    assert missing == ["알수없는주식(999999)"]

    content = wl.read_text(encoding="utf-8")
    assert "00126380" in content
    assert "00164779" in content
    assert "999999 | TBD" in content


def test_real_watchlist_loads():
    """실제 _watchlist.md 24종목 모두 ticker 가지고 있는지."""
    from pipeline import config
    from pipeline.watchlist_parser import parse_watchlist
    text = config.WATCHLIST_PATH.read_text(encoding="utf-8")
    entries = parse_watchlist(text)
    assert len(entries) == 24
    for e in entries:
        assert e.ticker.isdigit() and len(e.ticker) == 6, e.ticker
