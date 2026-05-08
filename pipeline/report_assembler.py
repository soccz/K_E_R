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
    frame: FrameSpec,
    company: str,
    period: str,
    all_sections_text: str,
    market_snapshot: dict | None = None,
    foreign_snapshot: dict | None = None,
) -> tuple[str, str]:
    market_block = ""
    if market_snapshot:
        import json as _json

        market_block = (
            f"\n# 시장 스냅샷 (시가총액·종가) — owner-valuation의 X 값\n"
            f"```json\n{_json.dumps(market_snapshot, ensure_ascii=False, indent=2)}\n```\n"
            f"위 시가총액(market_cap_trillion_krw)을 owner-valuation 본문에 반드시 인용해라. "
            f"수치가 None이면 '확인되지 않음 — 시장 데이터 미통합'으로 명시.\n"
        )
    foreign_block = ""
    if foreign_snapshot:
        import json as _json

        foreign_block = (
            f"\n# 외국인 보유 스냅샷 (★★★ 페르소나)\n"
            f"```json\n{_json.dumps(foreign_snapshot, ensure_ascii=False, indent=2)}\n```\n"
            f"DART 5% 이상 보유공시 표본만 잡힌다. 전체 외인 비중·추세는 잡히지 않으면 "
            f"'확인되지 않음 (KRX 일별 잔고 별도 데이터 필요)'으로 표시.\n"
        )

    sys_prompt = (
        f"{frame.frame_md}\n\n---\n\n{frame.persona_md}\n\n---\n\n"
        f"# 너의 작업\n\n"
        f"너는 {company} {period} 종합진단 보고서의 **마지막 종합 한 페이지**를 작성한다.\n\n"
        f"## 톤 (페르소나 5절 owner mindset 엄격 적용)\n"
        f"- '이 회사를 시가총액 X조원에 통째로 살 수 있다면, 3년 후에도 매력 있는 회사인가? 살 만한가?'\n"
        f"- **반드시 시가총액(market_cap_trillion_krw)을 인용**해라. 인용 못 하면 그 사실 자체를 한 줄 명시.\n"
        f"- **시총 / 연 FCF 배수**를 직접 계산해 본문에 적어라 (예: '시총 1,204조 / FCF 25.85조 = 약 47배 — 사이클 정점 이익이 영속한다는 가정').\n"
        f"- **입장을 정해라.** '그러나 이런 가능성도 있다' 식의 양다리 결론 금지.\n"
        f"  현재 가격 수준에서 살 만한가, 아닌가, 어떤 조건이면 살 만한가 — 입장과 *왜 그렇게 보는지의 논리*.\n"
        f"- 비판적·회의적이 기본 톤 (페르소나 2절). 호재는 시장이 알아서 반영한다 — 너는 위험을 본다.\n"
        f"- 주가 예측·매수권고·목표가 금지\n"
        f"\n"
        f"## 페르소나 ★★★ 신호 의무 단락 (모두 본문에 등장해야 함)\n"
        f"- **영업CF vs 영업이익 괴리**: 호재인지 적신호인지 한 줄.\n"
        f"- **미국 시장 검증**: 미국 빅테크·인증·IR로 검증된 매출이 어느 정도인지.\n"
        f"- **3년 기술 트랙**: 방향성·일관성이 흔들렸는지 유지됐는지.\n"
        f"- **외인 vs 국내 자금 디커플링**: ticker_snapshot의 close_60d/1y_pct_change와 foreign_holding 데이터를 *교차*해서 분석.\n"
        f"  - 주가 1년 등락률이 +50% 이상이면 '국내 환호가 강한 상태' — 페르소나 §1.7 역지표.\n"
        f"  - 외인 추세가 *확인되지 않음*이면, '국내 환호 + 외인 미확인 = 디커플링 여부 판단 불가'를 명시적으로 짚어라.\n"
        f"  - DART 5%↑ 보유공시가 있으면 글로벌 장기 기관(BlackRock·Vanguard·Norges·연기금) 인지 확인하고 인용.\n"
        f"- **압도적 기술 보유 종목**이면: 주주에게 귀속될 몫을 IP 보호·인수 시나리오 관점에서 한 줄 검토.\n"
        f"\n"
        f"## 분량·형식\n"
        f"- 8~12줄 분량 (입장 한 줄 + ★★★ 호재 단락 + ★★★ 리스크 단락 + ★★★ 외인 단락 + 압도적 기술 한 줄 + 결론 한 줄)\n"
        f"- 출처는 인라인으로 [섹션 N] 형식으로 인용\n"
        f"- 형식:\n"
        f"```\n## 종합 한 페이지 — Owner valuation\n\n[본문]\n```"
    )
    user_prompt = (
        f"# 분석 대상\n{company} ({period})\n\n"
        f"{market_block}"
        f"{foreign_block}"
        f"# 8개 섹션 본문 (01~10)\n\n{all_sections_text}\n\n"
        f"위 섹션들을 통합 검토하여 owner-valuation 톤의 종합 한 페이지를 작성해라. "
        f"시가총액·외인 스냅샷이 제공된 경우 반드시 인용. 빈 데이터는 '확인되지 않음'으로 정직히 표시."
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
    market_snapshot: dict | None = None,
    foreign_snapshot: dict | None = None,
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
        sys_p, user_p = _build_owner_valuation_prompt(
            frame,
            company,
            period,
            all_text,
            market_snapshot=market_snapshot,
            foreign_snapshot=foreign_snapshot,
        )
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
