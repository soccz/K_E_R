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


_NOT_CONFIRMED_PATTERN = re.compile(r"확인되지\s*않음")
_INFERENCE_MARKER = re.compile(r"\*?\(?\s*추론.*?\)?\*?|\[추론.*?\]")
# 미래·예정 키워드 — 미확인 라인이 미래 시기 한정이면 과거/현재 단언과 충돌 아님
_FUTURE_KEYWORDS = re.compile(
    r"(2026|2027|2028|2029|2030|미래|향후|가이던스|예정|계획|차기|다음 [분반]기|다음 연도)"
)

# 카테고리 키워드 — 같은 키워드가 *같은 의미로* 한 곳에서 '확인되지 않음', 다른 곳에서
# 단언 숫자로 등장하면 충돌. 인접 단락(±60자)에 *동일 키워드*가 있어야 진짜 충돌로 본다.
_CROSS_CHECK_KEYWORDS = (
    "capex",
    "유형자산 취득",
    "배당금",
    "외국인 보유",
    "외국인 비중",
    "시가총액",
    "지역별 매출",
    "HBM 매출",
    "DRAM 매출",
    "NAND 매출",
    "WACC",
)


def find_inconsistencies(text: str) -> list[str]:
    """진짜 충돌만 잡는다. *(추론)* 마커 단언은 제외.

    v0.2 정책 (2026-05):
      - 추론 마커가 같은 라인 또는 인접 라인에 있으면 단언으로 보지 않음 (페르소나 §3.3 정상 처리)
      - 윈도우 ±60자로 좁힘 (이전 ±200자 → 인접 단락 false positive 줄임)
      - 단언 숫자가 *동일 키워드와 같은 단락(±60자)*에 있을 때만 충돌로 본다
        (예: 'capex 확인되지 않음' 단락 옆에 'capex 27조'가 있으면 진짜 충돌, 다른 항목 무관)
    """
    findings: list[str] = []
    lower_text = text.lower()
    big_num_pat = re.compile(r"[\d.,]+\s*(조|억)\s*원?")

    for kw in _CROSS_CHECK_KEYWORDS:
        kw_lower = kw.lower()
        # 키워드 출현 위치 모두 수집
        positions: list[int] = []
        idx = 0
        while True:
            i = lower_text.find(kw_lower, idx)
            if i == -1:
                break
            positions.append(i)
            idx = i + len(kw_lower)
        if not positions:
            continue

        # 각 출현이 '확인되지 않음 컨텍스트'인지 '단언 컨텍스트'인지 분류
        # 미래 한정 미확인(예: '2026 capex 가이던스')은 별도로 분리 — 과거/현재 단언과 충돌 아님
        unknown_positions: list[int] = []
        future_unknown_positions: list[int] = []
        assert_positions: list[int] = []
        for p in positions:
            window = text[max(0, p - 60) : p + 60]
            line_start = text.rfind("\n", 0, p) + 1
            line_end = text.find("\n", p)
            if line_end == -1:
                line_end = len(text)
            line = text[line_start:line_end]

            # 추론 마커가 라인에 있으면 — *(추론 — ... 미확인 ...)* 같은 정상 처리.
            # NOT_CONFIRMED·단언 둘 다 분류 안 함 (false positive 방지).
            if _INFERENCE_MARKER.search(line):
                continue

            if _NOT_CONFIRMED_PATTERN.search(line):
                # 미래 한정 미확인은 별도 — 과거 단언과 충돌 아님
                if _FUTURE_KEYWORDS.search(line):
                    future_unknown_positions.append(p)
                else:
                    unknown_positions.append(p)
                continue

            # 윈도우 추론 마커 인접도 정상으로 본다
            if _INFERENCE_MARKER.search(window):
                continue

            # 단언 후보: 같은 라인에 큰 숫자 있는지
            if big_num_pat.search(line):
                assert_positions.append(p)
                continue
            # 단언 후보: 윈도우 안에 큰 숫자 + '확인되지 않음' 없음
            if big_num_pat.search(window) and not _NOT_CONFIRMED_PATTERN.search(window):
                assert_positions.append(p)

        # 진짜 충돌: '확인되지 않음 컨텍스트' 위치와 '단언 컨텍스트' 위치가 *별개*로 있어야
        if unknown_positions and assert_positions:
            findings.append(
                f"키워드 '{kw}'가 같은 문서에서 '확인되지 않음'과 *추론 마커 없는* 단언 수치로 "
                f"동시에 등장 — 본문/표/헤드라인 간 일관성 점검 필요"
            )
    return findings


def validate_generated_text(text: str) -> GuardResult:
    markers = find_report_failure_markers(text)
    failures = [f"생성물에 실패/빈 데이터 마커가 남아 있습니다: {m}" for m in markers]
    inconsistencies = find_inconsistencies(text)
    warnings = [f"일관성 충돌: {c}" for c in inconsistencies]
    return GuardResult(passed=not failures, failures=failures, warnings=warnings)


def is_usable_report(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    return validate_generated_text(text).passed
