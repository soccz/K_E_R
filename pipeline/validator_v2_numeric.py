"""V2 numeric claims validator — LLM 출력의 큰 숫자가 source_pack에 있는지 검증.

**v0.2 정책 (2026-05 갱신):**
- `numeric_scale_mismatch` (자릿수 정확히 10x/0.1x/100x/0.01x 매치) → **hard fail**
  근거: 자릿수 오류는 거의 100% LLM의 단위 실수. false positive (다른 컨셉이 우연히 정확히 10x인 경우)
  가능성은 매우 낮음. SK하이닉스 08 섹션의 "826억 vs 8,263억" 같은 사례를 한 번 더 거른다.
- `numeric_abs_or_rounded_match` (절대값/반올림 매치) → warn
- `numeric_unverified` (어떤 매치도 없음) → warn
  근거: XBRL이 cover하지 못하는 비재무 데이터(지역별·점유율·근사값) 가능. concept-aware v0.3까지 보류.

검증 로직 (각 큰 숫자 ≥100억 이상에 대해):
  1. 추론 마커 *(추론)* 같은 줄에 있으면 skip
  2. source_pack에서 직접 매치 (±0.5%) → verified, no signal
  3. 절대값/반올림 매치 → numeric_abs_or_rounded_match warn (부호 차이·파생값 가능)
  4. 10x / 0.1x / 100x / 0.01x 스케일 매치 → **numeric_scale_mismatch fail** (자릿수 오류)
  5. 그 외 → numeric_unverified warn

section_builder는 V2 fail도 재시도 트리거로 사용한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline.source_pack import SourcePack
from pipeline.validator import ValidationResult, Violation


# 한국식 큰 숫자 패턴: "333.61조", "1,234억원", "△1.5조"
_BIG_NUM_PATTERN = re.compile(
    r"(?<![A-Za-z\d.])"
    r"([+-]?[△▲▼]?\s*[\d,]+\.?\d*)"
    r"\s*(조|억)"
    r"(?:\s*원)?"
)
_INFERENCE_MARKER = re.compile(r"\*?\(?추론.*?\)?\*?|\[추론.*?\]")
_UNIT_SCALE = {"조": 1e12, "억": 1e8}

# 100억 이상만 검증 (작은 숫자는 합산·비율 결과일 가능성)
_MIN_ABS_VALUE = 1e10

# 외부(비-XBRL) 데이터 인용 라인은 V2 skip — false positive 방지.
# 시총·종가·KRX·발행주식수 등은 ticker_market_data·foreign_holdings에서 온 값이라
# source_pack(XBRL)에 없는 게 정상. 우연히 다른 fact와 자릿수 매치되어도 fail 아님.
_EXTERNAL_DATA_KEYWORDS = (
    # 시장 시세·시총 (KRX OHLCV·DART 발행주식수 외부 데이터)
    "시가총액",
    "시총",
    "market cap",
    "market_cap",
    "종가",
    "주가",
    "KRX",
    "ticker_snapshot",
    "발행주식수",
    "유통주식수",
    # 외인 (DART majorstock + KRX 일별잔고 외부)
    "외국인 보유",
    "외인 보유",
    "외인 매도",
    "외국인 매도",
    "BlackRock",
    "Capital Research",
    "Vanguard",
    "Norges",
    "majorstock",
    # 분기 잠정실적 (사업보고서 외)
    "1Q26",
    "1Q 2026",
    "잠정실적",
    "분기 매출",
    "분기 영업이익",
    "quarterly_disclosures",
    # 매크로 지표 (KOSPI·USD/KRW·WTI·미국 10Y)
    "KOSPI",
    "USD/KRW",
    "USDKRW",
    "WTI",
    "미국 10Y",
    "기준금리",
    # 동종업계·산업 통계 (TrendForce·Gartner·IDC 외부)
    "TrendForce",
    "Gartner",
    "IDC",
    "TSMC",
    "Micron",
    "마이크론",
    "삼성전자 매출",
    "삼성 매출",
    "시장점유율",
    "DRAM 점유율",
    "HBM 점유율",
    "NAND 점유율",
    # owner-valuation 톤 문구 (시총·종가 인용이 명시 키워드 없이 등장하는 결론 단락)
    "통째로 살",
    "통째로 사",
    "owner-valuation",
    "owner valuation",
    "오너 밸류에이션",
    "PER",
    "P/E",
    "배수",
    "FCF 배수",
    "시총/FCF",
)


@dataclass(frozen=True)
class NumericClaim:
    text: str
    value: float
    line_no: int
    context: str
    is_in_inference: bool


def _parse_korean_number(num_str: str, unit: str) -> float | None:
    s = num_str.strip()
    sign = 1.0
    if s.startswith(("△", "▼")):
        sign = -1.0
        s = s[1:].strip()
    elif s.startswith("-"):
        sign = -1.0
        s = s[1:].strip()
    elif s.startswith(("+", "▲")):
        s = s[1:].strip()
    s = s.replace(",", "")
    try:
        return float(s) * _UNIT_SCALE[unit] * sign
    except (ValueError, KeyError):
        return None


def extract_numeric_claims(
    text: str, min_abs_value: float = _MIN_ABS_VALUE
) -> list[NumericClaim]:
    claims: list[NumericClaim] = []
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        is_inference = bool(_INFERENCE_MARKER.search(line))
        # 같은 라인에 외부(비-XBRL) 데이터 인용 키워드 있으면 V2 skip
        # (false positive 방지 — 시총 1,204조가 source_pack 자본구성요소 121조와 우연히 10x 매치되는 케이스)
        if any(kw in line for kw in _EXTERNAL_DATA_KEYWORDS):
            continue
        for m in _BIG_NUM_PATTERN.finditer(line):
            num_str, unit = m.group(1), m.group(2)
            val = _parse_korean_number(num_str, unit)
            if val is None or abs(val) < min_abs_value:
                continue
            claims.append(
                NumericClaim(
                    text=m.group(0).strip(),
                    value=val,
                    line_no=i,
                    context=line.strip()[:200],
                    is_in_inference=is_inference,
                )
            )
    return claims


def validate_numeric_claims(text: str, pack: SourcePack) -> ValidationResult:
    """v0.2: scale_mismatch는 hard fail, 나머지는 warn."""
    claims = extract_numeric_claims(text)
    warnings: list[Violation] = []
    failures: list[Violation] = []

    for claim in claims:
        if claim.is_in_inference:
            continue

        direct = pack.find_value(claim.value)
        if direct:
            continue

        sign_insensitive = _find_abs_value(pack, claim.value, tolerance_pct=0.03)
        if sign_insensitive:
            sample = sign_insensitive[0]
            sample_label = pack.label_for(sample.concept) or sample.concept.split(":")[-1]
            sample_period = (
                f"{sample.period_start}~{sample.period_end}"
                if sample.period_start
                else sample.period_end or ""
            )
            warnings.append(
                Violation(
                    severity="warn",
                    category="numeric_abs_or_rounded_match",
                    line=claim.line_no,
                    snippet=claim.context[:150],
                    message=(
                        f"숫자 '{claim.text}'는 절대값 또는 반올림 기준 source_pack에 근접 매치됩니다. "
                        f"현금유출/지급 개념의 표시 부호 차이나 파생 계산값일 수 있으므로 검토 필요. "
                        f"가까운 fact: '{sample_label}' = {sample.value:.3g} ({sample_period})"
                    ),
                )
            )
            continue

        scaled = pack.find_with_scales(claim.value)
        if scaled:
            scale_str = " 또는 ".join(f"{s}x" for s in sorted(scaled.keys()))
            sample = next(iter(scaled.values()))[0]
            sample_label = pack.label_for(sample.concept) or sample.concept.split(":")[-1]
            sample_period = (
                f"{sample.period_start}~{sample.period_end}"
                if sample.period_start
                else sample.period_end or ""
            )
            failures.append(
                Violation(
                    severity="fail",
                    category="numeric_scale_mismatch",
                    line=claim.line_no,
                    snippet=claim.context[:150],
                    message=(
                        f"숫자 '{claim.text}' (≈{claim.value:.3g})가 source_pack에 직접 매치 없음. "
                        f"{scale_str} 변환 시 정확 매치 → 자릿수 오류 (단위 실수). "
                        f"가까운 fact: '{sample_label}' = {sample.value:.3g} ({sample_period}). "
                        f"올바른 단위로 정정하거나 '확인되지 않음' 박스로 옮겨라."
                    ),
                )
            )
        else:
            warnings.append(
                Violation(
                    severity="warn",
                    category="numeric_unverified",
                    line=claim.line_no,
                    snippet=claim.context[:150],
                    message=(
                        f"숫자 '{claim.text}' (≈{claim.value:.3g}) source_pack 미매치. "
                        f"비재무(점유율·지역별·근사값) 또는 환각 가능."
                    ),
                )
            )

    return ValidationResult(
        passed=not failures,
        failures=failures,
        warnings=warnings,
    )


def _find_abs_value(pack: SourcePack, value: float, tolerance_pct: float = 0.01):
    if hasattr(pack, "find_abs_value"):
        return pack.find_abs_value(value, tolerance_pct=tolerance_pct)
    target = abs(value)
    tol = max(target * tolerance_pct, 1.0)
    return [f for f in pack.facts if abs(abs(f.value) - target) <= tol]


def render_numeric_failures_for_retry(result: ValidationResult) -> str:
    if not result.failures:
        return ""
    lines = [
        "이전 출력에서 다음 숫자가 source_pack(XBRL ground truth)과 일치하지 않는다.",
        "**자릿수 오류로 의심**되는 케이스다. 다음을 *모두* 수정해야 한다:",
        "",
    ]
    for v in result.failures:
        lines.append(f"- L{v.line} [{v.category}]")
        lines.append(f"  context: {v.snippet}")
        lines.append(f"  detail: {v.message}")
    lines.append("")
    lines.append(
        "수정 방향: (a) 자릿수 정정 (예: 1.5조 → 15조), "
        "(b) source_pack에서 *맞는 값과 컨텍스트*를 찾아 인용, "
        "(c) 확인 불가하면 그 주장을 **통째로 빼고** '확인되지 않음' 박스에 명시."
    )
    return "\n".join(lines)
