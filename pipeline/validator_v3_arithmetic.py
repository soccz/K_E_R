"""V3 산술 sanity check — 표 안의 수치가 *기계적으로* 맞는지 자동 검증.

이게 실패하면 hard fail (재시도 트리거). LLM이 표 안의 숫자를 환각해서 생성하는 것을
가장 싸고 즉시 잡아내는 방화벽이다.

검사 대상:
  1. 표 합계행 vs 데이터행 칼럼 합 일치
  2. 백분율 칼럼이 ~100%에 근접 (합계행 없는 경우)
  3. 한국식 음수 표기 (△, ▼) 정확히 처리

검사 외 (이건 V2 source pack 영역):
  - 인라인 숫자가 원자료에 실제 있는지 (예: "DS 2023 적자 △1.5조" 같은 자릿수 오류)
  - 출처 인용 셀 안의 숫자가 해당 섹션에 정말 있는지
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline.validator import ValidationResult, Violation


_NUMBER_PATTERN = re.compile(r"[△▲▼+-]?[\d,]+\.?\d*")
_TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")
_SEPARATOR_LINE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")

_TOTAL_KEYWORDS = (
    "합계", "총계", "총합", "총", "전체",
    "연결 합계", "연결합계", "수출 합계",
    "total", "sum",
)

# *합산해서 100%가 보장되는* 칼럼 헤더만 (비중·구성비 류).
# "율"·"점유율"·"변화" 등은 합산성이 없으므로 제외 — false fail 방지.
_SUMMABLE_PCT_HEADERS = (
    "비중", "구성비", "구성 비", "구성",
    "share", "weight",
)

# 합산성이 명백히 *없는* 칼럼 키워드. 이 키워드가 헤더에 있으면 합산 검증 skip.
_NON_SUMMABLE_HEADERS = (
    "율", "rate", "ratio", "margin", "마진",        # 영업이익률, ROE, ROIC, 마진율
    "변화", "증감", "yoy", "qoq", "성장",           # 변화율
    "점유율",                                        # 서로 다른 시장의 한 회사 점유율
    "수익률", "회전율", "회전",                     # 회전율, 수익률
    "대비",                                          # "영업CF 대비 비중" — 분모가 외부라 100% 합산 X
)


@dataclass(frozen=True)
class _Row:
    cells: list[str]
    line_no: int
    is_separator: bool = False


@dataclass(frozen=True)
class _Table:
    header: _Row
    body: list[_Row]
    line_start: int


def _strip_md(text: str) -> str:
    return text.strip().replace("**", "").replace("*", "")


def _split_row(line: str) -> list[str]:
    parts = line.split("|")
    return [_strip_md(p) for p in parts[1:-1]]


def _parse_number(text: str) -> float | None:
    text = _strip_md(text).replace(",", "").replace("%", "")
    if not text or text in {"—", "-", "·", "N/A", "n/a", ""}:
        return None
    sign = 1.0
    if text.startswith(("△", "▼")):
        sign = -1.0
        text = text[1:].strip()
    elif text.startswith("▲"):
        text = text[1:].strip()
    elif text.startswith("-"):
        sign = -1.0
        text = text[1:].strip()
    elif text.startswith("+"):
        text = text[1:].strip()
    try:
        return float(text) * sign
    except ValueError:
        return None


def _is_total_row(row: _Row) -> bool:
    if not row.cells:
        return False
    label = _strip_md(row.cells[0]).lower()
    return any(kw.lower() in label for kw in _TOTAL_KEYWORDS)


def _is_summable_pct_column(header_cell: str) -> bool:
    """이 칼럼이 '합산해서 100%가 보장되는' 비중·구성비 칼럼인가?

    보수적: 헤더에 명시적으로 '비중'·'구성비' 등이 들어간 경우에만 True.
    '율'·'점유율'·'변화' 키워드가 있으면 무조건 False (합산 무의미).
    """
    h = header_cell.lower()
    if any(kw in h for kw in _NON_SUMMABLE_HEADERS):
        return False
    return any(kw in h for kw in _SUMMABLE_PCT_HEADERS)


def _column_is_likely_absolute(header_cell: str, rows: list[_Row], col: int) -> bool:
    """이 칼럼이 절대값(합산 가능)인가? %·율 키워드가 없고, 셀에 % 표시도 거의 없으면 절대값으로 본다."""
    h = header_cell.lower()
    if any(kw in h for kw in _NON_SUMMABLE_HEADERS):
        return False
    if any(kw in h for kw in _SUMMABLE_PCT_HEADERS):
        return False
    pct_count = sum(
        1 for r in rows if col < len(r.cells) and "%" in r.cells[col]
    )
    return pct_count <= len(rows) * 0.2


def _parse_tables(text: str) -> list[_Table]:
    tables: list[_Table] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if not _TABLE_LINE.match(lines[i]):
            i += 1
            continue
        if i + 1 >= len(lines) or not _SEPARATOR_LINE.match(lines[i + 1]):
            i += 1
            continue

        header = _Row(cells=_split_row(lines[i]), line_no=i + 1)
        body: list[_Row] = []
        j = i + 2
        while j < len(lines) and _TABLE_LINE.match(lines[j]):
            body.append(_Row(cells=_split_row(lines[j]), line_no=j + 1))
            j += 1
        tables.append(_Table(header=header, body=body, line_start=i + 1))
        i = j
    return tables


def _check_table(table: _Table) -> list[Violation]:
    violations: list[Violation] = []
    if not table.body or len(table.header.cells) < 2:
        return violations

    total_rows = [r for r in table.body if _is_total_row(r)]
    detail_rows = [r for r in table.body if not _is_total_row(r)]
    if len(detail_rows) < 2:
        return violations

    n_cols = len(table.header.cells)

    for col in range(1, n_cols):
        col_values: list[float] = []
        for r in detail_rows:
            if col < len(r.cells):
                v = _parse_number(r.cells[col])
                if v is not None:
                    col_values.append(v)

        if len(col_values) < 2:
            continue

        col_header = table.header.cells[col] if col < len(table.header.cells) else ""
        col_label = _strip_md(col_header)
        is_summable_pct = _is_summable_pct_column(col_header)
        is_absolute = _column_is_likely_absolute(col_header, detail_rows, col)

        # 검증 1: 합계행이 있고 칼럼이 합산성 (절대값 또는 비중)인 경우에만 합 비교
        if is_absolute or is_summable_pct:
            for tr in total_rows:
                if col >= len(tr.cells):
                    continue
                tv = _parse_number(tr.cells[col])
                if tv is None:
                    continue
                actual = sum(col_values)
                tolerance = (
                    3.0 if is_summable_pct
                    else max(abs(tv) * 0.02, 0.5)
                )
                if abs(actual - tv) > tolerance:
                    violations.append(
                        Violation(
                            severity="fail",
                            category="table_sum_mismatch",
                            line=table.line_start,
                            snippet=(
                                f"col '{col_label}': "
                                f"detail rows sum = {actual:.4g}, total row = {tv:.4g} "
                                f"(diff {abs(actual - tv):.4g}, tol {tolerance:.4g})"
                            ),
                            message=(
                                f"표 칼럼 '{col_label}' 산술 불일치: "
                                f"행 합 {actual:.4g} vs 합계행 {tv:.4g}"
                            ),
                        )
                    )

        # 검증 2: 합계행 없는 합산성 비중 칼럼 → 합이 100±5
        if not total_rows and is_summable_pct and len(col_values) >= 3:
            pct_sum = sum(col_values)
            if not (95.0 <= pct_sum <= 105.0):
                violations.append(
                    Violation(
                        severity="fail",
                        category="percentage_sum_off",
                        line=table.line_start,
                        snippet=f"col '{col_label}': pct sum = {pct_sum:.2f}%",
                        message=(
                            f"비중 칼럼 '{col_label}' 합계가 100%에서 벗어남: "
                            f"{pct_sum:.2f}%"
                        ),
                    )
                )
    return violations


def validate_arithmetic(text: str) -> ValidationResult:
    """모든 마크다운 표를 파싱하여 산술 검증."""
    tables = _parse_tables(text)
    failures: list[Violation] = []
    for tbl in tables:
        failures.extend(_check_table(tbl))
    return ValidationResult(passed=len(failures) == 0, failures=failures, warnings=[])


def render_arithmetic_failures(result: ValidationResult) -> str:
    if not result.failures:
        return ""
    lines = [
        "이전 출력의 표에서 산술 불일치가 발견됐다. 다음을 *모두* 수정해야 한다:",
        "",
    ]
    for v in result.failures:
        lines.append(f"- L{v.line} [{v.category}] {v.message}")
        if v.snippet:
            lines.append(f"  detail: {v.snippet}")
    lines.append("")
    lines.append(
        "표의 칼럼 합과 합계행이 자릿수까지 정확히 일치해야 한다. "
        "합계가 안 맞으면 (a) 합계행 값을 행 합으로 수정하거나, "
        "(b) 빠진 행을 추가하거나, "
        "(c) 표 자체를 다시 작성해라. "
        "추정·요약치라면 합계행을 빼라."
    )
    return "\n".join(lines)
