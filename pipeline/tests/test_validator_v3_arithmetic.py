"""V3 산술 검증 단위 테스트."""
from pipeline.validator_v3_arithmetic import (
    _parse_number,
    _parse_tables,
    validate_arithmetic,
    render_arithmetic_failures,
)


# ----- 숫자 파싱 -----

def test_parse_basic_numbers():
    assert _parse_number("123") == 123.0
    assert _parse_number("123.45") == 123.45
    assert _parse_number("1,234") == 1234.0
    assert _parse_number("1,234.56") == 1234.56


def test_parse_korean_negative():
    assert _parse_number("△1.5") == -1.5
    assert _parse_number("△30.11") == -30.11
    assert _parse_number("▼5") == -5.0


def test_parse_signed():
    assert _parse_number("+10.5") == 10.5
    assert _parse_number("-22.3") == -22.3


def test_parse_bold_markdown():
    assert _parse_number("**333.61**") == 333.61
    assert _parse_number("**100%**") == 100.0


def test_parse_percentage_strips_sign():
    assert _parse_number("8.3%") == 8.3
    assert _parse_number("100%") == 100.0


def test_parse_blank_or_dash():
    assert _parse_number("") is None
    assert _parse_number("—") is None
    assert _parse_number("-") is None
    assert _parse_number("·") is None
    assert _parse_number("N/A") is None


# ----- 표 파싱 -----

def test_parse_simple_table():
    text = """
| 부문 | 매출 |
|---|---|
| DX | 100 |
| DS | 50 |
"""
    tables = _parse_tables(text)
    assert len(tables) == 1
    assert tables[0].header.cells == ["부문", "매출"]
    assert len(tables[0].body) == 2


def test_parse_multiple_tables():
    text = """
| A | B |
|---|---|
| 1 | 2 |

기타 텍스트

| X | Y |
|---|---|
| 3 | 4 |
"""
    tables = _parse_tables(text)
    assert len(tables) == 2


# ----- 산술 검증 -----

def test_correct_table_passes():
    text = """
| 부문 | 매출 |
|---|---|
| A | 100 |
| B | 50 |
| **합계** | **150** |
"""
    result = validate_arithmetic(text)
    assert result.passed


def test_table_with_negative_correction_passes():
    text = """
| 부문 | 매출 |
|---|---|
| DX | 187.97 |
| DS | 130.13 |
| SDC | 29.84 |
| Harman | 15.78 |
| 내부거래 제거 | △30.11 |
| **연결 합계** | **333.61** |
"""
    result = validate_arithmetic(text)
    assert result.passed, f"failures: {[f.message for f in result.failures]}"


def test_sum_mismatch_fails():
    text = """
| 부문 | 매출 |
|---|---|
| A | 100 |
| B | 50 |
| **합계** | **200** |
"""
    result = validate_arithmetic(text)
    assert not result.passed
    cats = [f.category for f in result.failures]
    assert "table_sum_mismatch" in cats


def test_percentage_sum_off_fails():
    text = """
| 항목 | 비중 |
|---|---|
| A | 30% |
| B | 30% |
| C | 30% |
"""
    # 30+30+30 = 90, not in 95~105 range -> fail
    result = validate_arithmetic(text)
    assert not result.passed
    cats = [f.category for f in result.failures]
    assert "percentage_sum_off" in cats


def test_percentage_sum_within_tolerance_passes():
    text = """
| 항목 | 비중 |
|---|---|
| A | 33.4% |
| B | 33.3% |
| C | 33.3% |
"""
    result = validate_arithmetic(text)
    assert result.passed


def test_mixed_columns_handled():
    text = """
| 부문 | 매출 (조원) | 비중 |
|---|---|---|
| A | 100 | 50% |
| B | 100 | 50% |
| **합계** | **200** | **100%** |
"""
    result = validate_arithmetic(text)
    assert result.passed


def test_yoy_change_table_no_total_no_check():
    text = """
| 부문 | 2023 | 2024 | 변화 |
|---|---|---|---|
| A | 100 | 110 | +10% |
| B | 50 | 45 | -10% |
"""
    # No total row, mixed columns — should pass
    result = validate_arithmetic(text)
    assert result.passed


def test_real_samsung_table_4_does_not_false_fail():
    """Table 4 같은 케이스 — 5행 합 ≈ 합계행, 다만 라벨이 '수출 합계'로 잘못됨.
    V3는 산술만 보므로 통과해야 한다 (라벨 의미는 V2 영역)."""
    text = """
| 지역 | 2025년 (조원) | 비중 |
|---|---|---|
| 내수 | 21.7 | 8.3% |
| 미주 | 67.9 | 26.1% |
| 유럽 | 31.2 | 12.0% |
| 아시아·아프리카 | 45.7 | 17.6% |
| 중국 | 71.6 | 27.5% |
| **수출 합계** | **238.0** | **91.7%** |
"""
    result = validate_arithmetic(text)
    # 5 detail row sum = 238.1 vs total 238.0 (within tolerance)
    # pct sum = 91.5 vs total 91.7 (within tolerance)
    assert result.passed, f"failures: {[f.message for f in result.failures]}"


