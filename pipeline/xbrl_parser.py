"""DART XBRL 패키지 파싱.

XBRL 인스턴스 + 한국어 라벨 linkbase에서:
  - 모든 numeric facts (concept, value, period, dimensions)
  - 한국어 개념명 매핑 (concept_id → 한글 라벨)
를 추출한다.

stdlib xml.etree만 사용 (외부 의존성 0).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


XBRLI_NS = "http://www.xbrl.org/2003/instance"
LINK_NS = "http://www.xbrl.org/2003/linkbase"
XLINK_NS = "http://www.w3.org/1999/xlink"
XBRLDI_NS = "http://xbrl.org/2006/xbrldi"
XML_NS = "http://www.w3.org/XML/1998/namespace"


@dataclass(frozen=True)
class XbrlFact:
    concept: str
    value: float
    raw_value: str
    context_id: str
    unit_id: str | None
    decimals: int | None
    period_type: str
    period_start: str | None
    period_end: str | None
    dimensions: tuple[tuple[str, str], ...]

    def context_summary(self) -> str:
        if self.period_type == "instant":
            base = f"as of {self.period_end}"
        else:
            base = f"{self.period_start} ~ {self.period_end}"
        if self.dimensions:
            dim_str = "; ".join(f"{k.split(':')[-1]}={v.split(':')[-1]}" for k, v in self.dimensions)
            base += f" [{dim_str}]"
        return base


@dataclass(frozen=True)
class XbrlPackage:
    facts: list[XbrlFact]
    contexts: dict[str, dict]
    units: dict[str, str]
    label_map: dict[str, str]


def _localname(tag: str) -> tuple[str | None, str]:
    if tag.startswith("{"):
        ns, local = tag[1:].split("}", 1)
        return ns, local
    return None, tag


def _ns_prefix(ns: str | None, ns_map: dict[str, str]) -> str:
    if ns is None:
        return ""
    return ns_map.get(ns, ns)


def _build_ns_map(root: ET.Element) -> dict[str, str]:
    """Best-effort namespace URL → prefix map.

    DART는 fixed taxonomy + entity-specific extensions를 쓰므로 패턴으로 prefix 결정.
    """
    return {
        "http://xbrl.ifrs.org/taxonomy/2021-03-24/ifrs-full": "ifrs-full",
        "http://www.xbrl.org/2003/instance": "xbrli",
        "http://xbrl.org/2006/xbrldi": "xbrldi",
        "http://www.xbrl.org/2003/linkbase": "link",
        "http://www.xbrl.org/2003/iso4217": "iso4217",
        "http://www.xbrl.org/2003/XLink": "xl",
        "http://www.w3.org/1999/xlink": "xlink",
        "http://www.xbrl.org/dtr/type/numeric": "num",
        "http://www.xbrl.org/dtr/type/non-numeric": "nonnum",
    }


def _ns_prefix_smart(ns: str | None, ns_map: dict[str, str]) -> str:
    """패턴 기반 prefix 매핑."""
    if ns is None:
        return ""
    if ns in ns_map:
        return ns_map[ns]
    if ns.startswith("http://dart.fss.or.kr/taxonomy/") and "/ifrs/dart-gcd" in ns:
        return "dart-gcd"
    if ns.startswith("http://dart.fss.or.kr/taxonomy/") and "/ifrs/dart" in ns:
        return "dart"
    if ns.startswith("http://dart.fss.or.kr/taxonomy/") and "/entity" in ns:
        return "entity"
    if ns.startswith("http://dart.fss.or.kr/role/"):
        return "rol_dart"
    return ns


def _parse_decimals(d: str | None) -> int | None:
    if not d:
        return None
    if d == "INF":
        return None
    s = d.lstrip("-")
    if s.isdigit():
        return int(d)
    return None


def parse_xbrl_instance(path: Path) -> XbrlPackage:
    tree = ET.parse(path)
    root = tree.getroot()
    ns_map = _build_ns_map(root)

    contexts: dict[str, dict] = {}
    for ctx in root.findall(f"{{{XBRLI_NS}}}context"):
        ctx_id = ctx.get("id") or ""
        period_elem = ctx.find(f"{{{XBRLI_NS}}}period")
        if period_elem is None:
            continue
        instant = period_elem.find(f"{{{XBRLI_NS}}}instant")
        if instant is not None:
            period_type = "instant"
            period_start = None
            period_end = (instant.text or "").strip()
        else:
            period_type = "duration"
            s = period_elem.find(f"{{{XBRLI_NS}}}startDate")
            e = period_elem.find(f"{{{XBRLI_NS}}}endDate")
            period_start = (s.text or "").strip() if s is not None else None
            period_end = (e.text or "").strip() if e is not None else None

        dims: list[tuple[str, str]] = []
        seg = ctx.find(f"{{{XBRLI_NS}}}entity/{{{XBRLI_NS}}}segment")
        if seg is not None:
            for em in seg.findall(f"{{{XBRLDI_NS}}}explicitMember"):
                dim_name = em.get("dimension") or ""
                member = (em.text or "").strip()
                if dim_name:
                    dims.append((dim_name, member))
        contexts[ctx_id] = {
            "period_type": period_type,
            "period_start": period_start,
            "period_end": period_end,
            "dimensions": tuple(dims),
        }

    units: dict[str, str] = {}
    for u in root.findall(f"{{{XBRLI_NS}}}unit"):
        u_id = u.get("id") or ""
        measure = u.find(f"{{{XBRLI_NS}}}measure")
        if measure is not None:
            units[u_id] = (measure.text or "").strip()

    facts: list[XbrlFact] = []
    for elem in root:
        ns, local = _localname(elem.tag)
        if ns == XBRLI_NS or ns == LINK_NS:
            continue
        ctx_ref = elem.get("contextRef")
        if not ctx_ref:
            continue
        val_text = (elem.text or "").strip()
        if not val_text:
            continue
        try:
            value = float(val_text)
        except ValueError:
            continue
        prefix = _ns_prefix_smart(ns, ns_map)
        concept = f"{prefix}:{local}" if prefix else local
        ctx_info = contexts.get(ctx_ref, {})
        facts.append(
            XbrlFact(
                concept=concept,
                value=value,
                raw_value=val_text,
                context_id=ctx_ref,
                unit_id=elem.get("unitRef"),
                decimals=_parse_decimals(elem.get("decimals")),
                period_type=ctx_info.get("period_type", "?"),
                period_start=ctx_info.get("period_start"),
                period_end=ctx_info.get("period_end"),
                dimensions=ctx_info.get("dimensions", ()),
            )
        )

    return XbrlPackage(facts=facts, contexts=contexts, units=units, label_map={})


def parse_korean_labels(path: Path) -> dict[str, str]:
    """lab-ko.xml에서 concept_id → 한글 라벨 매핑 추출.

    XBRL 라벨 linkbase 구조:
      loc (concept_id 가리키는 locator) ← labelArc → label (실제 텍스트)
    """
    tree = ET.parse(path)
    root = tree.getroot()

    href_map: dict[str, str] = {}  # locator label → concept_id (from href)
    label_resources: dict[str, str] = {}  # label resource label → text
    arcs: list[tuple[str, str]] = []  # (from_label, to_label)

    for link_elem in root.iter():
        ns, local = _localname(link_elem.tag)
        if ns != LINK_NS:
            continue

        if local == "loc":
            href = link_elem.get(f"{{{XLINK_NS}}}href") or ""
            xlabel = link_elem.get(f"{{{XLINK_NS}}}label") or ""
            if "#" in href and xlabel:
                concept_id = href.split("#", 1)[1]
                href_map[xlabel] = concept_id

        elif local == "label":
            xlabel = link_elem.get(f"{{{XLINK_NS}}}label") or ""
            lang = link_elem.get(f"{{{XML_NS}}}lang") or ""
            role = link_elem.get(f"{{{XLINK_NS}}}role") or ""
            text = (link_elem.text or "").strip()
            if not text or not xlabel:
                continue
            if lang.startswith("ko"):
                # standard label role 우선 — 다른 role(periodStart/End 등)이 덮어쓰지 않도록
                if "/label" in role and not role.endswith("documentation"):
                    if xlabel not in label_resources or "/2003/role/label" in role:
                        label_resources[xlabel] = text

        elif local == "labelArc":
            from_lbl = link_elem.get(f"{{{XLINK_NS}}}from") or ""
            to_lbl = link_elem.get(f"{{{XLINK_NS}}}to") or ""
            if from_lbl and to_lbl:
                arcs.append((from_lbl, to_lbl))

    label_map: dict[str, str] = {}
    for from_lbl, to_lbl in arcs:
        concept_id = href_map.get(from_lbl)
        if not concept_id:
            continue
        text = label_resources.get(to_lbl)
        if text:
            label_map[concept_id] = text
    return label_map


def load_xbrl_package(xbrl_dir: Path) -> XbrlPackage:
    instance_files = list(xbrl_dir.glob("*.xbrl"))
    if not instance_files:
        raise FileNotFoundError(f"no .xbrl file in {xbrl_dir}")
    instance_path = instance_files[0]

    pkg = parse_xbrl_instance(instance_path)

    label_map: dict[str, str] = {}
    for ko_path in xbrl_dir.glob("*lab-ko.xml"):
        label_map.update(parse_korean_labels(ko_path))

    return XbrlPackage(
        facts=pkg.facts,
        contexts=pkg.contexts,
        units=pkg.units,
        label_map=label_map,
    )


def lookup_label(pkg: XbrlPackage, concept: str) -> str | None:
    """concept (예: ifrs-full:Revenue) → 한글 라벨. 없으면 None."""
    if concept in pkg.label_map:
        return pkg.label_map[concept]
    if ":" in concept:
        local = concept.split(":", 1)[1]
        for k, v in pkg.label_map.items():
            if k.endswith(local) or k == local:
                return v
    return None
