"""일간 메모 생성기 (Phase C).

`daily_trigger.evaluate_all_triggers()`가 트리거 통과를 보고하면 본 모듈이:
  1. 트리거 통과 종목의 60일 시계열 + 매매 데이터 fetch
  2. 매크로 스냅샷 fetch (KOSPI/USD-KRW/WTI)
  3. LLM 호출 — 학술/연구 톤으로 1면 메모 생성
  4. SVG 스파크라인 데이터 산출 (마크다운에 포함)
  5. `daily_notes/<YYYY-MM-DD>.md` 저장

페르소나·spec 정합:
  - _persona.md 100% (출처 엄격주의·비관 편향·매수권고 금지)
  - _daily_note_spec.md (학술 어휘·1면·관찰·종목 카드)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pipeline.daily_trigger import TriggerHit, TriggerReport


@dataclass(frozen=True)
class SparklinePoints:
    """60일 종가 시계열 → SVG polyline points (정규화 0~1)."""

    raw_closes: list[float]
    dates: list[str]
    min_value: float
    max_value: float
    normalized_points: list[tuple[float, float]]  # (x 0~1, y 0~1) — y는 위→아래로 0=고가

    def to_svg_polyline_str(self, width: int = 120, height: int = 30) -> str:
        """SVG polyline points="x1,y1 x2,y2 ..." 문자열."""
        if not self.normalized_points:
            return ""
        return " ".join(
            f"{x * width:.1f},{y * height:.1f}"
            for x, y in self.normalized_points
        )

    def to_svg_with_axis(self, width: int = 200, height: int = 50, label: str = "") -> str:
        """축·툴팁이 있는 SVG. 브라우저 native title로 hover 시 첫·마지막 값 표시."""
        if not self.normalized_points or not self.raw_closes:
            return ""
        polyline = self.to_svg_polyline_str(width, height - 12)
        first = self.raw_closes[0]
        last = self.raw_closes[-1]
        first_date = self.dates[0] if self.dates else ""
        last_date = self.dates[-1] if self.dates else ""
        change_pct = (last / first - 1) * 100 if first else 0
        cls = (
            "spark-up" if change_pct > 0.5
            else "spark-down" if change_pct < -0.5
            else "spark-flat"
        )
        # 시작값·끝값을 SVG 좌상·우상에 작은 텍스트로
        first_str = f"{first:,.0f}"
        last_str = f"{last:,.0f}"
        max_str = f"max {self.max_value:,.0f}"
        min_str = f"min {self.min_value:,.0f}"
        title = (
            f"{label}\n시작 ({first_date}): {first_str}\n현재 ({last_date}): {last_str}\n"
            f"변화: {change_pct:+.1f}%"
        )
        return (
            f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            f'class="dn-spark {cls}">'
            f'<title>{title}</title>'
            f'<polyline points="{polyline}" fill="none" stroke-width="1.5" '
            f'vector-effect="non-scaling-stroke" transform="translate(0,8)"/>'
            f'<text x="2" y="6" class="dn-spark-label">{first_str}</text>'
            f'<text x="{width - 2}" y="6" class="dn-spark-label" text-anchor="end">{last_str}</text>'
            f'</svg>'
        )


@dataclass(frozen=True)
class TickerCardData:
    """일간 메모의 종목 카드 1개에 들어가는 데이터."""

    ticker: str
    company_name: str
    today_close: float
    today_date: str
    pct_change: float
    sparkline_60d: SparklinePoints
    sector: str | None
    trigger_hits: list[TriggerHit]
    foreign_3d_krw: float | None  # placeholder (KRX 계정 v0.4 후 활성)
    volume_z_score: float | None
    avg_volume_60d: float | None
    llm_comment: str = ""  # LLM이 작성한 학술 톤 멘트 2~3줄


@dataclass(frozen=True)
class MacroIndicator:
    """매크로 스냅샷 1개 (KOSPI/USD-KRW/WTI 등)."""

    label: str
    latest: float
    latest_str: str
    change_pct_1d: float | None
    change_pct_60d: float | None
    sparkline: SparklinePoints | None


@dataclass(frozen=True)
class DailyNote:
    """완성된 일간 메모 1면."""

    fetch_date: str  # YYYY-MM-DD
    headline: str  # 트리거 헤드라인 1줄
    macro_indicators: list[MacroIndicator]
    observation: str  # 관찰 3~4줄 (LLM 생성)
    ticker_cards: list[TickerCardData]
    sector_tone: dict[str, str]  # {"반도체": "↑", ...}
    triggers_summary: str  # "외인 +500억 + 가격 -7% + 잠정실적"
    notes: list[str] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)
    raw_llm_text: str = ""  # LLM이 만든 본문 (관찰·카드 멘트)

    def to_markdown(self) -> str:
        """spec §2 형식 그대로 마크다운 1면 생성."""
        out: list[str] = []
        out.append(f"# {self.fetch_date} 일간 메모            {self.headline}")
        out.append("")
        out.append(f"## 매크로 ({self.fetch_date} 기준)")
        out.append("")
        out.append("| 지표 | 값 | 1일 | 60일 | 추세 |")
        out.append("|---|---|---|---|---|")
        for m in self.macro_indicators:
            d1 = f"{m.change_pct_1d:+.2f}%" if m.change_pct_1d is not None else "n/a"
            d60 = f"{m.change_pct_60d:+.1f}%" if m.change_pct_60d is not None else "n/a"
            spark = (
                m.sparkline.to_svg_with_axis(width=140, height=36, label=f"{m.label} 60일")
                if m.sparkline
                else "—"
            )
            out.append(f"| {m.label} | {m.latest_str} | {d1} | {d60} | {spark} |")
        out.append("")

        if self.observation:
            out.append("## 관찰")
            out.append("")
            out.append(self.observation)
            out.append("")

        if self.ticker_cards:
            out.append("## 종목 카드")
            out.append("")
            for c in self.ticker_cards:
                arrow = "▲" if c.pct_change > 0 else "▼" if c.pct_change < 0 else "→"
                out.append(
                    f"### {c.company_name} ({c.ticker})  "
                    f"[{c.sector or '?'}]  {arrow} {c.pct_change:+.2f}%"
                )
                out.append("")
                spark = c.sparkline_60d.to_svg_with_axis(
                    width=240, height=54, label=f"{c.company_name} 60일 종가"
                )
                out.append(f"60일 종가 시계열: {spark}")
                out.append("")
                # 트리거 데이터 1줄
                trig_lines = []
                for h in c.trigger_hits:
                    if h.trigger_type == "price_move":
                        trig_lines.append(f"가격 {h.detail.get('pct_change'):+.2f}%")
                    elif h.trigger_type == "dart_disclosure":
                        trig_lines.append(f"공시: {h.detail.get('report_nm')[:50]}")
                    elif h.trigger_type == "foreign_flow":
                        trig_lines.append(f"외인 3일 {h.detail.get('cumulative_krw', 0)/1e8:+.0f}억")
                    elif h.trigger_type == "decoupling":
                        trig_lines.append("외인-국내 디커플링")
                if trig_lines:
                    out.append("**트리거**: " + " · ".join(trig_lines))
                    out.append("")
                if c.llm_comment:
                    out.append(c.llm_comment.strip())
                    out.append("")

            out.append("")

        if self.sector_tone:
            out.append("## 섹터 관찰")
            out.append("")
            tone_str = "    ".join(
                f"{k} {v}" for k, v in self.sector_tone.items()
            )
            out.append(tone_str)
            out.append("")

        out.append("---")
        out.append(f"> **트리거**: {self.triggers_summary}")
        out.append(
            "> **목적**: 본 노트는 매수·매도 권고가 아닌 *공개 관찰 기록*. "
            "가설·검증 중심 (페르소나 §5 owner mindset + 학술 톤)."
        )
        if self.notes:
            for n in self.notes:
                out.append(f"> {n}")

        return "\n".join(out)

    def save(self, path: Path) -> None:
        """마크다운 저장 + raw LLM 텍스트는 _raw/<date>.txt로 별도 저장.

        raw 저장 목적: 톤 캘리브레이션 시 'LLM이 왜 그렇게 나왔나' 추적.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_markdown(), encoding="utf-8")
        if self.raw_llm_text:
            raw_dir = path.parent / "_raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            (raw_dir / f"{self.fetch_date}.txt").write_text(
                self.raw_llm_text, encoding="utf-8"
            )

    @property
    def is_valid(self) -> bool:
        """LLM 호출 실패한 메모는 사이트 push 차단용."""
        if not self.observation:
            return False
        if self.observation.startswith("(LLM 호출 실패"):
            return False
        return True


