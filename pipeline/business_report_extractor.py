"""사업보고서 본문 HTML에서 페르소나·프레임 우선 항목 절단.

사업보고서는 정해진 목차(I. 회사의 개요, II. 사업의 내용 ...)가 있다.
페르소나 우선 정보가 모이는 섹션:
  - II.4 매출 및 수주상황 — 지역별·제품별 매출 (★★★ 페르소나 매출 비중 점검)
  - I.4 신용평가에 관한 사항 — 신용등급 변동
  - II.7 주요 계약 — 라이선스·OEM 등
  - III.4 자금 조달 등의 현황 — 차입금 만기 분포
  - IV.4 주식의 총수 등 — 자기주식·교환사채

본 모듈은 회사가 제출한 본문 HTML 파일 모음에서 위 섹션의 텍스트를 절단해
LLM 프롬프트에 분리 주입할 수 있도록 한다. 토큰 한도 절약 + LLM이 핵심 표를
'못 본' 채로 추론하는 사고 차단.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


# 매핑 — 섹션 키 → 본문에서 찾을 헤더 패턴 (sub-string 검색, 대소문자/공백 관대)
_SECTION_PATTERNS: dict[str, list[str]] = {
    "II.4_매출및수주상황": [
        "매출 및 수주상황",
        "매출및수주상황",
        "수주상황",
    ],
    "II.4a_주요매출처": [  # NVIDIA 90% 의존 같은 단일 고객 노출도 — 페르소나 §1.8 IP 양면성
        "주요 매출처",
        "주요 거래처",
        "주요 고객",
        "단일 매출처",
    ],
    "I.4_신용평가": [
        "신용평가에 관한 사항",
        "신용평가",
    ],
    "I.6_주가현황": [  # 보고기준일 종가·시가총액 — owner-valuation 'X조' 채움
        "주가에 관한 사항",
        "주가의 현황",
        "주가 추이",
        "보고서 작성기준일",
    ],
    "II.7_주요계약": [
        "주요 계약",
        "주요계약 및 연구활동",
        "주요계약·연구개발활동",
    ],
    "II.8_연구개발": [
        "연구개발활동",
        "연구개발 활동",
    ],
    "III.4_자금조달": [
        "자금 조달 등의 현황",
        "자금조달",
        "차입금",
    ],
    "III.5_금융위험_환율민감도": [  # 페르소나 매크로 ★ 환율 정량 분해
        "금융위험관리",
        "환율 위험",
        "외환 위험",
        "환율위험",
        "외환위험",
        "민감도 분석",
    ],
    "III.6_차입금만기": [  # 페르소나 ★★ "차입금 만기 집중" 적신호
        "차입금 만기",
        "장기차입금",
        "사채",
        "약정사항",
    ],
    "IV.4_주식총수": [
        "주식의 총수 등",
        "주식의 총수",
        "자기주식",
    ],
    "VI.1_주주현황": [  # 외국인 보유 비중·5%↑ 주주 — 페르소나 ★★★ 외인 추세 보조
        "주주에 관한 사항",
        "주주현황",
        "최대주주 및 그 특수관계인",
        "5%이상 주주",
    ],
    "VII.1_연구개발실적": [  # HBM·DDR5 마일스톤 (06_경쟁포지션진단의 1순위 출처)
        "연구개발 실적",
        "연구개발실적",
        "기술개발 실적",
    ],
}


@dataclass(frozen=True)
class ExtractedSection:
    section_key: str
    found_pattern: str | None
    text: str  # 잘라낸 본문 (taglevel 제거된 plain)
    char_count: int
    source_file: str


@dataclass(frozen=True)
class BusinessReportExtraction:
    sections: dict[str, list[ExtractedSection]] = field(default_factory=dict)

    def to_prompt_dict(self, max_chars_per_section: int = 8000) -> dict:
        out: dict = {}
        for key, hits in self.sections.items():
            joined = "\n\n--- 다음 본문 조각 ---\n\n".join(
                h.text for h in hits if h.text
            )
            if len(joined) > max_chars_per_section:
                joined = joined[:max_chars_per_section] + "\n... [잘림]"
            out[key] = joined
        out["_usage_rule"] = (
            "위 섹션 텍스트는 사업보고서 본문에서 직접 잘라온 것이다. "
            "지역별·제품별 매출 비중, 신용등급, 주요계약 등 페르소나 ★★★ 항목의 "
            "1순위 출처. 이 안에 숫자가 있으면 본문에서 인용해라. 비어 있으면 "
            "'확인되지 않음 — 사업보고서 본문에서 잡히지 않음'으로 처리."
        )
        return out


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\xa0　]+")
_NL_RE = re.compile(r"\n{3,}")


def _strip_html(text: str) -> str:
    text = _TAG_RE.sub("", text)
    text = _WS_RE.sub(" ", text)
    text = _NL_RE.sub("\n\n", text)
    return text.strip()


def _slice_around_pattern(text: str, pattern: str, window_after: int = 12000) -> str | None:
    """패턴이 처음 등장한 위치에서 window_after 글자 잘라낸다.

    다음 같은 레벨 헤더(I. / II. / III. / IV. / V. / VI. / VII.) 만나면 더 일찍 끝.
    sub-section(예: 'II.4', '4.') 헤더는 무시 — 단독 로마숫자.절제 형식만 컷.
    """
    idx = text.find(pattern)
    if idx == -1:
        return None
    end = idx + window_after
    next_section_re = re.compile(r"\n\s*([IVX]+)\.\s+[^\n]+\n")
    m = next_section_re.search(text, pos=idx + len(pattern))
    if m:
        end = min(end, m.start())
    return text[idx:end]


def extract_from_html(
    html_path: Path,
    section_keys: list[str] | None = None,
) -> list[ExtractedSection]:
    """단일 HTML 파일에서 섹션 절단."""
    if section_keys is None:
        section_keys = list(_SECTION_PATTERNS.keys())
    try:
        raw = html_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    plain = _strip_html(raw)

    out: list[ExtractedSection] = []
    for key in section_keys:
        for pat in _SECTION_PATTERNS.get(key, []):
            sliced = _slice_around_pattern(plain, pat)
            if sliced:
                out.append(
                    ExtractedSection(
                        section_key=key,
                        found_pattern=pat,
                        text=sliced,
                        char_count=len(sliced),
                        source_file=html_path.name,
                    )
                )
                break  # 같은 key에서 첫 매치만
    return out


def extract_from_filing_dir(
    filing_dir: Path,
    section_keys: list[str] | None = None,
) -> BusinessReportExtraction:
    """raw_inputs/dart_filings/ 폴더 안 모든 HTML/XML에서 섹션 절단 통합."""
    sections: dict[str, list[ExtractedSection]] = {}
    if not filing_dir.exists():
        return BusinessReportExtraction(sections=sections)
    for path in sorted(filing_dir.iterdir()):
        if path.suffix.lower() not in (".html", ".htm", ".xml", ".xhtml"):
            continue
        for sec in extract_from_html(path, section_keys=section_keys):
            sections.setdefault(sec.section_key, []).append(sec)
    return BusinessReportExtraction(sections=sections)
