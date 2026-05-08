"""한 섹션 생성 + 다단계 validator 재시도 루프.

generate_section_with_validation:
  1. LLM 호출 → 섹션 1차 생성
  2. V1 (validator.py) — 출처·추론·구조 검증 → fail 시 재시도
  3. V3 (validator_v3_arithmetic.py) — 표 산술 검증 → fail 시 재시도
  4. V2 (validator_v2_numeric) — XBRL source_pack 자릿수 매칭 → fail 재시도
  5. **V4 (cross_section_consistency)** — 권위 사실(시총·매출·영업이익·1Q 잠정실적 등)
     인용 정확도 검증 → fail 재시도. 02 섹션 '시총 80조' 환각 같은 케이스 차단.
  6. V1/V2/V3/V4 중 하나라도 fail이면 통합 피드백을 LLM에 전달하며 재생성 (최대 N회)
  7. 끝까지 fail이면 예외 발생
  8. warn은 SectionResult에 기록되어 사용자 검토용
"""
from __future__ import annotations

from dataclasses import dataclass

from pipeline import (
    config,
    cross_section_consistency,
    llm_client,
    prompt_builder,
    validator,
    validator_v3_arithmetic,
    validator_v2_numeric,
)
from pipeline.cross_section_consistency import (
    AuthoritativeFact,
    ConsistencyViolation,
)
from pipeline.frame_loader import FrameSpec
from pipeline.source_pack import SourcePack


@dataclass
class SectionResult:
    section_id: str
    raw_outputs: list[str]
    final_text: str
    v1_validation: validator.ValidationResult
    v3_validation: validator.ValidationResult
    v2_validation: validator.ValidationResult | None  # None if no source_pack
    v4_violations: list[ConsistencyViolation]  # cross-section consistency
    attempts: int

    @property
    def passed(self) -> bool:
        v2_passed = self.v2_validation is None or self.v2_validation.passed
        v4_passed = len(self.v4_violations) == 0
        return (
            self.v1_validation.passed
            and self.v3_validation.passed
            and v2_passed
            and v4_passed
        )

    @property
    def all_warnings(self) -> list[validator.Violation]:
        out = list(self.v1_validation.warnings) + list(self.v3_validation.warnings)
        if self.v2_validation is not None:
            out.extend(self.v2_validation.warnings)
        return out


class SectionBuildError(Exception):
    def __init__(
        self,
        section_id: str,
        v1: validator.ValidationResult,
        v3: validator.ValidationResult,
        v2: validator.ValidationResult | None = None,
        v4: list[ConsistencyViolation] | None = None,
        raw_outputs: list[str] | None = None,
    ):
        self.section_id = section_id
        self.v1 = v1
        self.v3 = v3
        self.v2 = v2
        self.v4 = v4 or []
        self.raw_outputs = raw_outputs or []
        msg = (
            f"section {section_id} failed validation after retries:\n"
            f"--- V1 (style/source) ---\n{v1.render()}\n"
            f"--- V3 (arithmetic) ---\n{v3.render()}"
        )
        if v2 is not None and not v2.passed:
            msg += f"\n--- V2 (XBRL scale mismatch) ---\n{v2.render()}"
        if self.v4:
            msg += f"\n--- V4 (cross-section consistency) ---\n{cross_section_consistency.render_violations(self.v4)}"
        super().__init__(msg)


def _render_v4_feedback(violations: list[ConsistencyViolation]) -> str:
    if not violations:
        return ""
    lines = [
        "이전 출력에서 다음 권위 사실(authoritative facts) 인용이 정확하지 않다.",
        "**1순위 출처(XBRL·KRX·DART majorstock·잠정실적 본문)에서 정확한 값이 제공됐는데**, "
        "그 값과 다른 숫자를 적었다. 학습 데이터 기반 추정 금지 — *정확한 값으로 정정*해라.",
        "",
    ]
    for v in violations:
        lines.append(
            f"- L{v.line_no} '{v.fact_label}' 위반: 적힌 값 '{v.found_text}' "
            f"({v.found_value_krw/1e12:.2f}조), 정확한 값 {v.expected_krw/1e12:.2f}조, "
            f"편차 {v.deviation_pct:+.1f}%"
        )
    lines.append("")
    lines.append(
        "수정 방향: market_data.ticker_snapshot.market_cap_trillion_krw, "
        "core_consolidated_timeseries, quarterly_disclosures.interim_filings[0].body_excerpt를 "
        "직접 인용해라."
    )
    return "\n".join(lines)