# ────────────────────────────────────────────────────────────────────
# Sparkline 정규화
# ────────────────────────────────────────────────────────────────────


def build_sparkline(closes: list[float], dates: list[str]) -> SparklinePoints:
    """60일 종가 → SVG polyline (0~1 정규화)."""
    if not closes:
        return SparklinePoints([], [], 0.0, 0.0, [])
    mn = min(closes)
    mx = max(closes)
    rng = mx - mn if mx > mn else 1.0
    n = len(closes)
    points: list[tuple[float, float]] = []
    for i, c in enumerate(closes):
        x = i / (n - 1) if n > 1 else 0.0
        y = 1.0 - (c - mn) / rng  # 위에서 아래로 (SVG 좌표계)
        points.append((x, y))
    return SparklinePoints(
        raw_closes=list(closes),
        dates=list(dates),
        min_value=mn,
        max_value=mx,
        normalized_points=points,
    )


def _fetch_60d_sparkline(ticker_krx: str) -> SparklinePoints | None:
    """KRX OHLCV 60일 종가 → SparklinePoints."""
    try:
        from pykrx import stock
    except ImportError:
        return None
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=120)).strftime("%Y%m%d")  # 영업일 60+ 확보
    try:
        df = stock.get_market_ohlcv_by_date(start, end, ticker_krx)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    closes = df["종가"].dropna().tail(60).tolist()
    dates = [d.strftime("%Y-%m-%d") for d in df.index[-60:]]
    if not closes:
        return None
    return build_sparkline([float(c) for c in closes], dates)


