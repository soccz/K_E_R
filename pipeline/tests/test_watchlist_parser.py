"""_watchlist.md 파싱 테스트."""
from pipeline.watchlist_parser import parse_watchlist, find_by_ticker, find_by_name


SAMPLE = """---
name: 워치리스트
---

# 워치리스트 — 코스피 24종목

| # | 기업명 | 티커 (KRX) | corp_code (DART) | 섹터 | 비고 |
|---|---|---|---|---|---|
| 1 | 삼성전자 | 005930 | TBD | 반도체 | 시총 1위 |
| 2 | SK하이닉스 | 000660 | 00164779 | 반도체 | 메모리 순수 |

기타 텍스트.
"""


def test_parse_basic():
    entries = parse_watchlist(SAMPLE)
    assert len(entries) == 2
    assert entries[0].name == "삼성전자"
    assert entries[0].ticker == "005930"
    assert entries[0].corp_code is None
    assert entries[1].corp_code == "00164779"


def test_find_by_ticker():
    entries = parse_watchlist(SAMPLE)
    found = find_by_ticker(entries, "000660")
    assert found is not None
    assert found.name == "SK하이닉스"


def test_find_by_name():
    entries = parse_watchlist(SAMPLE)
    found = find_by_name(entries, "삼성전자")
    assert found is not None
    assert found.ticker == "005930"


def test_full_watchlist_loads():
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "_watchlist.md").read_text(encoding="utf-8")
    entries = parse_watchlist(text)
    assert len(entries) == 24
    names = [e.name for e in entries]
    assert "삼성전자" in names
    assert "한화에어로스페이스" in names
    assert all(e.corp_code is None for e in entries)
