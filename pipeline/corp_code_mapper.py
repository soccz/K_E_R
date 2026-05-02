"""DART corpCode.xml → ticker(stock_code) → corp_code 매핑.

DART의 회사 마스터 (전체 상장 + 기타법인 ~10만개)에서 워치리스트의 24종목만 추출.
한 번 받아서 _watchlist.md의 TBD 칼럼을 자동으로 채운다.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from pipeline.dart_client import DartClient
from pipeline.watchlist_parser import WatchlistEntry, parse_watchlist


def parse_corp_code_xml(xml_path: Path) -> dict[str, str]:
    """CORPCODE.xml → {stock_code(KRX 6자리): corp_code(DART 8자리)}.

    상장사만 (stock_code 빈 값은 비상장 → 제외).
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    mapping: dict[str, str] = {}
    for company in root.findall("list"):
        stock_code = (company.findtext("stock_code") or "").strip()
        corp_code = (company.findtext("corp_code") or "").strip()
        if stock_code and corp_code:
            mapping[stock_code] = corp_code
    return mapping


def fetch_corp_code_mapping(client: DartClient, cache_dir: Path) -> dict[str, str]:
    """DART에서 corpCode.xml 받아 매핑 생성. 캐시되어 있으면 재사용."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    xml_path = cache_dir / "CORPCODE.xml"
    if not xml_path.exists():
        client.download_corp_code_zip(cache_dir)
    return parse_corp_code_xml(xml_path)


def update_watchlist_md(watchlist_path: Path, mapping: dict[str, str]) -> tuple[int, list[str]]:
    """_watchlist.md의 TBD 칼럼을 실제 corp_code로 치환.

    반환: (업데이트된 행 수, 매핑 못 찾은 ticker 목록)
    """
    text = watchlist_path.read_text(encoding="utf-8")
    entries = parse_watchlist(text)
    updated = 0
    missing: list[str] = []
    new_text = text

    for entry in entries:
        if entry.corp_code is not None:
            continue
        cc = mapping.get(entry.ticker)
        if cc is None:
            missing.append(f"{entry.name}({entry.ticker})")
            continue
        # Replace " | TBD |" only in the row containing this ticker
        # Match full row pattern to be safe
        old_marker = f"| {entry.ticker} | TBD |"
        new_marker = f"| {entry.ticker} | {cc} |"
        if old_marker in new_text:
            new_text = new_text.replace(old_marker, new_marker, 1)
            updated += 1

    watchlist_path.write_text(new_text, encoding="utf-8")
    return updated, missing
