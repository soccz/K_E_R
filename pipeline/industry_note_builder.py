"""산업노트 generator (frame.md §6 주말판).

매주 일요일 21:00 KST k_e_r-weekend.timer가 호출.
워치리스트 13섹터 중 "가장 오래 다루지 않은 + 외부 변수 변화 큰" 섹터를 자동 선정 →
그 섹터의 워치리스트 종목들 비교 페어 노트 1편.

frame.md §6.2 구조:
  1. 한 줄 요약
  2. 데이터 기준시점 박스
  3. 30초 산업 소개
  4. 이번 주 흥미로운 이유 (트리거 — 그 주 공시·이벤트)
  5. 워치리스트 안의 종목들 — 한 줄씩 비교 표
  6. 종목 간 차이를 만드는 변수 3개 (이게 핵심)
  7. 사이클 지점 — 외부 변수 영향
  8. 비유로 이해하기
  9. 다음 변곡점 (이벤트·공시 캘린더)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SectorPickResult:
    """그 주 다룰 섹터 1개 + 선정 근거."""

    sector: str
    tickers: list[str]  # 그 섹터의 워치리스트 종목 코드들
    company_names: list[str]
    last_covered_iso_week: str | None  # 가장 최근에 다룬 ISO 주차 (없으면 None)
    weeks_since_last: int  # 마지막으로 다룬 후 경과 주
    recent_dart_count: int  # 그 주 DART 신규 공시 수
    score: float


@dataclass(frozen=True)
class IndustryNote:
    """산업노트 1편."""

    iso_week: str  # YYYY-WNN
    sector: str
    fetch_date: str
    headline: str
    summary_one_line: str
    sector_intro_30s: str
    weekly_trigger: str
    ticker_comparison_table: list[dict]  # [{ticker, name, market_cap_t, change_60d, ...}]
    differentiating_factors: list[str]  # 3개
    cycle_position: str
    analogy: str
    next_milestones: list[str]
    notes: list[str] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)
    raw_llm_text: str = ""

    def to_markdown(self) -> str:
        out = [f"# {self.iso_week} — {self.sector} 산업노트"]
        out.append("")
        out.append(f"> {self.summary_one_line}")
        out.append("")
        out.append(
            f"> **데이터 기준시점**: 작성일 {self.fetch_date} · ISO {self.iso_week} · "
            f"DART list.json + KRX OHLCV + 워치리스트 _watchlist.md"
        )
        out.append("")
        out.append("## 30초 산업 소개")
        out.append("")
        out.append(self.sector_intro_30s)
        out.append("")
        out.append("## 이번 주 흥미로운 이유")
        out.append("")
        out.append(self.weekly_trigger)
        out.append("")
        out.append("## 종목 비교")
        out.append("")
        if self.ticker_comparison_table:
            cols = list(self.ticker_comparison_table[0].keys())
            out.append("| " + " | ".join(cols) + " |")
            out.append("|" + "|".join("---" for _ in cols) + "|")
            for row in self.ticker_comparison_table:
                out.append("| " + " | ".join(str(row.get(c, "")) for c in cols) + " |")
        out.append("")
        out.append("## 종목 간 차이를 만드는 변수 3개")
        out.append("")
        for i, f in enumerate(self.differentiating_factors, 1):
            out.append(f"{i}. {f}")
        out.append("")
        out.append("## 사이클 지점")
        out.append("")
        out.append(self.cycle_position)
        out.append("")
        out.append("## 비유로 이해하기")
        out.append("")
        out.append(self.analogy)
        out.append("")
        out.append("## 다음 변곡점")
        out.append("")
        for m in self.next_milestones:
            out.append(f"- {m}")
        out.append("")
        out.append("---")
        out.append(
            "> **목적**: 본 산업노트는 매수·매도 권고가 아닌 *섹터 페어 비교 관찰*. "
            "frame.md §6 주말판 + 페르소나 §1.2 미국 시장 검증·§1.4 3년 단위 트랙 적용."
        )
        if self.notes:
            for n in self.notes:
                out.append(f"> {n}")
        return "\n".join(out)

    @property
    def is_valid(self) -> bool:
        if not self.summary_one_line or self.summary_one_line.startswith("(LLM"):
            return False
        if not self.differentiating_factors or len(self.differentiating_factors) < 2:
            return False
        return True

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_markdown(), encoding="utf-8")
        if self.raw_llm_text:
            raw_dir = path.parent / "_raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            (raw_dir / f"{self.iso_week}-{self.sector}.txt").write_text(
                self.raw_llm_text, encoding="utf-8"
            )


# ────────────────────────────────────────────────────────────────────
# 섹터 선정 (frame.md §6.3 우선순위)
# ────────────────────────────────────────────────────────────────────


def _existing_iso_weeks_by_sector(industry_dir: Path) -> dict[str, list[str]]:
    """industry_notes/<YYYY-WNN>-<섹터>.md 파일들 스캔 → 섹터별 작성 이력."""
    out: dict[str, list[str]] = {}
    if not industry_dir.exists():
        return out
    for p in sorted(industry_dir.glob("*.md")):
        stem = p.stem
        # 형식: 2026-W18-반도체
        parts = stem.split("-", 2)
        if len(parts) != 3:
            continue
        iso_week = f"{parts[0]}-{parts[1]}"
        sector = parts[2]
        out.setdefault(sector, []).append(iso_week)
    return out


def _current_iso_week() -> str:
    now = datetime.now()
    iso = now.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _weeks_between(iso_a: str, iso_b: str) -> int:
    """두 ISO 주차 사이의 주 수 (b - a)."""
    try:
        ya, wa = iso_a.split("-W")
        yb, wb = iso_b.split("-W")
        # 주를 월요일 기준으로 변환
        from datetime import date

        date_a = date.fromisocalendar(int(ya), int(wa), 1)
        date_b = date.fromisocalendar(int(yb), int(wb), 1)
        return (date_b - date_a).days // 7
    except Exception:
        return 0


def pick_sector(
    watchlist_entries: list,
    industry_dir: Path,
    sector_dart_counts: dict[str, int] | None = None,
) -> SectorPickResult | None:
    """frame.md §6.3 우선순위로 그 주 다룰 섹터 1개 선정.

    1. 가장 오래 다루지 않은 섹터 (가산점 ↑)
    2. 그 주 DART 공시가 많은 섹터 (가산점 ↑)
    3. 단일 종목만 있는 섹터는 제외 (페어 비교 불가)
    """
    from collections import defaultdict

    sectors: dict[str, list] = defaultdict(list)
    for e in watchlist_entries:
        sec = getattr(e, "sector", None) or "기타"
        sectors[sec].append(e)

    # 단일 종목 섹터 제외 (페어 비교 못 함)
    candidates = {s: ents for s, ents in sectors.items() if len(ents) >= 2}
    if not candidates:
        return None

    history = _existing_iso_weeks_by_sector(industry_dir)
    current = _current_iso_week()

    sector_dart_counts = sector_dart_counts or {}

    best: SectorPickResult | None = None
    for sec, ents in candidates.items():
        last_weeks = history.get(sec, [])
        last_iso = max(last_weeks) if last_weeks else None
        weeks_since = _weeks_between(last_iso, current) if last_iso else 999
        dart_count = sector_dart_counts.get(sec, 0)
        # 점수: 오래 안 다룬 섹터 가산 + 공시 많은 섹터 가산
        score = weeks_since * 1.0 + dart_count * 2.0
        if best is None or score > best.score:
            best = SectorPickResult(
                sector=sec,
                tickers=[e.ticker for e in ents],
                company_names=[e.name for e in ents],
                last_covered_iso_week=last_iso,
                weeks_since_last=min(weeks_since, 999),
                recent_dart_count=dart_count,
                score=score,
            )
    return best


# ────────────────────────────────────────────────────────────────────
# 섹터 종목 데이터 fetch (KRX·DART·캐시 활용)
# ────────────────────────────────────────────────────────────────────


def fetch_sector_ticker_data(
    tickers: list[str],
    cache_dir: Path | None = None,
) -> list[dict]:
    """섹터 워치리스트 종목들의 ticker_market 캐시에서 비교 데이터 추출."""
    cache_dir = cache_dir or Path("/home/soccz/22tb/report/pipeline/cache")
    out: list[dict] = []
    for t in tickers:
        cache_path = cache_dir / f"ticker_market_{t}.json"
        if not cache_path.exists():
            out.append({"ticker": t, "available": False})
            continue
        try:
            d = json.loads(cache_path.read_text(encoding="utf-8"))
            out.append(
                {
                    "ticker": t,
                    "available": True,
                    "company": d.get("company_name"),
                    "latest_close_krw": d.get("latest_close_krw"),
                    "market_cap_trillion_krw": d.get("market_cap_trillion_krw"),
                    "change_60d_pct": d.get("close_60d_pct_change"),
                    "change_1y_pct": d.get("close_1y_pct_change"),
                }
            )
        except Exception:
            out.append({"ticker": t, "available": False})
    return out


# ────────────────────────────────────────────────────────────────────
# LLM 프롬프트 + 빌드
# ────────────────────────────────────────────────────────────────────


def _build_llm_prompts(
    sector: str,
    iso_week: str,
    fetch_date: str,
    ticker_data: list[dict],
    weekly_dart_summary: str,
) -> tuple[str, str]:
    try:
        from pipeline.frame_loader import load_frame
        frame = load_frame()
        persona = frame.persona_md
        frame_md = frame.frame_md
    except ImportError:
        persona = ""
        frame_md = ""

    sys_prompt = (
        f"{persona}\n\n---\n\n{frame_md}\n\n---\n\n"
        f"# 너의 작업\n\n"
        f"K_E_R 주말판 산업노트 1편 작성. 섹터: **{sector}** ({iso_week}).\n"
        f"frame.md §6.2 구조 9개 항목을 모두 채워라.\n\n"
        f"## 톤 절대 규칙\n"
        f"- 페르소나 §1.4 3년 단위 기술 트랙 + §1.2 미국 시장 검증 적용\n"
        f"- 매수·매도 권고·% 예측 금지 (페르소나 §8)\n"
        f"- 학술/관찰 톤 (해석된다·관찰된다·검증 포인트)\n"
        f"- 종목 간 차이 변수 3개는 *구체적*으로 (기술·고객·자본 등)\n"
        f"- 비유는 그 섹터 *고유 사실*에 박혀야 (페르소나 §10)\n\n"
        f"## 출력 형식 (JSON)\n"
        f'```json\n{{\n'
        f'  "headline": "1줄 헤드라인 (★/★★ 신호 톤)",\n'
        f'  "summary_one_line": "1줄 요약 (관찰 톤)",\n'
        f'  "sector_intro_30s": "30초 산업 소개 — 비전문가도 이해 (3-4줄)",\n'
        f'  "weekly_trigger": "이번 주 흥미로운 이유 — 공시·이벤트 (3-5줄)",\n'
        f'  "differentiating_factors": ["변수 1", "변수 2", "변수 3"],\n'
        f'  "cycle_position": "사이클 지점 — 외부 변수 영향 (3-4줄)",\n'
        f'  "analogy": "그 섹터 고유 비유 1줄",\n'
        f'  "next_milestones": ["변곡점 1", "변곡점 2", "변곡점 3"]\n'
        f'}}\n```'
    )

    user_payload = {
        "sector": sector,
        "iso_week": iso_week,
        "fetch_date": fetch_date,
        "tickers": ticker_data,
        "weekly_dart_summary": weekly_dart_summary,
    }
    user_prompt = (
        f"# 섹터 데이터\n\n```json\n{json.dumps(user_payload, ensure_ascii=False, indent=2)}\n```\n\n"
        f"위 JSON 형식으로만 산업노트 작성."
    )
    return sys_prompt, user_prompt


def _parse_llm_json(text: str) -> dict | None:
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    else:
        s, e = text.find("{"), text.rfind("}")
        if s >= 0 and e > s:
            text = text[s : e + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


import re


def build_industry_note(
    sector_pick: SectorPickResult,
    cache_dir: Path | None = None,
    weekly_dart_summary: str = "",
    llm_call: Any = None,
) -> IndustryNote | None:
    fetch_date = datetime.now().strftime("%Y-%m-%d")
    ticker_data = fetch_sector_ticker_data(sector_pick.tickers, cache_dir=cache_dir)

    sys_p, user_p = _build_llm_prompts(
        sector_pick.sector,
        _current_iso_week(),
        fetch_date,
        ticker_data,
        weekly_dart_summary,
    )

    if llm_call is None:
        try:
            from pipeline.llm_client import generate_section
            llm_call = generate_section
        except ImportError:
            llm_call = None

    raw_text = ""
    parsed: dict = {}
    if llm_call is not None:
        try:
            raw_text = llm_call(sys_p, user_p, max_tokens=2400)
            parsed = _parse_llm_json(raw_text) or {}
        except Exception as e:
            parsed = {"summary_one_line": f"(LLM 호출 실패 — {e})"}

    # 비교 표 데이터 정리
    comparison_table = []
    for d in ticker_data:
        if not d.get("available"):
            continue
        mc = d.get("market_cap_trillion_krw")
        c60 = d.get("change_60d_pct")
        comparison_table.append(
            {
                "종목": d.get("company") or d["ticker"],
                "코드": d["ticker"],
                "시총(조)": f"{mc:.1f}" if mc else "—",
                "60일": f"{c60:+.1f}%" if c60 is not None else "—",
                "1년": f"{d.get('change_1y_pct'):+.1f}%" if d.get("change_1y_pct") is not None else "—",
            }
        )

    iso_week = _current_iso_week()

    return IndustryNote(
        iso_week=iso_week,
        sector=sector_pick.sector,
        fetch_date=fetch_date,
        headline=parsed.get("headline", f"{sector_pick.sector} {iso_week}"),
        summary_one_line=parsed.get(
            "summary_one_line", f"({sector_pick.sector} 섹터 {iso_week} 관찰 노트 — LLM 출력 미확보)"
        ),
        sector_intro_30s=parsed.get("sector_intro_30s", ""),
        weekly_trigger=parsed.get("weekly_trigger", ""),
        ticker_comparison_table=comparison_table,
        differentiating_factors=parsed.get("differentiating_factors", []) or [],
        cycle_position=parsed.get("cycle_position", ""),
        analogy=parsed.get("analogy", ""),
        next_milestones=parsed.get("next_milestones", []) or [],
        notes=[
            f"섹터 선정: '{sector_pick.sector}' · 마지막 다룬 후 {sector_pick.weeks_since_last}주 · "
            f"이번 주 DART 신규 {sector_pick.recent_dart_count}건 · 점수 {sector_pick.score:.1f}",
        ],
        sources={
            "tickers": "ticker_market 캐시 (KRX OHLCV + DART 발행주식수)",
            "weekly_dart": "DART list.json",
            "frame": "frame.md §6 주말판 spec",
        },
        raw_llm_text=raw_text,
    )
