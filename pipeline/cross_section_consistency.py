"""섹션 간 핵심 사실 일관성 검증.

V2/V3는 *값 매치*·*표 산술*만 검사한다. 그러나 LLM이 학습 데이터 기반 환각으로
*같은 사실*을 섹션마다 다른 값으로 인용하는 케이스(예: 02의 '시총 약 80조원대' vs
실제 1,204조)는 못 잡는다.

본 모듈은 **권위 사실 dict** (authoritative facts)를 정의하고, 모든 섹션이 그 사실을
±허용 범위 안에서 인용했는지 검증한다.

권위 사실:
  - 시가총액 (ticker_market_data에서 KRX 종가 × DART 발행주식수)
  - 매출, 영업이익, 영업CF, 자본총계 등 (XBRL)
  - 1Q 잠정실적 영업이익 (quarterly_disclosure body_excerpt에서 추출)

검증 방식:
  - 각 권위 사실의 키워드(예: '시총', '시가총액')가 섹션에 등장하면
  - 그 라인의 *큰 숫자*를 추출
  - 권위 값의 ±허용 범위(시총 5%, 재무 1%, 잠정실적 5%) 안에 있어야 함
  - 벗어나면 환각으로 분류 → fail
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class AuthoritativeFact:
    """단일 사실 — 모든 섹션에서 일관되게 인용되어야 하는 값."""

    key: str  # 사실 식별자 (예: 'market_cap', 'revenue_2025')
    label: str  # 사람이 읽는 이름 (예: '시가총액 2026-05-07')
    value_krw: float  # 정확한 값 (원 단위)
    keywords: tuple[str, ...]  # 텍스트에서 매치할 키워드 (예: '시가총액', '시총')
    tolerance_pct: float = 0.01  # 허용 오차 (1% = 0.01)


@dataclass(frozen=True)
class ConsistencyViolation:
    section: str
    fact_key: str
    fact_label: str
    expected_krw: float
    found_text: str
    found_value_krw: float
    line_no: int
    deviation_pct: float


# 한국식 큰 숫자 패턴: "1,204조", "47.21조원", "97조 1,467억", "37조 6,103억원"
_KOREAN_NUMBER = re.compile(
    r"(?:(?P<jo>\d{1,4}(?:,\d{3})*(?:\.\d+)?)\s*조)?"
    r"(?:\s*(?P<eok>\d{1,4}(?:,\d{3})*(?:\.\d+)?)\s*억)?"
)
_BIG_NUM = re.compile(
    r"(?<![A-Za-z\d.])"
    r"([+-]?[△▲▼]?\s*\d{1,4}(?:,\d{3})*(?:\.\d+)?)\s*(조|억)"
)


def _parse_korean_to_krw(num_str: str, unit: str) -> float | None:
    s = num_str.strip().lstrip("△▲▼+- ").replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None
    if unit == "조":
        return v * 1e12
    if unit == "억":
        return v * 1e8
    return None


def _extract_big_numbers(line: str) -> list[tuple[str, float]]:
    """라인에서 큰 숫자(조·억) 추출. 같은 라인에 여러 개일 수도."""
    out: list[tuple[str, float]] = []
    for m in _BIG_NUM.finditer(line):
        v = _parse_korean_to_krw(m.group(1), m.group(2))
        if v is None:
            continue
        # "97조 1,467억" 같이 조+억 결합 패턴 매치 시 — 단순화: 큰 단위만 사용
        out.append((m.group(0).strip(), v))
    # 추가: "97조 1,467억" 결합 시 (조 + 억 동시)
    combo = re.search(
        r"(\d{1,4}(?:,\d{3})*(?:\.\d+)?)\s*조\s*(\d{1,4}(?:,\d{3})*(?:\.\d+)?)\s*억",
        line,
    )
    if combo:
        try:
            j = float(combo.group(1).replace(",", ""))
            e = float(combo.group(2).replace(",", ""))
            v = j * 1e12 + e * 1e8
            out.append((combo.group(0).strip(), v))
        except ValueError:
            pass
    return out


def _extract_big_numbers_with_positions(line: str) -> list[tuple[str, float, int]]:
    """라인에서 큰 숫자 + 시작 위치 추출."""
    out: list[tuple[str, float, int]] = []
    for m in _BIG_NUM.finditer(line):
        v = _parse_korean_to_krw(m.group(1), m.group(2))
        if v is None:
            continue
        out.append((m.group(0).strip(), v, m.start()))
    combo = re.search(
        r"(\d{1,4}(?:,\d{3})*(?:\.\d+)?)\s*조\s*(\d{1,4}(?:,\d{3})*(?:\.\d+)?)\s*억",
        line,
    )
    if combo:
        try:
            j = float(combo.group(1).replace(",", ""))
            e = float(combo.group(2).replace(",", ""))
            out.append((combo.group(0).strip(), j * 1e12 + e * 1e8, combo.start()))
        except ValueError:
            pass
    return out


def check_section_against_facts(
    section_id: str,
    text: str,
    facts: Iterable[AuthoritativeFact],
) -> list[ConsistencyViolation]:
    """한 섹션 텍스트에서 권위 사실의 키워드와 매치되는 라인을 찾고,
    *키워드 오른쪽 첫 큰 숫자*가 권위 값과 일치하는지 검증.

    정책 (v0.2):
      - 권위 사실(시총·매출·영업이익 등)은 *추론 마커가 있어도* 정확해야 한다.
        페르소나 §3.3 추론 라벨은 *해석·전망·추정*에 허용 — 1순위 출처가 있는 사실 자체를
        다른 값으로 적는 것은 환각이며 정직 처리 위반.
      - 키워드 *오른쪽*의 첫 큰 숫자만 매치 (왼쪽은 다른 항목 가능성 높음).
        예: 'FCF 33.4조 → 시총의 2.8%'의 경우, '시총' 오른쪽엔 '2.8%'(%단위, _BIG_NUM 미매치)
        밖에 없으므로 위반 없음. 33.4조는 시총 키워드 *왼쪽*이라 무시.
    """
    violations: list[ConsistencyViolation] = []
    fact_list = list(facts)
    for line_no, line in enumerate(text.splitlines(), 1):
        big_nums = _extract_big_numbers_with_positions(line)
        if not big_nums:
            continue
        for fact in fact_list:
            # 키워드 *모든 매치* 위치 수집 (라인 안에 같은 키워드가 여러 번 등장 가능)
            kw_positions: list[int] = []
            for kw in fact.keywords:
                start = 0
                while True:
                    p = line.find(kw, start)
                    if p == -1:
                        break
                    kw_positions.append(p)
                    start = p + len(kw)
            if not kw_positions:
                continue

            tol = fact.value_krw * fact.tolerance_pct
            # 정책: 어느 *한* 키워드 매치라도 그 *근접 60자* 안에 정확한 권위값이 있으면 통과.
            # 라인 전체에서 "시총/FCF 배수"(헤더 언급) + "시총 1,204조"(정확 인용)가 둘 다 있으면
            # 두 번째 매치가 통과시킨다.
            PROXIMITY = 60
            any_pass = False
            failing_candidates: list[tuple[str, float, int]] = []
            for kw_pos in kw_positions:
                proximate = [
                    (t, v, pos) for t, v, pos in big_nums
                    if kw_pos <= pos <= kw_pos + PROXIMITY
                ]
                if not proximate:
                    continue
                proximate.sort(key=lambda x: x[2])
                first_text, first_v, first_pos = proximate[0]
                if abs(first_v - fact.value_krw) <= tol:
                    any_pass = True
                    break
                failing_candidates.append((first_text, first_v, first_pos))
            if any_pass:
                continue
            if not failing_candidates:
                continue
            # 가장 가까운 (편차 작은) 후보로 위반 표기
            best = min(failing_candidates, key=lambda c: abs(c[1] - fact.value_krw))
            first_text, first_v, _ = best
            deviation = (first_v - fact.value_krw) / fact.value_krw * 100
            violations.append(
                ConsistencyViolation(
                    section=section_id,
                    fact_key=fact.key,
                    fact_label=fact.label,
                    expected_krw=fact.value_krw,
                    found_text=first_text,
                    found_value_krw=first_v,
                    line_no=line_no,
                    deviation_pct=deviation,
                )
            )
    return violations


def render_violations(violations: list[ConsistencyViolation]) -> str:
    if not violations:
        return "cross-section consistency: PASS (위반 없음)"
    out = [f"cross-section consistency: FAIL ({len(violations)}건)"]
    for v in violations:
        out.append(
            f"  [{v.section} L{v.line_no}] '{v.fact_label}' 위반 — "
            f"기대 {v.expected_krw:.3g}원 ({v.expected_krw/1e12:.2f}조), "
            f"발견 '{v.found_text}' ({v.found_value_krw:.3g}원, "
            f"편차 {v.deviation_pct:+.1f}%)"
        )
    return "\n".join(out)


def build_authoritative_facts(
    market_cap_krw: float | None,
    revenue_krw: float | None,
    operating_income_krw: float | None,
    operating_cash_flow_krw: float | None,
    capex_krw: float | None,
    interim_q_operating_income_krw: float | None = None,
    interim_q_label: str = "1Q 잠정실적 영업이익",
) -> list[AuthoritativeFact]:
    """run_dart의 데이터 fetch 결과를 권위 사실 리스트로 변환."""
    facts: list[AuthoritativeFact] = []
    if market_cap_krw is not None:
        facts.append(
            AuthoritativeFact(
                key="market_cap",
                label="시가총액",
                value_krw=market_cap_krw,
                keywords=("시가총액", "시총"),
                tolerance_pct=0.05,  # 5% — 종가 변동·인용 시점 차이 허용
            )
        )
    if revenue_krw is not None:
        facts.append(
            AuthoritativeFact(
                key="revenue",
                label="2025 연결 매출",
                value_krw=revenue_krw,
                keywords=("연결 매출", "매출 97", "매출액 97", "수익(매출액)"),
                tolerance_pct=0.01,
            )
        )
    if operating_income_krw is not None:
        facts.append(
            AuthoritativeFact(
                key="operating_income",
                label="2025 연결 영업이익",
                value_krw=operating_income_krw,
                keywords=("영업이익 47", "연결 영업이익"),
                tolerance_pct=0.01,
            )
        )
    if operating_cash_flow_krw is not None:
        facts.append(
            AuthoritativeFact(
                key="operating_cash_flow",
                label="2025 영업활동현금흐름",
                value_krw=operating_cash_flow_krw,
                keywords=("영업활동현금흐름 53", "영업CF 53"),
                tolerance_pct=0.01,
            )
        )
    if capex_krw is not None:
        facts.append(
            AuthoritativeFact(
                key="capex",
                label="2025 유형자산 취득(capex)",
                value_krw=capex_krw,
                keywords=("유형자산 취득 27", "capex 27", "Capex 27"),
                tolerance_pct=0.02,
            )
        )
    if interim_q_operating_income_krw is not None:
        facts.append(
            AuthoritativeFact(
                key="interim_q_operating_income",
                label=interim_q_label,
                value_krw=interim_q_operating_income_krw,
                keywords=("1Q26 영업이익", "1Q 2026 영업이익", "분기 영업이익", "Q1 2026 영업이익"),
                tolerance_pct=0.05,
            )
        )
    return facts
