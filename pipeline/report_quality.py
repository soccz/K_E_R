"""보고서 생성 전후 품질 가드.

목표는 빈 입력이나 실패 보고서가 "완료"로 흘러가는 것을 막는 것이다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GuardResult:
    passed: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines: list[str] = []
        if self.failures:
            lines.append(f"FAIL ({len(self.failures)}건)")
            lines.extend(f"  - {m}" for m in self.failures)
        if self.warnings:
            lines.append(f"WARN ({len(self.warnings)}건)")
            lines.extend(f"  - {m}" for m in self.warnings)
        if not lines:
            return "PASS"
        return "\n".join(lines)


_FAILURE_MARKERS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"filings\s*:\s*\[\]"), "empty filings marker"),
    (re.compile(r"공시\s*(데이터|목록)이\s*비어"), "empty DART disclosure marker"),
    (re.compile(r"수신된\s*공시\s*건수\s*[:：]?\s*0건"), "empty DART disclosure marker"),
    (re.compile(r"이번\s*(실행|회|분석|작성\s*회차).{0,80}(공시|DART).{0,60}(없|0건|미수신|미로드|미포함)"), "empty DART disclosure marker"),
    (re.compile(r"DART\s*API.{0,50}(비어|미응답|반환하지 않았|공시 없음|미수신)"), "DART API empty-data marker"),
    (re.compile(r"학습\s*데이터\s*기반"), "training-data based claim"),
    (re.compile(r"훈련\s*데이터\s*기반"), "training-data based claim"),
    (re.compile(r"XBRL\s*미수신"), "XBRL missing marker"),
    (re.compile(r"재무제표\s*원문\s*미수신"), "financial statements missing marker"),
]


def find_report_failure_markers(text: str) -> list[str]:
    markers: list[str] = []
    for pattern, message in _FAILURE_MARKERS:
        if pattern.search(text):
            markers.append(message)
    return markers


def validate_generation_inputs(
    dart_data: dict[str, Any],
    source_pack: Any | None = None,
    *,
    require_xbrl: bool = True,
    min_total_text_chars: int = 5_000,
) -> GuardResult:
    failures: list[str] = []
    warnings: list[str] = []

    filings = dart_data.get("filings") or []
    if not filings:
        failures.append("DART 원문 로딩 결과가 0건입니다. 빈 데이터로 보고서를 만들 수 없습니다.")
    else:
        total_text_chars = sum(int(f.get("text_chars") or 0) for f in filings)
        loaded_chars = sum(len(f.get("text") or "") for f in filings)
        if total_text_chars <= 0 or loaded_chars <= 0:
            failures.append("DART 원문 텍스트가 비어 있습니다.")
        elif total_text_chars < min_total_text_chars:
            warnings.append(
                f"DART 원문 텍스트가 {total_text_chars:,}자로 작습니다. 보고서 원문이 일부만 로드됐는지 확인이 필요합니다."
            )

        skipped = dart_data.get("skipped_files") or []
        if skipped:
            warnings.append(f"지원하지 않는 원문 파일 {len(skipped)}건을 건너뜀: {', '.join(skipped[:5])}")

    if require_xbrl:
        if source_pack is None:
            failures.append("XBRL source_pack이 없습니다. 정기보고서는 XBRL 없이 생성하지 않습니다.")
        elif len(getattr(source_pack, "facts", [])) < 100:
            failures.append("XBRL fact 수가 비정상적으로 적습니다. 재무 수치 검증이 불가능합니다.")

    return GuardResult(passed=not failures, failures=failures, warnings=warnings)


def validate_generated_text(text: str) -> GuardResult:
    markers = find_report_failure_markers(text)
    failures = [f"생성물에 실패/빈 데이터 마커가 남아 있습니다: {m}" for m in markers]
    return GuardResult(passed=not failures, failures=failures)


def is_usable_report(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    return validate_generated_text(text).passed
