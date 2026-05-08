"""V2 numeric validator 단위 테스트."""
from dataclasses import dataclass

from pipeline.validator_v2_numeric import (
    extract_numeric_claims,
    validate_numeric_claims,
    render_numeric_failures_for_retry,
)


# ----- mock SourcePack for testing -----

@dataclass
class _MockFact:
    concept: str
    value: float
    period_start: str | None = "2025-01-01"
    period_end: str | None = "2025-12-31"

    @property
    def period_type(self):
        return "duration"


class _MockPack:
    def __init__(self, facts):
        self._facts = facts

    @property
    def facts(self):
        return self._facts

    def label_for(self, concept):
        return concept.split(":")[-1]

    def find_value(self, value, tolerance_pct=0.005):
        tol = max(abs(value) * tolerance_pct, 1.0)
        return [f for f in self._facts if abs(f.value - value) <= tol]

    def find_with_scales(self, value, scales=None, tolerance_pct=0.05):
        if scales is None:
            scales = (10.0, 0.1, 100.0, 0.01)
        results = {}
        abs_value = abs(value)
        for s in scales:
            target = abs_value * s
            tol = max(target * tolerance_pct, 1.0)
            matches = [f for f in self._facts if abs(abs(f.value) - target) <= tol]
            if matches:
                results[s] = matches
        return results


# ----- claim 추출 -----

def test_extract_jowon():
    claims = extract_numeric_claims("매출 333.61조원")
    assert len(claims) == 1
    assert claims[0].value == 333.61e12
    assert claims[0].text.startswith("333.61")


def test_extract_korean_negative():
    claims = extract_numeric_claims("DS 적자 △1.5조원")
    assert len(claims) == 1
    assert claims[0].value == -1.5e12


def test_extract_eok_unit():
    claims = extract_numeric_claims("자사주 매입 1,234억원")
    assert len(claims) == 1
    assert claims[0].value == 1234e8


def test_skip_small_numbers():
    claims = extract_numeric_claims("R&D 11.3% 매출 대비, 11.3억 규모")
    # 11.3억 = 1.13e9 < 1e10 → skip
    assert all(abs(c.value) >= 1e10 for c in claims)


def test_extract_multiple_in_text():
    text = "매출 333조, 영업이익 43.6조, DS 25조"
    claims = extract_numeric_claims(text)
    assert len(claims) == 3


def test_inference_marker_flagged():
    text = "메모리 회복으로 1.5조 추가 가능 *(추론 — 1Q 데이터 기반)*"
    claims = extract_numeric_claims(text)
    assert len(claims) == 1
    assert claims[0].is_in_inference


# ----- validation -----

def test_direct_match_passes():
    pack = _MockPack([_MockFact("Revenue", 333.61e12)])
    result = validate_numeric_claims("연결 매출 333.61조원", pack)
    assert result.passed


def test_scale_mismatch_now_fails():
    """v0.2: scale mismatch는 hard fail. SK하이닉스 08의 '826억 vs 8,263억' 같은 케이스 차단."""
    pack = _MockPack([_MockFact("OperatingIncome", 15.094e12)])
    result = validate_numeric_claims(
        "DS 2023년 △1.5조원 적자",
        pack,
    )
    assert not result.passed
    cats = [v.category for v in result.failures]
    assert "numeric_scale_mismatch" in cats


def test_dividend_unit_typo_caught():
    """v0.2 회귀 테스트: '826억' (실제 8,263억) 같은 자릿수 오류를 fail로 잡는다."""
    pack = _MockPack([_MockFact("DividendsPaid", 8.263e11)])  # 8,263억 = 8.263e11
    result = validate_numeric_claims("2024년 배당금: 826억 원", pack)
    assert not result.passed
    cats = [v.category for v in result.failures]
    assert "numeric_scale_mismatch" in cats


def test_market_cap_skipped_by_external_keyword():
    """v0.3 회귀: 시총 1,204조가 자본구성요소 121조와 10x 매치돼도 fail 아님 (false positive)."""
    # source_pack에 우연히 121조 fact가 있다고 가정
    pack = _MockPack([_MockFact("기타자본구성요소", 1.21e14)])  # 121조
    text = "시가총액 1,204.1조원 (KRX 종가 × 발행주식수)"
    result = validate_numeric_claims(text, pack)
    assert result.passed
    # claims 자체가 추출되지 않음 (라인 skip)
    claims = extract_numeric_claims(text)
    assert claims == []


def test_close_price_line_skipped():
    """종가 라인은 V2 skip."""
    pack = _MockPack([_MockFact("Revenue", 1.65e10)])  # 165억
    text = "KRX 2026-05-07 종가 1,654,000원"
    # 1,654,000원은 100억 미만이라 어차피 검출 안 되지만, 명시적 skip 검증
    claims = extract_numeric_claims(text)
    # 'KRX' + '종가' 키워드로 skip
    assert claims == []


