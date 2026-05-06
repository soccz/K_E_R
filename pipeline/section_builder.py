"""한 섹션 생성 + 다단계 validator 재시도 루프.

generate_section_with_validation:
  1. LLM 호출 → 섹션 1차 생성
  2. V1 (validator.py) — 출처·추론·구조 검증 → fail 시 재시도
  3. V3 (validator_v3_arithmetic.py) — 표 산술 검증 → fail 시 재시도
  4. V2 (validator_v2_numeric) — XBRL source_pack 매칭 → warn-only (재시도 X)
  5. V1 또는 V3 fail이면 통합 피드백을 LLM에 전달하며 재생성 (최대 N회)
  6. 끝까지 V1/V3 fail이면 예외 발생
  7. V2 warn은 SectionResult에 기록되어 사용자 검토용
"""
from __future__ import annotations

from dataclasses import dataclass

from pipeline import (
    config,
    llm_client,
    prompt_builder,
    validator,
    validator_v3_arithmetic,
    validator_v2_numeric,
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
    attempts: int

    @property
    def passed(self) -> bool:
        return self.v1_validation.passed and self.v3_validation.passed

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
    ):
        self.section_id = section_id
        self.v1 = v1
        self.v3 = v3
        super().__init__(
            f"section {section_id} failed validation after retries:\n"
            f"--- V1 (style/source) ---\n{v1.render()}\n"
            f"--- V3 (arithmetic) ---\n{v3.render()}"
        )


def _combined_feedback(
    v1: validator.ValidationResult,
    v3: validator.ValidationResult,
) -> str:
    parts: list[str] = []
    if v1.failures:
        parts.append(validator.format_failures_for_retry(v1))
    if v3.failures:
        parts.append(validator_v3_arithmetic.render_arithmetic_failures(v3))
    return "\n\n".join(parts)


def generate_section_with_validation(
    frame: FrameSpec,
    section_id: str,
    company_name: str,
    timestamps: prompt_builder.DataTimestamps,
    dart_data: dict,
    market_data: dict,
    source_pack: SourcePack | None = None,
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

    raw_outputs: list[str] = []
    last_v1: validator.ValidationResult | None = None
    last_v3: validator.ValidationResult | None = None

    for attempt in range(1, max_retries + 2):
        if attempt == 1:
            current_user = user_prompt
        else:
            assert last_v1 is not None and last_v3 is not None
            feedback = _combined_feedback(last_v1, last_v3)
            current_user = prompt_builder.build_retry_user_prompt(user_prompt, feedback)

        text = llm_client.generate_section(system_prompt, current_user)
        raw_outputs.append(text)
        v1 = validator.validate_section(text, section_id)
        v3 = validator_v3_arithmetic.validate_arithmetic(text)
        last_v1, last_v3 = v1, v3

        if v1.passed and v3.passed:
            v2 = (
                validator_v2_numeric.validate_numeric_claims(text, source_pack)
                if source_pack is not None
                else None
            )
            return SectionResult(
                section_id=section_id,
                raw_outputs=raw_outputs,
                final_text=text,
                v1_validation=v1,
                v3_validation=v3,
                v2_validation=v2,
                attempts=attempt,
            )

    assert last_v1 is not None and last_v3 is not None
    raise SectionBuildError(section_id, last_v1, last_v3)
