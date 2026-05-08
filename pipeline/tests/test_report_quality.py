"""보고서 품질 가드 테스트."""
from pipeline.report_quality import (
    find_inconsistencies,
    find_report_failure_markers,
    is_usable_report,
    validate_generated_text,
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


def test_inconsistency_when_capex_unknown_and_asserted():
    """SK하이닉스 08 사례: capex가 '확인되지 않음'이라 적힌 같은 문서에서
    헤드라인이 '3.4조' 단언 → 충돌 경고."""
    text = (
        "## 04 자본활용\n"
        "| 항목 | 2023 | 2024 |\n"
        "| capex | 확인되지 않음 | 15.95조원 |\n"
        "\n"
        "## 08 헤드라인\n"
        "Capex 전면 가속 — 2년 만에 3.4조 → 27.5조\n"
    )
    findings = find_inconsistencies(text)
    assert any("capex" in f.lower() for f in findings)


def test_no_inconsistency_when_only_unknown():
    text = "지역별 매출 비중은 확인되지 않음"
    assert find_inconsistencies(text) == []


def test_no_inconsistency_when_only_assertion():
    text = "유형자산 취득 27.52조원 [XBRL]"
    assert find_inconsistencies(text) == []


def test_validate_generated_text_emits_warning_for_inconsistency():
    text = (
        "지역별 매출은 확인되지 않음.\n"
        "참고로 지역별 매출 미국향 30조원.\n"  # 같은 키워드 + 단언 + 추론 마커 없음
    )
    result = validate_generated_text(text)
    assert result.passed
    assert any("일관성 충돌" in w for w in result.warnings)


def test_inference_marker_excludes_assertion():
    """v0.2: *(추론)* 마커가 있는 단언은 충돌로 보지 않음."""
    text = (
        "WACC의 정확한 수치는 확인되지 않음.\n"
        "추정 WACC: 약 9~10% *(추론 — 자기자본 비용 모형 가정)*\n"
    )
    findings = find_inconsistencies(text)
    # 추론 마커가 있어 단언 아님 → 충돌 없음
    assert findings == []


def test_window_narrow_avoids_adjacent_paragraph_collision():
    """v0.2: 윈도우 ±60자로 좁힘 — 인접 단락의 다른 항목이 false positive 안 됨."""
    text = (
        "지역별 매출 비중은 사업보고서에서 미분해 → 확인되지 않음.\n"
        "\n"
        "별도 단락 — 연도별 합계 매출은 다음과 같다:\n"
        "2025년 매출 97.1조원\n"
    )
    findings = find_inconsistencies(text)
    # '지역별 매출' 인근 ±60자에 큰 숫자 없음 + 두번째 '매출' 인근에 '확인되지 않음' 없음
    assert all("지역별 매출" not in f for f in findings)


def test_real_collision_still_caught():
    """v0.2 회귀: SK하이닉스 08 'capex 확인되지 않음 vs 헤드라인 3.4조' 같은 진짜 충돌은 여전히 잡음."""
    text = (
        "## 04 자본활용\n"
        "| capex 2023 | 확인되지 않음 |\n"
        "| capex 2024 | 15.95조원 |\n"
        "## 08 헤드라인\n"
        "Capex 전면 가속 — 2년 만에 capex 3.4조 → 27.5조\n"
    )
    findings = find_inconsistencies(text)
    assert any("capex" in f.lower() for f in findings)


def test_future_unknown_does_not_collide_with_past_assertion():
    """v0.3: '2026 capex 가이던스 확인되지 않음'은 '2025 capex 27.5조' 단언과 충돌 아님."""
    text = (
        "2025년 capex는 27.5조원이다 [XBRL].\n"
        "\n"
        "> - 2026년 capex 가이던스: 확인되지 않음 (IR 발언 미공시)\n"
    )
    findings = find_inconsistencies(text)
    assert findings == []


def test_owner_valuation_phrase_not_treated_as_capex_collision():
    """v0.3: '통째로 살' 문구가 capex 충돌과 무관해야 한다 (V2와 별개 — 검사기는 키워드 기반)."""
    text = (
        "2025년 capex 27.5조원.\n"
        "지금 1,204조원에 통째로 살 만한가? 그 가격은 사이클 정점이다.\n"
    )
    findings = find_inconsistencies(text)
    # capex가 단언이지만 미확인이 없음 → 충돌 0
    assert findings == []
