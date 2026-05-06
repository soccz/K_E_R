"""보고서 품질 가드 테스트."""
from pipeline.report_quality import (
    find_report_failure_markers,
    is_usable_report,
    validate_generation_inputs,
)


class _Pack:
    facts = list(range(101))


def test_generation_inputs_fail_on_empty_filings():
    result = validate_generation_inputs({"filings": []}, _Pack())
    assert not result.passed
    assert "0건" in result.failures[0]


def test_generation_inputs_require_xbrl():
    result = validate_generation_inputs(
        {"filings": [{"text": "x" * 6000, "text_chars": 6000}]},
        None,
    )
    assert not result.passed
    assert any("XBRL" in m for m in result.failures)


def test_detects_empty_data_markers():
    markers = find_report_failure_markers(
        "이번 실행에서 DART API가 공시 데이터를 반환하지 않았습니다 (`filings: []`)."
    )
    assert markers


def test_failed_report_is_not_usable(tmp_path):
    report = tmp_path / "00_종합진단.md"
    report.write_text("DART API가 공시 데이터를 반환하지 않았습니다 (`filings: []`).", encoding="utf-8")
    assert not is_usable_report(report)


def test_clean_report_is_usable(tmp_path):
    report = tmp_path / "00_종합진단.md"
    report.write_text("2025 사업보고서와 XBRL 기준으로 작성된 보고서입니다.", encoding="utf-8")
    assert is_usable_report(report)
