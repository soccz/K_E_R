"""V2 numeric claims validator — LLM 출력의 큰 숫자가 source_pack에 있는지 검증.

**v0.1: 모든 위반을 warn으로 격하 (hard fail 안 함).**
이유: XBRL이 cover하지 못하는 데이터(지역별·근사값·비재무)가 많아 value-only 매칭은
false positive가 흔함. concept-aware v0.2 전까지는 *분석가 도우미 역할*로만 사용.

검증 로직 (각 큰 숫자 ≥100억 이상에 대해):
  1. 추론 마커 *(추론)* 같은 줄에 있으면 skip
  2. source_pack에서 직접 매치 (±0.5%) → verified, no signal
  3. 10x / 0.1x / 100x / 0.01x 스케일 매치 → **자릿수 오류 의심** warn (소프트)
  4. 둘 다 아니면 → unverified warn (XBRL에 없는 비재무 데이터일 수 있음)

진단 사례 (LLM "DS 2023 △1.5조" → 10x 매치 = 15조 → ⚠️ 분석가 검토 권고)
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
    """v0.1: 모든 시그널을 warn으로 처리 (hard fail 없음)."""
    claims = extract_numeric_claims(text)
    warnings: list[Violation] = []

    for claim in claims:
        if claim.is_in_inference:
            continue

        direct = pack.find_value(claim.value)
        if direct:
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
            warnings.append(
                Violation(
                    severity="warn",
                    category="numeric_scale_mismatch",
                    line=claim.line_no,
                    snippet=claim.context[:150],
                    message=(
                        f"숫자 '{claim.text}' (≈{claim.value:.3g})가 source_pack에 직접 매치 없음. "
                        f"{scale_str} 변환 시 매치 → ⚠️ 자릿수 오류 가능성, 분석가 검토 권고. "
                        f"가까운 fact: '{sample_label}' = {sample.value:.3g} ({sample_period})"
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
        passed=True,  # v0.1: 항상 pass (warn만)
        failures=[],
        warnings=warnings,
    )


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
