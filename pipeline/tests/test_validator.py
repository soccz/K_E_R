"""validator 단위 테스트. 이게 통과하면 시스템의 출처 검증이 작동한다는 신호."""
from pipeline.validator import (
    validate_section,
    validate_assembled_report,
    format_failures_for_retry,
)


CLEAN_SECTION = """## 01_사업구조진단

삼성전자는 메모리 70%, 비메모리 20%, 디스플레이 10% 매출 구조다 [사업보고서 2025, 삼성전자, 세그먼트 정보].

비유: 이 회사 매출 구조는 균형 잡힌 농장이라기보다 단일 작물 의존도가 높은 농가에 가깝다.

이번 회 등장 용어: 세그먼트
"""


CLEAN_ASSEMBLED = """# 삼성전자 2026-Q1 종합진단

> **데이터 기준시점**
> - 작성일: 2026-05-02
> - DART 조회: 2026-05-02 21:10 KST

본문 [공시, 2026-05-02, 삼성전자].

비유: 이 회사는 거대한 단일 작물 농가에 가깝다.
"""


def test_clean_section_passes():
    result = validate_section(CLEAN_SECTION, "01_사업구조진단")
    assert result.passed
    assert not result.failures


def test_forbidden_phrase_fails():
    text = "보도에 따르면 삼성전자가 신사업을 검토 중이다."
    result = validate_section(text, "01")
    assert not result.passed
    cats = [v.category for v in result.failures]
    assert "vague_source" in cats


def test_alleged_phrase_fails():
    text = "회사는 신규 capex를 늘릴 것으로 알려져 있다."
    result = validate_section(text, "01")
    assert not result.passed


def test_industry_insider_phrase_fails():
    text = "업계 관계자에 따르면 신제품 출시는 2분기다."
    result = validate_section(text, "01")
    assert not result.passed


def test_inference_marker_present_passes_speculation():
    text = """## 01

메모리 가격 회복 모멘텀이 2Q에도 이어질 것으로 보인다 *(추론 — 1Q 출하량 증가율과 컨퍼런스콜 톤에서 유추)*.

비유: 농부가 봄비를 본 직후의 기대와 비슷하다.

이번 회 등장 용어: 모멘텀
"""
    result = validate_section(text, "01")
    assert result.passed


def test_speculation_without_marker_fails():
    text = "메모리 가격 회복 모멘텀이 2Q에도 이어질 것으로 보인다."
    result = validate_section(text, "01")
    assert not result.passed
    cats = [v.category for v in result.failures]
    assert "missing_inference_marker" in cats


def test_speculation_with_inline_inference_passes():
    text = "메모리 가격이 회복될 것으로 예상된다 [추론 — 1Q 출하량 데이터 기반]."
    result = validate_section(text, "01")
    assert not any(
        v.category == "missing_inference_marker" for v in result.failures
    )


def test_assembled_requires_timestamp_box():
    text = "# 헤드라인\n본문..."
    result = validate_assembled_report(text)
    assert not result.passed
    cats = [v.category for v in result.failures]
    assert "missing_timestamp_box" in cats


def test_assembled_with_timestamp_passes():
    result = validate_assembled_report(CLEAN_ASSEMBLED)
    assert result.passed


def test_warnings_for_missing_glossary_meta():
    text = """## 01_사업구조진단

본문 [출처, 날짜].

비유: 어떤 어떤 것에 가깝다.
"""
    result = validate_section(text, "01")
    assert result.passed
    cats = [v.category for v in result.warnings]
    assert "missing_glossary_meta" in cats


def test_warnings_for_missing_analogy():
    text = """## 01

본문 [출처, 날짜].

이번 회 등장 용어: A
"""
    result = validate_section(text, "01")
    cats = [v.category for v in result.warnings]
    assert "missing_analogy" in cats


def test_retry_feedback_is_actionable():
    text = "보도에 따르면 회사가 신사업을 한다."
    result = validate_section(text, "01")
    feedback = format_failures_for_retry(result)
    assert "vague_source" in feedback
    assert "보도에 따르면" in feedback
    assert "재작성" in feedback or "다시 작성" in feedback


def test_inference_marker_does_not_excuse_vague_source():
    text = "보도에 따르면 *(추론)* 회사가 신사업을 한다."
    result = validate_section(text, "01")
    assert not result.passed