def _fetch_volume_zscore(ticker_krx: str) -> tuple[float | None, float | None]:
    """오늘 거래량의 60일 z-score + 60일 평균 거래량."""
    try:
        from pykrx import stock
    except ImportError:
        return None, None
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=120)).strftime("%Y%m%d")
    try:
        df = stock.get_market_ohlcv_by_date(start, end, ticker_krx)
    except Exception:
        return None, None
    if df is None or df.empty or len(df) < 10:
        return None, None
    volumes = df["거래량"].dropna()
    if len(volumes) < 10:
        return None, None
    today_vol = float(volumes.iloc[-1])
    avg = float(volumes.tail(60).mean())
    std = float(volumes.tail(60).std())
    z = (today_vol - avg) / std if std > 0 else None
    return z, avg


# ────────────────────────────────────────────────────────────────────
# 종목 카드 데이터 빌드
# ────────────────────────────────────────────────────────────────────


def build_ticker_card(
    ticker_krx: str,
    company_name: str,
    sector: str | None,
    hits: list[TriggerHit],
) -> TickerCardData | None:
    """트리거 통과 종목의 카드 데이터 빌드."""
    spark = _fetch_60d_sparkline(ticker_krx)
    if spark is None or not spark.raw_closes:
        return None
    today_close = spark.raw_closes[-1]
    yesterday_close = (
        spark.raw_closes[-2] if len(spark.raw_closes) >= 2 else today_close
    )
    pct_change = (
        (today_close / yesterday_close - 1) * 100 if yesterday_close else 0.0
    )
    today_date = spark.dates[-1] if spark.dates else datetime.now().strftime("%Y-%m-%d")

    z, avg_vol = _fetch_volume_zscore(ticker_krx)

    return TickerCardData(
        ticker=ticker_krx,
        company_name=company_name,
        today_close=today_close,
        today_date=today_date,
        pct_change=pct_change,
        sparkline_60d=spark,
        sector=sector,
        trigger_hits=hits,
        foreign_3d_krw=None,  # placeholder
        volume_z_score=z,
        avg_volume_60d=avg_vol,
    )


# ────────────────────────────────────────────────────────────────────
# 매크로 데이터 빌드
# ────────────────────────────────────────────────────────────────────


def build_macro_indicators() -> list[MacroIndicator]:
    """매크로 스냅샷 + 60일 스파크라인 (yfinance 기존 캐시 활용)."""
    try:
        from pipeline.macro_data import load_macro_snapshot
        from pipeline import config
    except ImportError:
        return []
    cache = config.REPO_ROOT / "pipeline" / "cache" / "macro_snapshot.json"
    snaps = load_macro_snapshot(cache)
    out: list[MacroIndicator] = []
    for s in snaps:
        # 60일 스파크라인 데이터: snap.sparkline (이미 60-point list)
        spark = (
            build_sparkline(
                s.sparkline,
                [f"{i}" for i in range(len(s.sparkline))],
            )
            if s.sparkline
            else None
        )
        # 60일 등락률
        change_60d = None
        if s.sparkline and len(s.sparkline) >= 2 and s.sparkline[0] > 0:
            change_60d = (s.sparkline[-1] / s.sparkline[0] - 1) * 100
        out.append(
            MacroIndicator(
                label=s.label,
                latest=s.latest,
                latest_str=s.latest_str,
                change_pct_1d=s.change_pct_1d,
                change_pct_60d=change_60d,
                sparkline=spark,
            )
        )
    return out


