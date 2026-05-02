"""site_renderer 단위 테스트."""
from pathlib import Path

from pipeline.site_renderer import (
    _extract_one_liner,
    _period_to_friendly,
    _slugify_for_toc,
    _build_toc,
    _file_needs_rerender,
    discover_reports,
    render_all,
)


def test_period_to_friendly():
    assert _period_to_friendly("2025-annual") == "사업보고서 (2025)"
    assert _period_to_friendly("2025-H1") == "반기보고서 (2025)"
    assert _period_to_friendly("2026-Q1") == "1분기보고서 (2026)"
    assert _period_to_friendly("2026-Q3") == "3분기보고서 (2026)"
    assert _period_to_friendly("foobar") == "foobar"


def test_slugify_unicode_preserves_korean():
    assert _slugify_for_toc("01_사업구조진단") == "01_사업구조진단"
    assert _slugify_for_toc("30초 회사 소개") == "30초-회사-소개"


def test_extract_one_liner_skips_metabox():
    md = """## 01_test

> **데이터 기준시점**
> - 작성일: 2026-05-02

---

### 30초 회사 소개

삼성전자는 1969년 설립된 한국 대표 전자기업이다. 2025년 매출 333조원.

추가 단락.
"""
    summary = _extract_one_liner(md)
    assert "삼성전자" in summary
    assert "1969" in summary
    assert "데이터 기준시점" not in summary


def test_extract_one_liner_skips_toc_links():
    md = """# 종합진단

## 목차

- [01_사업구조진단](#01_사업구조진단)
- [02_재무건강진단](#02_재무건강진단)

## 본문

진짜 본문 단락이다 — 이게 추출되어야 한다 (충분한 길이).
"""
    summary = _extract_one_liner(md)
    assert "진짜 본문" in summary
    assert "[01_" not in summary  # markdown link syntax should not appear


def test_extract_one_liner_prefers_30sec_intro():
    md = """# 보고서

## 목차
- [a](#a)

## 30초 회사 소개

특별히 추출되어야 할 회사 소개 단락이다 — 충분한 길이로 작성됨.

## 다른 섹션

다른 단락.
"""
    summary = _extract_one_liner(md)
    assert "특별히 추출" in summary


def test_build_toc_extracts_h2_h3():
    md = """# Title

## 1번 섹션

본문

### 1.1 하위
본문
### 1.2 하위
본문

## 2번 섹션
"""
    toc = _build_toc(md)
    assert "1번 섹션" in toc
    assert "2번 섹션" in toc
    assert "1.1 하위" in toc
    assert 'href="#1번-섹션"' in toc or 'href="#1번 섹션"' in toc


def test_build_toc_returns_empty_for_no_headers():
    assert _build_toc("just some text\nno headers") == ""


def test_file_needs_rerender(tmp_path: Path):
    src = tmp_path / "src.md"
    dst = tmp_path / "dst.html"
    src.write_text("# hello", encoding="utf-8")
    # dst doesn't exist → needs rerender
    assert _file_needs_rerender(src, dst)
    # write dst, then src older
    dst.write_text("<html/>", encoding="utf-8")
    import os, time
    time.sleep(0.05)
    src.touch()  # src newer than dst → needs rerender
    assert _file_needs_rerender(src, dst)
    # Now make dst newer
    time.sleep(0.05)
    dst.touch()
    assert not _file_needs_rerender(src, dst)


def test_discover_reports_excludes_v2_warnings(tmp_path: Path):
    """v2_warnings.md 파일은 entry로 picked up되지 않아야."""
    company_dir = tmp_path / "회사A" / "2025-annual"
    company_dir.mkdir(parents=True)
    (company_dir / "00_종합진단.md").write_text("# Test\n\n진짜 본문 단락 충분한 길이.", encoding="utf-8")
    (company_dir / "01_사업구조진단.v2_warnings.md").write_text("# warnings", encoding="utf-8")
    discovered = discover_reports(tmp_path)
    assert "회사A" in discovered
    assert len(discovered["회사A"]) == 1
    assert discovered["회사A"][0].md_path.name == "00_종합진단.md"


