"""source_pack — XBRL에서 추출한 ground-truth 숫자 facts 모음.

V2 validator의 검증 기준이 되는 단일 사실 데이터 소스.
LLM 출력의 모든 큰 숫자는 이 안에 있거나 derivable해야 한다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pipeline.xbrl_parser import XbrlFact, XbrlPackage, load_xbrl_package, lookup_label


CORE_CONCEPTS = {
    # 손익계산서 (P&L)
    "ifrs-full:Revenue",
    "ifrs-full:CostOfSales",
    "ifrs-full:GrossProfit",
    "dart:OperatingIncomeLoss",
    "ifrs-full:ProfitLossBeforeTax",
    "ifrs-full:ProfitLoss",
    "ifrs-full:ProfitLossAttributableToOwnersOfParent",
    "ifrs-full:FinanceCosts",
    # EPS (희석 효과 — 페르소나 거버넌스 우선항목)
    "ifrs-full:BasicEarningsLossPerShare",
    "ifrs-full:DilutedEarningsLossPerShare",
    # 현금흐름 3종 + 핵심 세부
    "ifrs-full:CashFlowsFromUsedInOperatingActivities",
    "ifrs-full:CashFlowsFromUsedInInvestingActivities",
    "ifrs-full:CashFlowsFromUsedInFinancingActivities",
    # capex (★ 페르소나 자본활용 우선) — 누락 시 LLM이 환각으로 채움
    "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
    "ifrs-full:PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities",
    # 주주환원 (★ 페르소나 거버넌스)
    "ifrs-full:DividendsPaid",
    "ifrs-full:DividendsPaidClassifiedAsFinancingActivities",
    # 차입금 (★ 페르소나 재무건강 — 만기 분포)
    "ifrs-full:Borrowings",
    "ifrs-full:LongtermBorrowings",
    "ifrs-full:CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings",
    "ifrs-full:ProceedsFromBorrowingsClassifiedAsFinancingActivities",
    "ifrs-full:RepaymentsOfBorrowingsClassifiedAsFinancingActivities",
    # 재무상태표
    "ifrs-full:Assets",
    "ifrs-full:CurrentAssets",
    "ifrs-full:CashAndCashEquivalents",
    "ifrs-full:Inventories",
    "ifrs-full:TradeAndOtherReceivables",
    "ifrs-full:TradeAndOtherCurrentPayablesToTradeSuppliers",
    "ifrs-full:Liabilities",
    "ifrs-full:CurrentLiabilities",
    "ifrs-full:CurrentTaxLiabilities",
    "ifrs-full:Equity",
    "ifrs-full:RetainedEarnings",
    "ifrs-full:PropertyPlantAndEquipment",
}


@dataclass
class SourcePack:
    company: str
    period: str
    xbrl: XbrlPackage

    @property
    def facts(self) -> list[XbrlFact]:
        return self.xbrl.facts

    def label_for(self, concept: str) -> str | None:
        return lookup_label(self.xbrl, concept)

    def find_value(
        self, value: float, tolerance_pct: float = 0.01
    ) -> list[XbrlFact]:
        if value == 0:
            return [f for f in self.facts if f.value == 0]
        tol = max(abs(value) * tolerance_pct, 1.0)
        return [f for f in self.facts if abs(f.value - value) <= tol]

    def find_abs_value(
        self, value: float, tolerance_pct: float = 0.01
    ) -> list[XbrlFact]:
        target = abs(value)
        if target == 0:
            return [f for f in self.facts if f.value == 0]
        tol = max(target * tolerance_pct, 1.0)
        return [f for f in self.facts if abs(abs(f.value) - target) <= tol]

    def find_with_scales(
        self,
        value: float,
        scales: tuple[float, ...] = (10.0, 0.1),
        tolerance_pct: float = 0.02,
    ) -> dict[float, list[XbrlFact]]:
        """Value를 여러 스케일로 변환해 매칭 검색. 자릿수 오류 감지용.

        부호는 무시하고 *절대값* 기준으로 매치 — 자릿수 오류는 부호 오류와
        독립적으로 발생하며, "△1.5조 vs +15조"도 자릿수 오류 신호로 잡아야 한다.

        v0.2 정책 (2026-05): scales를 (10, 0.1)로 좁힘 (이전: 10/0.1/100/0.01).
        근거: LLM의 흔한 실수는 1자리 누락(10x 차이)이고, 100x/0.01x는 다른 컨셉이
        우연히 매치되는 false positive 빈도가 높다 (예: 시총 1,204조 vs 단기금융자산
        12조). tolerance도 5% → 2%로 좁혀 정확한 자릿수 매치만 잡는다.

        예: 1.5조 → 15조(10x) 매치 시 LLM이 자릿수 잘못 쓴 것으로 의심.
        """
        results: dict[float, list[XbrlFact]] = {}
        abs_value = abs(value)
        for s in scales:
            target = abs_value * s
            tol = max(target * tolerance_pct, 1.0)
            matches = [f for f in self.facts if abs(abs(f.value) - target) <= tol]
            if matches:
                results[s] = matches
        return results

    def to_summary_dict(self) -> dict:
        from collections import Counter
        concepts = Counter(f.concept for f in self.facts)
        return {
            "company": self.company,
            "period": self.period,
            "fact_count": len(self.facts),
            "context_count": len(self.xbrl.contexts),
            "label_count": len(self.xbrl.label_map),
            "top_concepts": concepts.most_common(20),
        }

    def to_prompt_summary(self, max_facts: int = 200) -> dict:
        """LLM 프롬프트에 넣을 핵심 XBRL fact 요약.

        구조: 컨셉별로 모든 연도 fact를 그룹핑해서 LLM이 시계열을 한눈에 보게 한다.
        한 해라도 빠지면 LLM이 "확인되지 않음"으로 처리하거나 환각으로 채우는 것을 방지.
        """
        from collections import defaultdict

        grouped: dict[str, list[dict]] = defaultdict(list)
        for fact in self.facts:
            if fact.concept not in CORE_CONCEPTS:
                continue
            if not _is_consolidated_primary_fact(fact):
                continue
            grouped[fact.concept].append(
                {
                    "value_krw": fact.raw_value,
                    "value_trillion_krw": round(fact.value / 1e12, 4),
                    "value_eok_krw": round(fact.value / 1e8, 1),
                    "period": fact.context_summary(),
                    "period_end": fact.period_end,
                }
            )

        core_timeseries: list[dict] = []
        total = 0
        for concept in sorted(grouped.keys()):
            entries = sorted(
                grouped[concept], key=lambda e: e.get("period_end") or ""
            )
            for e in entries:
                e.pop("period_end", None)
            core_timeseries.append(
                {
                    "concept": concept,
                    "label": self.label_for(concept) or concept,
                    "timeseries": entries,
                }
            )
            total += len(entries)
            if total >= max_facts:
                break

        return {
            "company": self.company,
            "period": self.period,
            "fact_count": len(self.facts),
            "label_count": len(self.xbrl.label_map),
            "core_consolidated_timeseries": core_timeseries,
            "usage_rule": (
                "위 timeseries는 XBRL ground truth다. 보고서 안 모든 큰 숫자는 "
                "(a) 위 데이터에서 직접 인용, (b) 위 데이터에서 산술적으로 도출 "
                "(예: 부채비율 = 부채/자본), 또는 (c) 명시적으로 '확인되지 않음' "
                "박스에 기재 — 이 셋 중 하나여야 한다. 학습기반 추정·환각·자릿수 변환 금지. "
                "한 컨셉의 시계열에서 특정 연도 값이 비어 있으면 그 연도는 '확인되지 않음'으로 적어라."
            ),
        }


def _is_consolidated_primary_fact(fact: XbrlFact) -> bool:
    if not fact.period_end or fact.period_end < "2023-01-01":
        return False
    dims = dict(fact.dimensions)
    if not dims:
        return True
    allowed_axis = "ifrs-full:ConsolidatedAndSeparateFinancialStatementsAxis"
    if set(dims.keys()) != {allowed_axis}:
        return False
    return dims[allowed_axis].endswith(":ConsolidatedMember")


def build_source_pack(xbrl_dir: Path, company: str, period: str) -> SourcePack:
    pkg = load_xbrl_package(xbrl_dir)
    return SourcePack(company=company, period=period, xbrl=pkg)


def save_source_pack_summary(pack: SourcePack, out_path: Path) -> None:
    out_path.write_text(
        json.dumps(pack.to_summary_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