# ────────────────────────────────────────────────────────────────────
# LLM 프롬프트 (관찰 + 종목 카드 멘트 한 번에)
# ────────────────────────────────────────────────────────────────────


def _build_llm_prompts(
    fetch_date: str,
    macro: list[MacroIndicator],
    ticker_cards: list[TickerCardData],
    triggers_summary: str,
) -> tuple[str, str]:
    """학술/연구 톤 일간 메모 LLM 프롬프트."""
    try:
        from pipeline.frame_loader import load_frame
    except ImportError:
        load_frame = None

    persona_md = ""
    spec_md = ""
    if load_frame:
        frame = load_frame()
        persona_md = frame.persona_md
    spec_path = Path("/mnt/20t/report/_daily_note_spec.md")
    if spec_path.exists():
        spec_md = spec_path.read_text(encoding="utf-8")

    sys_prompt = (
        f"{persona_md}\n\n---\n\n{spec_md}\n\n---\n\n"
        f"# 너의 작업\n\n"
        f"너는 K_E_R 일간 메모(외부 노출 트랙)의 본문을 작성한다. "
        f"**학술/연구 톤**으로 *관찰 단락(3~4줄)* 및 *종목 카드별 멘트(2~3줄)*만 작성.\n"
        f"매크로 표·SVG 스파크라인·트리거 데이터는 코드가 자동 채우므로 너는 *해석·서사*만 담당.\n\n"
        f"## 톤 절대 규칙\n"
        f"- 페르소나 §2 비관 편향, §8 매수·매도·% 예측 금지, §3 출처 엄격주의.\n"
        f"- spec §1.2 학술 어휘만 사용: '관찰된다', '해석된다', '가설', '검증 포인트', '단서', '재배분', '디커플링', '발현', '동조성'.\n"
        f"- 1인칭·감정·확신 회피. 결론보다 '관찰 → 해석 → 다음 검증' 구조.\n"
        f"- 페르소나 ★★★ 신호(영업CF 괴리, 외인 디커플링, 미국 시장 검증, 3년 기술 트랙)에 명시적 매핑.\n"
        f"- 관찰·종목 멘트에 *(추론)* 마커는 학술적 해석 자체에 적용 (예: '단기 차익실현으로 해석된다 *(추론 — 외인 3일 누적 매도 + 잠정실적 직후 시점)*').\n"
        f"- 결론적 표현은 '~로 해석된다·관찰된다·시그널·단서·발현' 류만 허용. '오를 것이다·살 만하다·매수 신호' 금지.\n\n"
        f"## 출력 형식 (반드시 정확히 이 JSON)\n"
        f'```json\n{{\n'
        f'  "headline": "★★★ 헤드라인 1줄 (트리거 핵심)",\n'
        f'  "observation": "관찰 단락 — 3~4줄. 매크로·트리거·★★★ 신호 매핑.",\n'
        f'  "ticker_comments": [\n'
        f'    {{"ticker": "000660", "comment": "2~3줄 학술 해석"}},\n'
        f'    ...\n'
        f'  ],\n'
        f'  "sector_tone": {{"반도체": "↑", "2차전지": "↓", ...}}\n'
        f'}}\n```\n\n'
        f"sector_tone은 워치리스트 13섹터 중 일간 동향이 *유의미한* 섹터만 포함 (3~6개). "
        f"'↑·↓·→' 중 하나."
    )

    user_payload = {
        "fetch_date": fetch_date,
        "macro": [
            {
                "label": m.label,
                "latest": m.latest,
                "change_pct_1d": m.change_pct_1d,
                "change_pct_60d": m.change_pct_60d,
            }
            for m in macro
        ],
        "ticker_cards": [
            {
                "ticker": c.ticker,
                "company": c.company_name,
                "sector": c.sector,
                "today_close": c.today_close,
                "pct_change": c.pct_change,
                "volume_z_score": c.volume_z_score,
                "trigger_hits": [
                    {"type": h.trigger_type, "severity": h.severity, "detail": h.detail}
                    for h in c.trigger_hits
                ],
            }
            for c in ticker_cards
        ],
        "triggers_summary": triggers_summary,
    }
    user_prompt = (
        f"# 분석 대상\n\n"
        f"```json\n{json.dumps(user_payload, ensure_ascii=False, indent=2)}\n```\n\n"
        f"위 데이터로 학술/연구 톤 일간 메모의 *관찰 단락 + 종목 카드 멘트 + 섹터 톤*을 작성해라. "
        f"위에 명시한 JSON 형식으로만 출력 — JSON 이외 텍스트 금지."
    )
    return sys_prompt, user_prompt