def test_discover_reports_falls_back_to_01_if_no_assembled(tmp_path: Path):
    """합본 없으면 01_사업구조진단으로."""
    company_dir = tmp_path / "회사A" / "2025-annual"
    company_dir.mkdir(parents=True)
    (company_dir / "01_사업구조진단.md").write_text("# Test\n\n본문 단락 충분한 길이.", encoding="utf-8")
    discovered = discover_reports(tmp_path)
    assert discovered["회사A"][0].md_path.name == "01_사업구조진단.md"
    assert "(부분)" in discovered["회사A"][0].title


def test_discover_reports_skips_empty_periods(tmp_path: Path):
    """000_종합진단도 01도 없는 빈 period는 entry 없음."""
    company_dir = tmp_path / "회사A" / "2025-annual"
    company_dir.mkdir(parents=True)
    (company_dir / "02_재무건강진단.md").write_text("# only this", encoding="utf-8")
    discovered = discover_reports(tmp_path)
    assert "회사A" not in discovered


def test_render_all_full_pipeline(tmp_path: Path):
    """end-to-end: companies/ + watchlist → site/."""
    src = tmp_path / "companies" / "삼성전자" / "2025-annual"
    src.mkdir(parents=True)
    (src / "00_종합진단.md").write_text("""# 삼성전자 2025-annual 종합진단

> **데이터 기준시점**
> - 작성일: 2026-05-02

## 30초 회사 소개

삼성전자는 한국 최대 전자기업이다 — 충분히 긴 첫 단락이다.

## 사업구조

세그먼트별 매출 분석.
""", encoding="utf-8")

    watchlist = tmp_path / "_watchlist.md"
    watchlist.write_text("""---
name: test
---

# 워치리스트

| # | 기업명 | 티커 (KRX) | corp_code (DART) | 섹터 | 비고 |
|---|---|---|---|---|---|
| 1 | 삼성전자 | 005930 | TBD | 반도체 | 시총 1위 |
| 2 | SK하이닉스 | 000660 | TBD | 반도체 | 메모리 |
""", encoding="utf-8")

    site = tmp_path / "site"
    companies_dir = tmp_path / "companies"
    n_c, n_total, n_rendered = render_all(companies_dir, site, watchlist_path=watchlist)
    assert n_c == 1
    assert n_total == 1
    assert n_rendered == 1

    # 마스터 인덱스 + 회사 인덱스 + 보고서 본문
    assert (site / "index.html").exists()
    assert (site / "삼성전자" / "index.html").exists()
    assert (site / "삼성전자" / "2025-annual" / "index.html").exists()

    # 마스터 인덱스 — 24 placeholder가 아닌 1+1=2 entries (워치리스트 기준)
    master = (site / "index.html").read_text(encoding="utf-8")
    assert "삼성전자" in master
    assert "SK하이닉스" in master  # placeholder
    assert "추적 중" in master       # placeholder badge

    # 회사 인덱스 — 정렬 토글
    company_html = (site / "삼성전자" / "index.html").read_text(encoding="utf-8")
    assert "최신순" in company_html
    assert "과거순" in company_html
    assert "kerSort" in company_html

    # 보고서 본문 — TOC + 본문
    report_html = (site / "삼성전자" / "2025-annual" / "index.html").read_text(encoding="utf-8")
    assert "30초 회사 소개" in report_html
    assert 'id="30초-회사-소개"' in report_html  # slugify_unicode anchor
    assert "report-toc" in report_html  # sidebar
    assert "toc-fab" in report_html  # mobile drawer button


def test_incremental_skips_unchanged(tmp_path: Path):
    """incremental=True면 mtime 안 바뀐 MD는 다시 렌더 안 함."""
    src = tmp_path / "companies" / "회사A" / "2025-annual"
    src.mkdir(parents=True)
    (src / "00_종합진단.md").write_text("# Test\n\n본문 단락 충분한 길이.", encoding="utf-8")

    site = tmp_path / "site"
    companies_dir = tmp_path / "companies"
    _, _, rendered_first = render_all(companies_dir, site)
    assert rendered_first == 1

    _, _, rendered_second = render_all(companies_dir, site, incremental=True)
    assert rendered_second == 0  # unchanged