def _combined_feedback(
    v1: validator.ValidationResult,
    v3: validator.ValidationResult,
    v2: validator.ValidationResult | None = None,
    v4: list[ConsistencyViolation] | None = None,
) -> str:
    parts: list[str] = []
    if v1.failures:
        parts.append(validator.format_failures_for_retry(v1))
    if v3.failures:
        parts.append(validator_v3_arithmetic.render_arithmetic_failures(v3))
    if v2 is not None and v2.failures:
        parts.append(validator_v2_numeric.render_numeric_failures_for_retry(v2))
    if v4:
        parts.append(_render_v4_feedback(v4))
    return "\n\n".join(parts)


def generate_section_with_validation(
    frame: FrameSpec,
    section_id: str,
    company_name: str,
    timestamps: prompt_builder.DataTimestamps,
    dart_data: dict,
    market_data: dict,
    source_pack: SourcePack | None = None,
    authoritative_facts: list[AuthoritativeFact] | None = None,
    max_retries: int | None = None,
) -> SectionResult:
    max_retries = max_retries if max_retries is not None else config.VALIDATOR_MAX_RETRIES

    system_prompt = prompt_builder.build_section_system_prompt(frame, section_id)
    user_prompt = prompt_builder.build_section_user_prompt(
        company_name,
        timestamps,
        dart_data,
        market_data,
        source_pack_summary=(
            source_pack.to_prompt_summary() if source_pack is not None else None
        ),
    )

    # 프롬프트 사이즈 가드 — 200KB 초과 시 경고 (claude CLI 600s timeout 회피)
    total_size = len(system_prompt) + len(user_prompt)
    if total_size > 200_000:
        print(
            f"  ⚠ {section_id} prompt size {total_size:,} chars "
            f"(system {len(system_prompt):,} + user {len(user_prompt):,}) — "
            f"timeout 위험. business_report max_chars / DART --max-total-chars 축소 권장."
        )

    raw_outputs: list[str] = []
    last_v1: validator.ValidationResult | None = None
    last_v3: validator.ValidationResult | None = None
    last_v2: validator.ValidationResult | None = None
    last_v4: list[ConsistencyViolation] = []

    for attempt in range(1, max_retries + 2):
        if attempt == 1:
            current_user = user_prompt
        else:
            assert last_v1 is not None and last_v3 is not None
            feedback = _combined_feedback(last_v1, last_v3, last_v2, last_v4)
            current_user = prompt_builder.build_retry_user_prompt(user_prompt, feedback)

        text = llm_client.generate_section(system_prompt, current_user)
        raw_outputs.append(text)
        v1 = validator.validate_section(text, section_id)
        v3 = validator_v3_arithmetic.validate_arithmetic(text)
        v2 = (
            validator_v2_numeric.validate_numeric_claims(text, source_pack)
            if source_pack is not None
            else None
        )
        v4 = (
            cross_section_consistency.check_section_against_facts(
                section_id, text, authoritative_facts
            )
            if authoritative_facts
            else []
        )
        last_v1, last_v3, last_v2, last_v4 = v1, v3, v2, v4

        v2_ok = v2 is None or v2.passed
        v4_ok = len(v4) == 0
        if v1.passed and v3.passed and v2_ok and v4_ok:
            return SectionResult(
                section_id=section_id,
                raw_outputs=raw_outputs,
                final_text=text,
                v1_validation=v1,
                v3_validation=v3,
                v2_validation=v2,
                v4_violations=v4,
                attempts=attempt,
            )

    assert last_v1 is not None and last_v3 is not None
    raise SectionBuildError(
        section_id, last_v1, last_v3, last_v2, last_v4, raw_outputs=raw_outputs
    )
