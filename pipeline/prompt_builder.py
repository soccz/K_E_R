"""각 섹션 sub-agent용 시스템·유저 프롬프트 빌드.

시스템 프롬프트 = _frame.md + _persona.md + 해당 섹션 spec.
유저 프롬프트 = 회사명 + DART 데이터 + 시장 데이터 + 데이터 기준시점.

LLM은 자기 섹션만 작성한다 (다른 섹션 침범 금지).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pipeline.frame_loader import FrameSpec


SECTION_SPECS: dict[str, dict[str, str]] = {
    "01_사업구조진단": {
        "focus": (
            "이 회사가 무엇으로 돈을 버는가? 세그먼트별 매출·이익 비중과 그 변화. "
            "직전 분기 / 1년 전 대비. 사업 다각화의 정도와 방향성. "
            "페르소나 우선 항목: 매출의 해외 비중, 미국 시장 노출도, "
            "정부 정책 의존도, 국내 개미·테마주 의존도."
        ),
        "length_pages": "2~5",
    },
    "02_재무건강진단": {
        "focus": (
            "자본구조(자기자본 vs 부채), 차입금 만기 분포, "
            "현금흐름 3종(영업/투자/재무) 패턴, free cash flow, "
            "운전자본(매출채권·재고·매입채무) 회전, 단기 유동성. "
            "페르소나 우선: 영업이익 vs 영업CF 괴리를 *맨 앞에* 본다."
        ),
        "length_pages": "2~5",
    },
    "03_수익성진단": {
        "focus": (
            "매출총·영업·순이익률 추이 (직전 4~8분기 시계열), "
            "ROE / ROIC — 절대값과 추세, 동종업계 비교, "
            "이익률 변화 분해 (가격·물량·비용·믹스 효과). "
            "페르소나 우선: 영업CF 기준 수익성을 회계 이익보다 우선."
        ),
        "length_pages": "2~5",
    },
    "04_자본활용진단": {
        "focus": (
            "capex 규모와 방향 (사업·지역), M&A 내역과 의도, "
            "주주환원(자사주·배당), ROIC vs WACC 효율. "
            "페르소나 우선: capex가 미국 트렌드 정합한 방향인지."
        ),
        "length_pages": "2~5",
    },
    "05_업황과사이클진단": {
        "focus": (
            "산업 사이클의 어느 지점인가, 회사가 사이클 대비 잘하나, "
            "외부변수 노출도. "
            "페르소나 우선: 환율·유가(섹터)·미국 금리·외국인 매매·지정학 5종 매크로 의무."
        ),
        "length_pages": "2~5",
    },
    "06_경쟁포지션진단": {
        "focus": (
            "시장점유율 추세, 직접 경쟁자 비교, 진입장벽·해자, 신규 위협. "
            "페르소나 우선: **3년 단위** 기술 트랙 일관성, 미국 시장 검증 여부. "
            "압도적 기술 보유 시 미국 자본의 인수·IP 시나리오 양면성 평가."
        ),
        "length_pages": "2~5",
    },
    "07_거버넌스리스크진단": {
        "focus": (
            "지배구조(최대주주·우호지분 변동), 주석 항목(특수관계자·우발채무·회계정책 변경), "
            "임원·이사회 변동, 잠재 리스크. "
            "페르소나 우선: *장기 외인 vs 단기 외인* 추세, "
            "*국내 인기 vs 외인 동향 디커플링*, 지배구조 발표의 실제 이행 검증."
        ),
        "length_pages": "2~5",
    },
    "08_이번분기변화": {
        "focus": (
            "직전 분기 보고서 대비 *새로 바뀐 것들만* 모은다. "
            "01~07 각 섹션의 변화점을 한 곳에. "
            "페르소나의 ★★★ 적신호·호재가 새로 발생/해소됐는지 우선 점검. "
            "마지막에 '이번 분기 헤드라인' 3~5개."
        ),
        "length_pages": "1~3",
    },
    "09_추적사항": {
        "focus": (
            "다음 분기 보고서 나오면 이거 변했는지 보겠다 — 5~7개 항목. "
            "우려/기대 사항. 페르소나의 ★★★ 신호 중 미해결인 것 우선."
        ),
        "length_pages": "1~2",
    },
    "10_용어사전": {
        "focus": (
            "01~09에서 등장한 모든 전문용어의 풀이. "
            "본문에서 인라인으로 첫 등장 풀이를 한 번 더 모은 것."
        ),
        "length_pages": "1~2",
    },
}


@dataclass(frozen=True)
class DataTimestamps:
    written_at: str
    dart_query_at: str
    financial_basis: str
    market_price: str
    foreign_holding: str
    macro_data: str

    def render_box(self) -> str:
        return (
            "> **데이터 기준시점**\n"
            f"> - 작성일: {self.written_at}\n"
            f"> - DART 조회: {self.dart_query_at}\n"
            f"> - 재무제표: {self.financial_basis}\n"
            f"> - 시장가격: {self.market_price}\n"
            f"> - 외인 동향: {self.foreign_holding}\n"
            f"> - 환율·금리: {self.macro_data}\n"
        )


def build_section_system_prompt(frame: FrameSpec, section_id: str) -> str:
    spec = SECTION_SPECS.get(section_id)
    if spec is None:
        raise KeyError(f"unknown section: {section_id}")
    return (
        f"{frame.frame_md}\n\n"
        f"---\n\n"
        f"{frame.persona_md}\n\n"
        f"---\n\n"
        f"# 너의 작업\n\n"
        f"너는 **{section_id}** 섹션을 작성한다.\n\n"
        f"## 이 섹션의 초점\n{spec['focus']}\n\n"
        f"## 분량\n{spec['length_pages']} 페이지.\n\n"
        f"## 작성 규칙 (위 _frame.md / _persona.md 외 추가 강조)\n"
        f"- 자기 섹션만 작성. 다른 섹션 침범 금지.\n"
        f"- 출처가 없거나 모호하면 그 주장을 통째로 빼라. 채우려고 약한 출처를 끌어다 쓰지 말 것.\n"
        f"- 추론은 *(추론)* 또는 [추론] 마커 + 근거 한 줄.\n"
        f"- 모든 숫자·사실에 출처 인용. 형식: [공시명, 접수일, 회사명] 또는 [XBRL, 보고서, 항목].\n"
        f"- 비유 한 줄 의무.\n"
        f"- 섹션 끝에 \"이번 회 등장 용어: A, B, C\" 메타 라인.\n"
        f"- 출력은 마크다운. 섹션 헤더는 `## {section_id}`로 시작.\n"
        f"\n"
        f"## 숫자·단위 절대 규칙 (위반 시 V2/V4 validator hard fail)\n"
        f"- 모든 큰 숫자는 user prompt의 `core_consolidated_timeseries`에서 직접 인용하거나, 그 값으로부터 산술적으로 도출(부채/자본 등)해야 한다.\n"
        f"- 단위는 **'조' 또는 '억'**으로 통일. 1조 = 10,000억 = 1,000,000,000,000원이다.\n"
        f"  - 예: XBRL 1,681,166백만원 = **1조 6,812억** = 1.68조. **'1,681억'으로 적으면 자릿수 오류 (10배 작음)**.\n"
        f"  - 한 보고서 안에서 같은 항목의 단위 표기를 일관되게 유지.\n"
        f"- timeseries에 특정 연도 값이 비어 있으면 그 연도는 본문 표에서도 '확인되지 않음'으로 적는다. 다른 출처에서 가져와도 안 되고, 추정치를 단언으로 적어도 안 된다.\n"
        f"- **헤드라인·요약 박스에 단언으로 적은 숫자**는 같은 보고서 본문에서도 똑같은 숫자로 일관되게 인용되어야 한다. 본문 표가 '확인되지 않음'인 항목을 헤드라인에서 단언으로 쓰지 말 것.\n"
        f"\n"
        f"## 권위 사실(authoritative facts) 인용 절대 규칙 (V4 cross-section consistency)\n"
        f"다음 사실은 1순위 출처에서 정확한 값이 제공되며, 모든 섹션이 *같은 값*으로 인용해야 한다:\n"
        f"- **시가총액**: market_data.ticker_snapshot.market_cap_trillion_krw (KRX 종가 × DART 발행주식수)\n"
        f"- **2025 연결 매출·영업이익·영업CF·capex**: source_pack.core_consolidated_timeseries\n"
        f"- **1Q 잠정실적 영업이익**: market_data.quarterly_disclosures.interim_filings[0].body_excerpt 안의 숫자\n"
        f"\n"
        f"이 사실들은 추정·환각 절대 금지. 학습 데이터 기반으로 '시가총액 약 80조' 같은 옛 시점 숫자를 적으면 V4 hard fail.\n"
        f"잠정실적 본문(body_excerpt)에 '37조 6,103억원' 같이 적혀 있으면 그 숫자를 그대로 인용해야 하며, "
        f"'1Q26 영업이익 6.97조' 같이 다른 추정값을 적으면 V4 hard fail.\n"
        f"권위 사실에 대한 *(추론)* 마커는 무효 — 추론 라벨로 환각을 정당화할 수 없다.\n"
        f"\n"
        f"## 페르소나 톤 강화\n"
        f"- 비판적·회의적이 기본 톤. 호재는 시장이 알아서 반영한다 — 너는 위험을 본다.\n"
        f"- '그러나 ~할 가능성도 있다' 식의 양다리 결론 금지. 입장을 정하고 *왜 그렇게 보는지의 논리*를 보여줄 것.\n"
        f"- 페르소나 적신호·호재 표의 ★★★ 항목이 자기 섹션에 해당하면 본문에서 *눈에 띄게* 강조 (별도 단락 또는 박스).\n"
    )


def build_section_user_prompt(
    company_name: str,
    timestamps: DataTimestamps,
    dart_data: dict[str, Any],
    market_data: dict[str, Any],
    source_pack_summary: dict[str, Any] | None = None,
) -> str:
    parts = [
        f"# 분석 대상 회사\n{company_name}\n\n"
        f"# 데이터 기준시점\n{timestamps.render_box()}\n\n"
    ]
    if source_pack_summary is not None:
        parts.append(
            f"# XBRL 핵심 재무 데이터 (우선 사용 — ground truth)\n```json\n"
            f"{json.dumps(source_pack_summary, ensure_ascii=False, indent=2)}\n"
            f"```\n\n"
            f"재무 숫자 사실 주장은 위 XBRL 핵심 데이터와 DART 원문을 **최우선 1순위 근거**로 사용해라. "
            f"위 데이터와 맞지 않는 학습기반 숫자 추정은 금지한다. "
            f"위 timeseries에 특정 연도가 비어 있으면 그 연도는 '확인되지 않음'으로 처리하고, 추정치로 채우지 마라.\n\n"
            f"단위 환산 참고: 1조 = 1e12원, 1억 = 1e8원. "
            f"value_trillion_krw·value_eok_krw 컬럼이 모두 제공되니 둘 중 하나를 골라 일관되게 사용하라.\n\n"
        )
    parts.append(
        f"# DART 공시 데이터\n```json\n"
        f"{json.dumps(dart_data, ensure_ascii=False, indent=2)}\n"
        f"```\n\n"
        f"# 시장 데이터\n```json\n"
        f"{json.dumps(market_data, ensure_ascii=False, indent=2)}\n"
        f"```\n\n"
        f"위 데이터를 근거로 자기 섹션을 작성해라. "
        f"데이터에 없는 사실은 출처가 없는 것이다 — 추론으로 표시하거나 빼라."
    )
    return "".join(parts)


def build_retry_user_prompt(original_user_prompt: str, validator_feedback: str) -> str:
    return (
        f"{original_user_prompt}\n\n"
        f"---\n\n"
        f"# 재작성 요청 (validator 위반)\n\n"
        f"{validator_feedback}\n\n"
        f"위 위반 사항을 *모두* 해결한 새로운 섹션 본문만 출력해라. "
        f"섹션 헤더부터 메타 라인까지 전체."
    )