def test_hallucinated_total_fails():
    """LLM이 합계 숫자를 환각한 경우 — 행 합과 명백히 다름."""
    text = """
| 부문 | 영업이익 (조원) |
|---|---|
| DX | 12.85 |
| DS | 24.86 |
| SDC | 4.12 |
| Harman | 1.53 |
| **합계** | **99.99** |
"""
    # row sum = 43.36, total = 99.99 -> fail
    result = validate_arithmetic(text)
    assert not result.passed


def test_render_failures_actionable():
    text = """
| 부문 | 매출 |
|---|---|
| A | 100 |
| B | 50 |
| **합계** | **999** |
"""
    result = validate_arithmetic(text)
    feedback = render_arithmetic_failures(result)
    assert "table_sum_mismatch" in feedback
    assert "999" in feedback or "150" in feedback


def test_empty_text_passes():
    assert validate_arithmetic("").passed
    assert validate_arithmetic("그냥 텍스트, 표 없음").passed


# ----- false fail 방지 (실제 보고서에서 발견된 케이스) -----

def test_margin_rate_column_not_summed():
    """영업이익률 같은 *율* 칼럼은 가중평균이 정상 — 합산 검증 skip."""
    text = """
| 부문 | 매출 | 영업이익률 |
|---|---|---|
| DX | 187.97 | 6.8% |
| DS | 130.13 | 19.1% |
| SDC | 29.84 | 13.8% |
| Harman | 15.78 | 9.7% |
| 내부거래 제거 | △30.11 | — |
| **연결 합계** | **333.61** | **13.1%** |
"""
    # 매출은 333.61로 합 일치, 율은 합 49.4 vs 13.1이지만 *율 칼럼은 검증 skip*
    result = validate_arithmetic(text)
    assert result.passed, f"failures: {[f.message for f in result.failures]}"


def test_yoy_change_column_not_summed():
    """변화율(YoY) 칼럼은 합산 무의미."""
    text = """
| 제품 | 2024년 | 2025년 | YoY 변화 |
|---|---|---|---|
| 스마트폰 | 114.4 | 126.5 | +10.6% |
| TV | 30.9 | 30.9 | +0.0% |
| 메모리 | 84.5 | 104.1 | +23.2% |
"""
    result = validate_arithmetic(text)
    assert result.passed, f"failures: {[f.message for f in result.failures]}"


def test_market_share_column_not_summed():
    """서로 다른 시장의 한 회사 점유율 칼럼은 합산 무의미."""
    text = """
| 제품 | 2023년 | 2024년 | 2025년 |
|---|---|---|---|
| TV (점유율) | 30.1% | 28.3% | 29.1% |
| 스마트폰 (점유율) | 19.7% | 18.3% | 19.2% |
| DRAM (점유율) | 42.2% | 41.5% | 34.0% |
"""
    # 헤더에 "%"는 있지만 행 라벨이 다른 시장 — 합산 무의미
    # 합계행 없으니 skip되어야
    result = validate_arithmetic(text)
    assert result.passed, f"failures: {[f.message for f in result.failures]}"


def test_explicit_share_column_summed():
    """헤더에 명시적 '비중'이 들어가면 합 100% 검증."""
    text = """
| 부문 | 매출 비중 |
|---|---|
| A | 50% |
| B | 30% |
| C | 5% |
"""
    # 합 = 85%, 비중 칼럼 → fail
    result = validate_arithmetic(text)
    assert not result.passed
    cats = [f.category for f in result.failures]
    assert "percentage_sum_off" in cats


def test_explicit_share_column_passing():
    """비중 합 100±5 → pass."""
    text = """
| 부문 | 매출 비중 |
|---|---|
| A | 50% |
| B | 30% |
| C | 20% |
"""
    result = validate_arithmetic(text)
    assert result.passed


def test_construction_ratio_column_not_summed():
    """'구성비' 단어는 합산 검증 ON, '구성률'은 OFF."""
    summable = """
| 항목 | 구성비 |
|---|---|
| A | 50% |
| B | 50% |
"""
    assert validate_arithmetic(summable).passed

    not_summable = """
| 항목 | 회전율 |
|---|---|
| A | 5.0 |
| B | 7.2 |
| C | 12.1 |
"""
    assert validate_arithmetic(not_summable).passed
