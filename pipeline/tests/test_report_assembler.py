"""report_assembler 테스트 — LLM 호출 없이 합본 구조 검증."""
from pathlib import Path

from pipeline.prompt_builder import DataTimestamps
from pipeline.report_assembler import (
    SECTION_FILES,
    _extract_first_paragraph,
    assemble_report,
)


def test_section_files_match_specs():
    """SECTION_FILES가 prompt_builder.SECTION_SPECS와 일치."""
    from pipeline.prompt_builder import SECTION_SPECS
    assert set(SECTION_FILES) == set(SECTION_SPECS.keys())


def test_extract_first_paragraph_skips_metabox():
    text = """## 01_사업구조진단

> **데이터 기준시점**
> - 작성일: 2026-05-02
> - DART: 2026-05-02

---

### 30초 회사 소개

삼성전자는 한국 최대 전자기업이다. 4개 부문으로 나뉜다.
"""
    para = _extract_first_paragraph(text)
    assert "삼성전자" in para
    assert "데이터 기준시점" not in para


def test_extract_skips_short_lines():
    text = """## section
짧은
조금 더 길지만 50자 미만
정말 충분한 길이의 첫 번째 의미 있는 단락이다 — 50자 이상이라는 게 핵심 조건이고 이걸 만족해야 추출된다.
"""
    para = _extract_first_paragraph(text)
    assert "충분한 길이" in para


def test_assemble_report_basic(tmp_path: Path):
    """LLM 없이 (--skip-owner-summary) 기본 합본 작성."""
    report_dir = tmp_path / "test_company" / "2025-annual"
    report_dir.mkdir(parents=True)
    (report_dir / "01_사업구조진단.md").write_text(
        "## 01_사업구조진단\n\n사업구조 분석 본문 — 충분히 긴 첫 단락 내용이다 ".ljust(80, "."),
        encoding="utf-8",
    )
    (report_dir / "02_재무건강진단.md").write_text(
        "## 02_재무건강진단\n\n재무건강 분석 본문 — 충분히 긴 첫 단락 내용이다 ".ljust(80, "."),
        encoding="utf-8",
    )

    ts = DataTimestamps(
        written_at="2026-05-02",
        dart_query_at="2026-05-02 21:00",
        financial_basis="2025 사업보고서",
        market_price="(미포함)",
        foreign_holding="(미포함)",
        macro_data="(미포함)",
    )

    target = assemble_report(
        report_dir=report_dir,
        company="테스트회사",
        period="2025-annual",
        timestamps=ts,
        headline="간단한 헤드라인",
        write_owner_summary=False,
    )
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert "테스트회사 2025-annual 종합진단" in content
    assert "데이터 기준시점" in content
    assert "01_사업구조진단" in content
    assert "02_재무건강진단" in content
    assert "사업구조 분석 본문" in content
    assert "Owner valuation" in content
