"""cross-section consistency 검증 테스트."""
from pipeline.cross_section_consistency import (
    AuthoritativeFact,
    build_authoritative_facts,
    check_section_against_facts,
    render_violations,
)


def test_market_cap_hallucination_caught():
    """SK하이닉스 02 사례: 시총 1,204조인데 '약 80조원대' 환각 → fail."""
    facts = [
        AuthoritativeFact(
            key="market_cap",
            label="시가총액",
            value_krw=1_204_115_911_710_000.0,
            keywords=("시가총액", "시총"),
            tolerance_pct=0.05,
        )
    ]
    text = "시총(약 80조원대) 대비 3년 누적 FCF 33.4조"
    violations = check_section_against_facts("02", text, facts)
    assert len(violations) == 1
    v = violations[0]
    assert v.fact_key == "market_cap"
    assert v.found_value_krw == 8e13
    assert v.deviation_pct < -90  # 1,204조 → 80조 = -93% 편차


def test_market_cap_correct_passes():
    """정확한 시총 1,204조 인용은 통과."""
    facts = [
        AuthoritativeFact(
            key="market_cap",
            label="시가총액",
            value_krw=1_204_115_911_710_000.0,
            keywords=("시가총액", "시총"),
            tolerance_pct=0.05,
        )
    ]
    text = "시가총액 1,204.12조원에 통째로 살 만한가"
    violations = check_section_against_facts("00", text, facts)
    assert violations == []


def test_inference_marker_does_NOT_skip_authoritative_fact():
    """v0.2 정책 변경: 권위 사실은 추론 마커가 있어도 정확해야.
    페르소나 §3.3 추론 라벨은 *해석·전망·추정*에만 허용 — 1순위 출처가 있는 사실 자체를
    다른 값으로 적는 것은 환각."""
    facts = [
        AuthoritativeFact(
            key="market_cap",
            label="시가총액",
            value_krw=1_204e12,
            keywords=("시총",),
            tolerance_pct=0.05,
        )
    ]
    text = "시총 80조원으로 추정 *(추론 — 옛 시점 기준)*"
    violations = check_section_against_facts("02", text, facts)
    assert len(violations) == 1  # 추론 마커가 있어도 환각은 잡힘


def test_quarterly_oi_hallucination_caught():
    """1Q26 영업이익 37.61조인데 '6.97조' 환각 → fail."""
    facts = [
        AuthoritativeFact(
            key="interim_q_operating_income",
            label="1Q26 잠정 영업이익",
            value_krw=37_610_000_000_000.0,
            keywords=("1Q26 영업이익", "분기 영업이익"),
            tolerance_pct=0.05,
        )
    ]
    text = "1Q26 영업이익 6.97조원이 연환산 시 약 28조 수준이다"
    violations = check_section_against_facts("02", text, facts)
    assert len(violations) >= 1
    assert violations[0].fact_key == "interim_q_operating_income"


def test_combined_jo_eok_pattern_parsed():
    """'97조 1,467억' 같은 결합 패턴이 정확한 값으로 추출되는지."""
    facts = [
        AuthoritativeFact(
            key="revenue",
            label="2025 매출",
            value_krw=97_146_675_000_000.0,
            keywords=("연결 매출",),
            tolerance_pct=0.01,
        )
    ]
    text = "2025년 연결 매출 97조 1,467억원"
    violations = check_section_against_facts("01", text, facts)
    # 결합 패턴이 정확히 매치되면 통과
    assert violations == []


def test_build_facts_skips_none():
    facts = build_authoritative_facts(
        market_cap_krw=1_204e12,
        revenue_krw=None,  # 누락
        operating_income_krw=47.21e12,
        operating_cash_flow_krw=None,
        capex_krw=27.52e12,
    )
    keys = [f.key for f in facts]
    assert "market_cap" in keys
    assert "revenue" not in keys
    assert "operating_income" in keys
    assert "operating_cash_flow" not in keys
    assert "capex" in keys


def test_render_violations_human_readable():
    v = check_section_against_facts(
        "02",
        "시총(약 80조원대) 대비",
        build_authoritative_facts(market_cap_krw=1_204e12, revenue_krw=None,
                                   operating_income_krw=None, operating_cash_flow_krw=None,
                                   capex_krw=None),
    )
    out = render_violations(v)
    assert "FAIL" in out
    assert "시가총액" in out
    assert "80조" in out or "8e+13" in out or "80" in out