def _summarize_triggers(report: TriggerReport) -> str:
    """트리거 헤드라인용 요약."""
    if not report.hits:
        return "(트리거 없음)"
    by_type: dict[str, int] = {}
    for h in report.hits:
        by_type[h.trigger_type] = by_type.get(h.trigger_type, 0) + 1
    parts = []
    if by_type.get("price_move"):
        parts.append(f"가격 변동 {by_type['price_move']}건")
    if by_type.get("dart_disclosure"):
        parts.append(f"DART 공시 {by_type['dart_disclosure']}건")
    if by_type.get("foreign_flow"):
        parts.append(f"외인 수급 {by_type['foreign_flow']}건")
    if by_type.get("decoupling"):
        parts.append(f"디커플링 {by_type['decoupling']}건")
    return " + ".join(parts)


# ────────────────────────────────────────────────────────────────────
# 메인 빌드 함수
# ────────────────────────────────────────────────────────────────────


def build_daily_note(
    trigger_report: TriggerReport,
    watchlist_entries: list,
    top_n: int = 3,
    llm_call: Any = None,  # 의존성 주입 (테스트에서 mock)
) -> DailyNote | None:
    """트리거 통과 시 일간 메모 1면 생성. 트리거 없으면 None."""
    if not trigger_report.should_publish():
        return None

    # 1) 종목 카드 데이터 (top_n)
    top_tickers = trigger_report.top_n_tickers(top_n)
    entry_by_ticker = {e.ticker: e for e in watchlist_entries}
    cards: list[TickerCardData] = []
    for t in top_tickers:
        entry = entry_by_ticker.get(t)
        if entry is None:
            continue
        sector = getattr(entry, "sector", None) or getattr(entry, "category", None)
        hits = trigger_report.hits_for_ticker(t)
        card = build_ticker_card(t, entry.name, sector, hits)
        if card:
            cards.append(card)

    # 2) 매크로
    macro = build_macro_indicators()

    # 3) LLM 호출 (학술 톤 관찰 + 종목 멘트 + 섹터 톤)
    triggers_summary = _summarize_triggers(trigger_report)
    sys_p, user_p = _build_llm_prompts(
        trigger_report.fetch_date, macro, cards, triggers_summary
    )

    headline = f"★ {triggers_summary}"
    observation = ""
    sector_tone: dict[str, str] = {}
    raw_text = ""
    if llm_call is None:
        try:
            from pipeline.llm_client import generate_section
            llm_call = generate_section
        except ImportError:
            llm_call = None

    if llm_call is not None:
        try:
            raw_text = llm_call(sys_p, user_p, max_tokens=2048)
            parsed = _parse_llm_json(raw_text)
            if parsed:
                headline = parsed.get("headline") or headline
                observation = parsed.get("observation", "")
                sector_tone = parsed.get("sector_tone", {})
                # 종목 카드 멘트 attach (frozen dataclass 재생성)
                comments_by_ticker = {
                    cmt.get("ticker"): cmt.get("comment", "")
                    for cmt in parsed.get("ticker_comments", [])
                }
                cards = [
                    TickerCardData(
                        ticker=c.ticker,
                        company_name=c.company_name,
                        today_close=c.today_close,
                        today_date=c.today_date,
                        pct_change=c.pct_change,
                        sparkline_60d=c.sparkline_60d,
                        sector=c.sector,
                        trigger_hits=c.trigger_hits,
                        foreign_3d_krw=c.foreign_3d_krw,
                        volume_z_score=c.volume_z_score,
                        avg_volume_60d=c.avg_volume_60d,
                        llm_comment=comments_by_ticker.get(c.ticker, ""),
                    )
                    for c in cards
                ]
        except Exception as e:
            observation = f"(LLM 호출 실패 — {e})"

    return DailyNote(
        fetch_date=trigger_report.fetch_date,
        headline=headline,
        macro_indicators=macro,
        observation=observation,
        ticker_cards=cards,
        sector_tone=sector_tone,
        triggers_summary=triggers_summary,
        notes=trigger_report.notes,
        sources=trigger_report.sources,
        raw_llm_text=raw_text,
    )


def _parse_llm_json(text: str) -> dict | None:
    """LLM 출력에서 JSON 블록 추출."""
    import re

    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    else:
        s = text.find("{")
        e = text.rfind("}")
        if s >= 0 and e > s:
            text = text[s : e + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
