"""8개 섹션 + 메타 → 00_종합진단.md 합본 생성.

구조 (frame.md 5.3에 명시):
  1. 헤드라인 1줄
  2. 데이터 기준시점 박스
  3. 30초 회사 소개 (01에서 추출)
  4. 이번 분기 핵심 변화 (08에서 추출)
  5. TOC + 각 섹션 1문단 요약 (각 섹션 첫 단락)
  6. 본문 01~10 풀텍스트
  7. 종합 한 페이지 — owner-valuation (별도 LLM 호출 필요, optional)
"""
from __future__ import annotations

import re
from pathlib import Path

from pipeline import llm_client
from pipeline.frame_loader import FrameSpec
from pipeline.prompt_builder import DataTimestamps


SECTION_FILES = [
    "01_사업구조진단",
    "02_재무건강진단",
    "03_수익성진단",
    "04_자본활용진단",
    "05_업황과사이클진단",
    "06_경쟁포지션진단",
    "07_거버넌스리스크진단",
    "08_이번분기변화",
    "09_추적사항",
    "10_용어사전",
]


def _extract_first_paragraph(text: str) -> str:
    """섹션 본문에서 헤더·메타박스 제외 첫 의미 단락 추출."""
    lines = text.splitlines()
    in_box = False
    paragraphs: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        s = line.strip()
        if s.startswith("> **데이터 기준시점**") or (in_box and s.startswith(">")):
            in_box = True
            continue
        if in_box and not s.startswith(">"):
            in_box = False
        if s.startswith("#"):
            if current:
                paragraphs.append(current)
                current = []
            continue
        if s.startswith("---"):
            continue
        if not s:
            if current:
                paragraphs.append(current)
                current = []
            continue
        current.append(s)
    if current:
        paragraphs.append(current)
    for p in paragraphs:
        joined = " ".join(p)
        if len(joined) >= 50:
            return joined
    return paragraphs[0][0] if paragraphs and paragraphs[0] else ""


def _build_owner_valuation_prompt(
    frame: FrameSpec, company: str, period: str, all_sections_text: str
) -> tuple[str, str]:
    sys_prompt = (
        f"{frame.frame_md}\n\n---\n\n{frame.persona_md}\n\n---\n\n"
        f"# 너의 작업\n\n"
        f"너는 {company} {period} 종합진단 보고서의 **마지막 종합 한 페이지**를 작성한다.\n\n"
        f"## 톤 (페르소나 5절 owner mindset 엄격 적용)\n"
        f"- '이 회사를 시가총액 X조원에 통째로 살 수 있다면, 3년 후에도 매력 있는 회사인가? 살 만한가?'\n"
        f"- 주가 예측·매수권고 금지\n"
        f"- 결론은 단정적이지 않아도 됨, *왜 그렇게 보는지의 논리*가 본질\n"
        f"- 5~7줄 분량\n"
        f"- 출처는 인라인으로 [섹션 N] 형식으로 인용\n"
        f"- 페르소나 ★★★ 적신호·호재가 있다면 두드러지게 다룸\n\n"
        f"## 형식\n"
        f"```\n## 종합 한 페이지 — Owner valuation\n\n[5~7줄 본문]\n```"
    )
    user_prompt = (
        f"# 분석 대상\n{company} ({period})\n\n"
        f"# 8개 섹션 본문 (01~10)\n\n{all_sections_text}\n\n"
        f"위 섹션들을 통합 검토하여 owner-valuation 톤의 종합 한 페이지를 작성해라."
    )
    return sys_prompt, user_prompt


def assemble_report(
    report_dir: Path,
    company: str,
    period: str,
    timestamps: DataTimestamps,
    frame: FrameSpec | None = None,
    headline: str | None = None,
    write_owner_summary: bool = True,
) -> Path:
    """8개 섹션 final + 메타 → 00_종합진단.md 합본."""
    parts: list[str] = []
    parts.append(f"# {company} {period} 종합진단\n")
    if headline:
        parts.append(f"\n> **헤드라인:** {headline}\n")
    parts.append("\n")
    parts.append(timestamps.render_box())
    parts.append("\n---\n\n## 목차\n\n")
    for sec in SECTION_FILES:
        if (report_dir / f"{sec}.md").exists():
            anchor = sec.lower()
            parts.append(f"- [{sec}](#{anchor})\n")
    parts.append("\n## 각 섹션 한 문단 요약\n\n")
    section_texts: dict[str, str] = {}
    for sec in SECTION_FILES:
        sec_path = report_dir / f"{sec}.md"
        if not sec_path.exists():
            continue
        body = sec_path.read_text(encoding="utf-8")
        section_texts[sec] = body
        first = _extract_first_paragraph(body)
        parts.append(f"### {sec}\n\n{first}\n\n")
    parts.append("\n---\n\n## 본문\n\n")
    for sec in SECTION_FILES:
        if sec not in section_texts:
            parts.append(f"\n### {sec}\n\n(섹션 미생성)\n\n---\n\n")
            continue
        parts.append(section_texts[sec])
        parts.append("\n\n---\n\n")

    if write_owner_summary:
        if frame is None:
            from pipeline.frame_loader import load_frame
            frame = load_frame()
        all_text = "\n\n".join(
            f"## {sec}\n\n{section_texts[sec]}" for sec in SECTION_FILES if sec in section_texts
        )
        sys_p, user_p = _build_owner_valuation_prompt(frame, company, period, all_text)
        owner_text = llm_client.generate_section(sys_p, user_p)
        parts.append(owner_text)
    else:
        parts.append(
            "\n## 종합 한 페이지 — Owner valuation\n\n"
            f"*{company}을 시가총액 X조원에 통째로 살 수 있다면, 3년 후에도 매력 있는 회사인가?*\n\n"
            "(이 페이지는 별도 LLM 호출로 자동 작성됩니다 — `--with-summary` 플래그 사용)\n"
        )

    target = report_dir / "00_종합진단.md"
    target.write_text("".join(parts), encoding="utf-8")
    return target