def test_normal_xbrl_line_still_validated():
    """일반 재무 라인(시총·종가 키워드 없음)은 그대로 V2 검증."""
    pack = _MockPack([_MockFact("OperatingIncome", 47.21e12)])
    # 정상 인용
    result = validate_numeric_claims("2025년 영업이익 47.21조원 [XBRL]", pack)
    assert result.passed
    # 자릿수 오류 — fail
    result = validate_numeric_claims("2025년 영업이익 4.7조원 [XBRL]", pack)
    assert not result.passed


def test_unverified_is_warning_not_fail():
    """source_pack에 없고 스케일 매치도 없으면 warn (fail 아님).
    100 vs 7.7 = 0.077 비율 → 어떤 스케일에도 안 맞음."""
    pack = _MockPack([_MockFact("Revenue", 7.7e12)])
    result = validate_numeric_claims("매출 100조원", pack)
    assert result.passed
    assert any(w.category == "numeric_unverified" for w in result.warnings)


def test_inference_marker_skips_check():
    """추론 마커가 있으면 검증 skip."""
    pack = _MockPack([])
    result = validate_numeric_claims(
        "다음 분기 50조 추가 가능 *(추론)*",
        pack,
    )
    # 50조가 source_pack에 없지만 추론 마커로 skip
    assert result.passed
    assert not result.failures


def test_negative_value_match():
    pack = _MockPack([_MockFact("OperatingLoss", -11.526e12)])
    result = validate_numeric_claims("별도 영업이익 △11.5조원", pack)
    assert result.passed


def test_abs_or_rounded_match_warns_without_scale_mismatch():
    pack = _MockPack([_MockFact("PaymentsToAcquirePPE", 27.52e12)])
    result = validate_numeric_claims("유형자산 취득 현금흐름은 -27.52조원", pack)
    cats = [w.category for w in result.warnings]
    assert "numeric_abs_or_rounded_match" in cats
    assert "numeric_scale_mismatch" not in cats


def test_render_retry_emits_for_scale_mismatch():
    """v0.2: scale_mismatch는 fail이므로 retry 피드백 비어있지 않아야 한다."""
    pack = _MockPack([_MockFact("OperatingIncome", 15.094e12)])
    result = validate_numeric_claims("DS 2023년 △1.5조 적자", pack)
    feedback = render_numeric_failures_for_retry(result)
    assert feedback != ""
    assert "자릿수" in feedback


# ----- real Samsung XBRL integration -----

def test_real_samsung_xbrl_integration():
    """실제 삼성전자 XBRL로 source_pack 빌드 → 알려진 숫자 매치 확인.

    V2 v0.1 한계 메모: value-only 매치라 concept mismatch는 못 잡음.
    예: '1.5조' 자체가 XBRL 다른 concept에 우연히 있으면 직접 매치로 pass됨.
    Concept-aware 검증은 v0.2 영역.
    """
    from pathlib import Path
    from pipeline.source_pack import build_source_pack

    xbrl_dir = Path(__file__).resolve().parents[2] / "companies/삼성전자/2025-annual/raw_inputs/xbrl"
    if not xbrl_dir.exists():
        import pytest
        pytest.skip("Samsung XBRL not available")

    pack = build_source_pack(xbrl_dir, "삼성전자", "2025-annual")
    assert len(pack.facts) > 1000
    assert len(pack.xbrl.label_map) > 100

    # 알려진 사실: 연결 매출 333.606조 → 직접 매치
    result = validate_numeric_claims("연결 매출 333.61조원", pack)
    assert result.passed, "333.61조 should match XBRL 333.606조"

    # 알려진 사실: 별도 매출 238.043조 → 직접 매치
    result = validate_numeric_claims("별도 매출 238.0조원", pack)
    assert result.passed, "238.0조 should match XBRL 238.043조"


def test_real_sk_hynix_rounded_negative_match():
    from pathlib import Path
    from pipeline.source_pack import build_source_pack

    xbrl_dir = Path(__file__).resolve().parents[2] / "companies/SK하이닉스/2025-annual/raw_inputs/xbrl"
    if not xbrl_dir.exists():
        import pytest
        pytest.skip("SK Hynix XBRL not available")

    pack = build_source_pack(xbrl_dir, "SK하이닉스", "2025-annual")
    result = validate_numeric_claims("2023년 매출총이익은 -0.53조원이었다.", pack)
    assert result.passed
    assert not any(w.category == "numeric_scale_mismatch" for w in result.warnings)

    result = validate_numeric_claims("2024년 Capex는 16.7조원으로 추정된다.", pack)
    assert result.passed
    assert not any(w.category == "numeric_scale_mismatch" for w in result.warnings)
