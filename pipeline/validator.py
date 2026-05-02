"""출처·추론 규칙 자동 검증.

이게 시스템의 실질적 해자다. LLM이 그럴듯하게 채워 넣으려는 시도를 잡아낸다.
규칙은 _frame.md 섹션 3 (출처·추론 규칙)을 코드로 옮긴 것이다.

Hard fail (보고서 생성 실패):
  - 출처 모호 표현 ("보도에 따르면" 등)
  - 추론 마커 없는 미래·해석 표현
  - 합본의 "데이터 기준시점" 박스 누락

Soft warn (로그만, 실패는 아님):
  - 섹션 끝 "이번 회 등장 용어" 메타 라인 누락
  - 비유 한 줄 누락
  - 섹션 길이 비정상
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

Severity = Literal["fail", "warn"]


@dataclass(frozen=True)
class Violation:
    severity: Severity
    category: str
    line: int
    snippet: str
    message: str


@dataclass
class ValidationResult:
    passed: bool
    failures: list[Violation] = field(default_factory=list)
    warnings: list[Violation] = field(default_factory=list)

    def render(self) -> str:
        if self.passed and not self.warnings:
            return "validator: PASS (위반 없음)"
        out: list[str] = []
        if self.failures:
            out.append(f"validator: FAIL ({len(self.failures)}건)")
            for v in self.failures:
                out.append(f"  [FAIL] L{v.line} {v.category}: {v.message}")
                if v.snippet:
                    out.append(f"         > {v.snippet}")
        if self.warnings:
            out.append(f"validator: warnings ({len(self.warnings)}건)")
            for v in self.warnings:
                out.append(f"  [warn] L{v.line} {v.category}: {v.message}")
        if self.passed:
            out.insert(0, "validator: PASS (warnings only)")
        return "\n".join(out)


_FORBIDDEN_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"보도에\s*따르면"), "vague_source", "출처 모호 — '보도에 따르면' 금지"),
    (re.compile(r"보도된\s*바(에\s*의하면)?"), "vague_source", "출처 모호 — '보도된 바' 금지"),
    (re.compile(r"알려져\s*있"), "vague_source", "출처 모호 — '알려져 있' 금지"),
    (re.compile(r"알려진\s*바"), "vague_source", "출처 모호 — '알려진 바' 금지"),
    (re.compile(r"알려진다"), "vague_source", "출처 모호 — '알려진다' 금지"),
    (re.compile(r"알려졌다"), "vague_source", "출처 모호 — '알려졌다' 금지"),
    (re.compile(r"업계\s*관계자"), "vague_source", "출처 모호 — '업계 관계자' 금지"),
    (re.compile(r"업계\s*소식통"), "vague_source", "출처 모호 — '업계 소식통' 금지"),
    (re.compile(r"관계자에\s*따르면"), "vague_source", "출처 모호 — '관계자에 따르면' 금지"),
    (re.compile(r"관계자에\s*의하면"), "vague_source", "출처 모호 — '관계자에 의하면' 금지"),
    (re.compile(r"들리는\s*바"), "vague_source", "출처 모호 — '들리는 바' 금지"),
    (re.compile(r"전해지는\s*바"), "vague_source", "출처 모호 — '전해지는 바' 금지"),
    (re.compile(r"~?로\s*전해진다"), "vague_source", "출처 모호 — '~로 전해진다' 금지"),
]

_SPECULATIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"예상된다"),
    re.compile(r"전망된다"),
    re.compile(r"기대된다"),
    re.compile(r"추정된다"),
    re.compile(r"것으로\s*보인다"),
    re.compile(r"것으로\s*예상"),
    re.compile(r"것으로\s*전망"),
    re.compile(r"것으로\s*추정"),
    re.compile(r"것으로\s*기대"),
]

_INFERENCE_MARKER = re.compile(r"\*?\(?추론\)?\*?|\[추론\]")
_TIMESTAMP_BOX_MARKER = re.compile(r"데이터\s*기준시점")
_GLOSSARY_META = re.compile(r"이번\s*(회\s*)?등장\s*용어")
_ANALOGY_HINT = re.compile(r"비유[:\s]|마치\s+.+\s+같|닮았|에\s*가깝다")


def _check_forbidden(text: str) -> list[Violation]:
    violations: list[Violation] = []
    for i, line in enumerate(text.splitlines(), 1):
        for regex, category, message in _FORBIDDEN_PATTERNS:
            if regex.search(line):
                violations.append(
                    Violation(
                        severity="fail",
                        category=category,
                        line=i,
                        snippet=line.strip()[:140],
                        message=message,
                    )
                )
                break
    return violations


def _check_inference_markers(text: str) -> list[Violation]:
    violations: list[Violation] = []
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        for regex in _SPECULATIVE_PATTERNS:
            if not regex.search(line):
                continue
            window = line
            if i >= 2:
                window += " " + lines[i - 2]
            if i < len(lines):
                window += " " + lines[i]
            if _INFERENCE_MARKER.search(window):
                continue
            violations.append(
                Violation(
                    severity="fail",
                    category="missing_inference_marker",
                    line=i,
                    snippet=line.strip()[:140],
                    message="추론적 표현에 *(추론)* 또는 [추론] 마커 없음",
                )
            )
            break
    return violations


def _check_timestamp_box(text: str) -> list[Violation]:
    if _TIMESTAMP_BOX_MARKER.search(text):
        return []
    return [
        Violation(
            severity="fail",
            category="missing_timestamp_box",
            line=0,
            snippet="",
            message="합본/산업노트 헤더에 '데이터 기준시점' 박스 누락 (_frame.md 3.6)",
        )
    ]


def _check_glossary_meta(text: str) -> list[Violation]:
    if _GLOSSARY_META.search(text):
        return []
    return [
        Violation(
            severity="warn",
            category="missing_glossary_meta",
            line=0,
            snippet="",
            message="섹션 끝 '이번 회 등장 용어' 메타 라인 누락 (_frame.md 10)",
        )
    ]


def _check_analogy(text: str) -> list[Violation]:
    if _ANALOGY_HINT.search(text):
        return []
    return [
        Violation(
            severity="warn",
            category="missing_analogy",
            line=0,
            snippet="",
            message="비유 한 줄 누락 (_frame.md 3a.5)",
        )
    ]


def validate_section(text: str, section_id: str | None = None) -> ValidationResult:
    failures = _check_forbidden(text) + _check_inference_markers(text)
    warnings = _check_glossary_meta(text) + _check_analogy(text)
    return ValidationResult(
        passed=len(failures) == 0,
        failures=failures,
        warnings=warnings,
    )


def validate_assembled_report(text: str) -> ValidationResult:
    failures = (
        _check_forbidden(text)
        + _check_inference_markers(text)
        + _check_timestamp_box(text)
    )
    return ValidationResult(
        passed=len(failures) == 0,
        failures=failures,
        warnings=[],
    )


def validate_industry_note(text: str) -> ValidationResult:
    return validate_assembled_report(text)


def format_failures_for_retry(result: ValidationResult) -> str:
    if not result.failures:
        return ""
    lines = [
        "이전 출력이 다음 규칙을 위반했다. 위반된 부분을 수정해서 같은 섹션을 다시 작성해라.",
        "",
    ]
    for v in result.failures:
        lines.append(f"- [{v.category}] (line {v.line}) {v.message}")
        if v.snippet:
            lines.append(f"  위반 텍스트: {v.snippet}")
    lines.append("")
    lines.append(
        "출처가 없거나 모호하면 그 주장을 통째로 빼라. "
        "추론은 *(추론)* 마커와 근거 한 줄을 함께 적어라."
    )
    return "\n".join(lines)
