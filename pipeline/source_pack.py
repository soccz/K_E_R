"""source_pack — XBRL에서 추출한 ground-truth 숫자 facts 모음.

V2 validator의 검증 기준이 되는 단일 사실 데이터 소스.
LLM 출력의 모든 큰 숫자는 이 안에 있거나 derivable해야 한다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pipeline.xbrl_parser import XbrlFact, XbrlPackage, load_xbrl_package, lookup_label


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
        self, value: float, tolerance_pct: float = 0.005
    ) -> list[XbrlFact]:
        if value == 0:
            return [f for f in self.facts if f.value == 0]
        tol = max(abs(value) * tolerance_pct, 1.0)
        return [f for f in self.facts if abs(f.value - value) <= tol]

    def find_with_scales(
        self,
        value: float,
        scales: tuple[float, ...] = (10.0, 0.1, 100.0, 0.01),
        tolerance_pct: float = 0.05,
    ) -> dict[float, list[XbrlFact]]:
        """Value를 여러 스케일로 변환해 매칭 검색. 자릿수 오류 감지용.

        부호는 무시하고 *절대값* 기준으로 매치 — 자릿수 오류는 부호 오류와
        독립적으로 발생하며, "△1.5조 vs +15조"도 자릿수 오류 신호로 잡아야 한다.

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


def build_source_pack(xbrl_dir: Path, company: str, period: str) -> SourcePack:
    pkg = load_xbrl_package(xbrl_dir)
    return SourcePack(company=company, period=period, xbrl=pkg)


def save_source_pack_summary(pack: SourcePack, out_path: Path) -> None:
    out_path.write_text(
        json.dumps(pack.to_summary_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
