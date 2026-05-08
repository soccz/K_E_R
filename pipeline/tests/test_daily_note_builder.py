"""daily_note_builder 단위 테스트 — KRX·LLM 호출은 mock."""
import json
from dataclasses import dataclass
from pathlib import Path

from pipeline import daily_note_builder as dnb
from pipeline.daily_trigger import TriggerHit, TriggerReport


# ───── Sparkline ─────


def test_build_sparkline_normalizes_to_unit_range():
    closes = [100, 110, 105, 120, 115]
    dates = [f"2026-05-0{i}" for i in range(1, 6)]
    s = dnb.build_sparkline(closes, dates)
    assert s.min_value == 100
    assert s.max_value == 120
    # min 종가 → y=1.0 (가장 아래), max 종가 → y=0.0 (가장 위, SVG 좌표계)
    ys = [y for _, y in s.normalized_points]
    assert min(ys) == 0.0
    assert max(ys) == 1.0


def test_build_sparkline_handles_empty():
    s = dnb.build_sparkline([], [])
    assert s.normalized_points == []
    assert s.to_svg_polyline_str() == ""


def test_sparkline_svg_polyline_str_format():
    closes = [100, 200]
    s = dnb.build_sparkline(closes, ["d1", "d2"])
    out = s.to_svg_polyline_str(width=100, height=50)
    # "0.0,50.0 100.0,0.0" 형태 (첫 점 아래·둘째 점 위)
    parts = out.split()
    assert len(parts) == 2
    assert parts[0] == "0.0,50.0"
    assert parts[1] == "100.0,0.0"


# ───── TickerCardData / DailyNote 마크다운 ─────


def _make_card(ticker="000660", pct=-7.0, comment=""):
    spark = dnb.build_sparkline(
        [100000 + i * 100 for i in range(60)],
        [f"2026-{i:02d}" for i in range(60)],
    )
    return dnb.TickerCardData(
        ticker=ticker,
        company_name=f"종목{ticker}",
        today_close=105900.0,
        today_date="2026-05-09",
        pct_change=pct,
        sparkline_60d=spark,
        sector="반도체",
        trigger_hits=[
            TriggerHit(ticker, f"종목{ticker}", "price_move", 1.4, {
                "pct_change": pct, "today_close": 105900,
                "today_date": "2026-05-09", "threshold_pct": 5.0,
            })
        ],
        foreign_3d_krw=None,
        volume_z_score=2.3,
        avg_volume_60d=1_500_000,
        llm_comment=comment,
    )


def test_daily_note_to_markdown_basic_structure():
    note = dnb.DailyNote(
        fetch_date="2026-05-09",
        headline="★★★ 가격 변동 + DART 공시",
        macro_indicators=[
            dnb.MacroIndicator(
                label="KOSPI", latest=2891.45, latest_str="2,891.45",
                change_pct_1d=0.8, change_pct_60d=12.3,
                sparkline=dnb.build_sparkline([2700, 2750, 2800, 2891],
                                              ["d1", "d2", "d3", "d4"]),
            ),
        ],
        observation="외인 자금 재배분이 관찰된다 *(추론 — 워치리스트 반도체 섹터 내부)*. ★★★ 디커플링은 미발현.",
        ticker_cards=[_make_card(ticker="000660", pct=-7.0,
                                  comment="1Q26 잠정실적 직후 차익실현으로 *해석된다*. 다음 검증 포인트: 5월 외인 흐름.")],
        sector_tone={"반도체": "↑", "2차전지": "↓"},
        triggers_summary="가격 변동 1건 + DART 공시 1건",
        notes=["외인 placeholder"],
    )
    md = note.to_markdown()
    assert "# 2026-05-09 일간 메모" in md
    assert "★★★ 가격 변동" in md
    assert "## 매크로" in md
    assert "KOSPI" in md
    assert "polyline" in md  # SVG 들어감
    assert "## 관찰" in md
    assert "재배분이 관찰된다" in md
    assert "## 종목 카드" in md
    assert "종목000660" in md
    assert "▼ -7.00%" in md
    assert "차익실현으로 *해석된다*" in md
    assert "## 섹터 관찰" in md
    assert "반도체 ↑" in md
    assert "공개 관찰 기록" in md  # 푸터


def test_daily_note_save(tmp_path):
    note = dnb.DailyNote(
        fetch_date="2026-05-09",
        headline="test",
        macro_indicators=[],
        observation="obs",
        ticker_cards=[],
        sector_tone={},
        triggers_summary="test",
    )
    target = tmp_path / "daily_notes" / "2026-05-09.md"
    note.save(target)
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert "2026-05-09" in text


# ───── _parse_llm_json ─────


def test_parse_llm_json_extracts_from_code_fence():
    raw = """앞부분 텍스트
```json
{
  "headline": "test",
  "observation": "obs"
}
```
뒷부분"""
    parsed = dnb._parse_llm_json(raw)
    assert parsed == {"headline": "test", "observation": "obs"}


def test_parse_llm_json_falls_back_to_braces():
    raw = '잡음 {"headline": "x"} 잡음'
    parsed = dnb._parse_llm_json(raw)
    assert parsed == {"headline": "x"}


def test_parse_llm_json_returns_none_on_invalid():
    assert dnb._parse_llm_json("no json here") is None
    assert dnb._parse_llm_json("{ invalid json") is None


# ───── _summarize_triggers ─────


def test_summarize_triggers_combines_types():
    report = TriggerReport(
        fetch_date="2026-05-09",
        hits=[
            TriggerHit("000660", "SK", "price_move", 1.4, {}),
            TriggerHit("005930", "삼성", "dart_disclosure", 1.5, {}),
            TriggerHit("105560", "KB", "dart_disclosure", 1.3, {}),
        ],
    )
    s = dnb._summarize_triggers(report)
    assert "가격 변동 1건" in s
    assert "DART 공시 2건" in s


def test_summarize_triggers_empty():
    report = TriggerReport(fetch_date="2026-05-09")
    assert dnb._summarize_triggers(report) == "(트리거 없음)"


# ───── build_daily_note (LLM mock) ─────


@dataclass
class _MockEntry:
    ticker: str
    name: str
    sector: str | None = None
    corp_code: str | None = None


def test_build_daily_note_with_no_triggers_returns_none():
    report = TriggerReport(fetch_date="2026-05-09")  # no hits
    note = dnb.build_daily_note(report, [], llm_call=lambda *a, **kw: "")
    assert note is None


def test_build_daily_note_with_mocked_llm(monkeypatch):
    """LLM mock + KRX mock으로 전체 흐름 검증."""
    # mock sparkline fetch
    def _mock_spark(ticker):
        return dnb.build_sparkline(
            [100000 + i * 100 for i in range(60)],
            [f"2026-{i:02d}-01" for i in range(60)],
        )

    def _mock_zscore(ticker):
        return 2.3, 1_500_000

    def _mock_macro():
        return [
            dnb.MacroIndicator(
                label="KOSPI", latest=2891.45, latest_str="2,891.45",
                change_pct_1d=0.8, change_pct_60d=12.0, sparkline=None,
            ),
        ]

    monkeypatch.setattr(dnb, "_fetch_60d_sparkline", _mock_spark)
    monkeypatch.setattr(dnb, "_fetch_volume_zscore", _mock_zscore)
    monkeypatch.setattr(dnb, "build_macro_indicators", _mock_macro)

    # mock LLM
    mock_response = json.dumps({
        "headline": "★★★ 외인 SK→삼성 자금 재배분 관찰",
        "observation": "워치리스트 반도체 섹터 내부에서 자금 재배분이 관찰된다. 단일 종목 -7% 하락은 1Q26 잠정실적 직후 차익실현으로 해석된다 *(추론 — 외인 데이터 없이 거래량 z-score 2.3 기반)*. ★★★ 외인-국내 디커플링의 *완전한 발현*은 외인 데이터 통합(KRX 계정) 후 검증 가능하다.",
        "ticker_comments": [
            {"ticker": "000660",
             "comment": "1Q26 잠정실적 직후의 차익실현 시그널로 해석된다. 시총/FCF 47배는 사이클 정점 가격 — 사이클 둔화 초기 단서인지 단기 조정인지가 다음 주 외인 흐름에서 검증될 것이다."},
        ],
        "sector_tone": {"반도체": "↑", "2차전지": "↓"},
    })

    def _mock_llm(sys_p, user_p, max_tokens=2048):
        return f"```json\n{mock_response}\n```"

    # trigger report
    report = TriggerReport(
        fetch_date="2026-05-09",
        hits=[
            TriggerHit("000660", "SK하이닉스", "price_move", 1.4,
                       {"pct_change": -7.0, "today_close": 105900,
                        "today_date": "2026-05-09", "threshold_pct": 5.0}),
        ],
    )
    watchlist = [_MockEntry("000660", "SK하이닉스", "반도체", "00164779")]

    note = dnb.build_daily_note(report, watchlist, llm_call=_mock_llm)
    assert note is not None
    assert note.fetch_date == "2026-05-09"
    assert "외인" in note.headline
    assert "재배분이 관찰된다" in note.observation
    assert note.sector_tone == {"반도체": "↑", "2차전지": "↓"}
    assert len(note.ticker_cards) == 1
    assert note.ticker_cards[0].ticker == "000660"
    assert "차익실현 시그널로 해석된다" in note.ticker_cards[0].llm_comment

    # 마크다운 생성 → SVG 들어감
    md = note.to_markdown()
    assert "polyline" in md
    assert "가설·검증 중심" in md


def test_build_daily_note_handles_llm_failure(monkeypatch):
    """LLM 호출 실패해도 카드·매크로는 살아남아 마크다운 생성. is_valid=False."""
    monkeypatch.setattr(dnb, "_fetch_60d_sparkline",
                        lambda t: dnb.build_sparkline([100, 110], ["a", "b"]))
    monkeypatch.setattr(dnb, "_fetch_volume_zscore", lambda t: (1.5, 1000))
    monkeypatch.setattr(dnb, "build_macro_indicators", lambda: [])

    def _failing_llm(sys_p, user_p, max_tokens=2048):
        raise RuntimeError("network down")

    report = TriggerReport(
        fetch_date="2026-05-09",
        hits=[TriggerHit("000660", "SK", "price_move", 1.5, {"pct_change": 7.5})],
    )
    note = dnb.build_daily_note(
        report, [_MockEntry("000660", "SK", "반도체")], llm_call=_failing_llm
    )
    assert note is not None
    assert "LLM 호출 실패" in note.observation
    assert len(note.ticker_cards) == 1
    # 가드 — push 차단 신호
    assert note.is_valid is False


def test_daily_note_is_valid_when_observation_present():
    note = dnb.DailyNote(
        fetch_date="2026-05-09",
        headline="t", macro_indicators=[],
        observation="외인 자금 재배분이 관찰된다.",
        ticker_cards=[], sector_tone={}, triggers_summary="t",
    )
    assert note.is_valid


def test_daily_note_save_writes_raw_text(tmp_path):
    note = dnb.DailyNote(
        fetch_date="2026-05-09",
        headline="t", macro_indicators=[],
        observation="o", ticker_cards=[], sector_tone={}, triggers_summary="t",
        raw_llm_text='{"headline": "t", "observation": "o"}',
    )
    target = tmp_path / "daily_notes" / "2026-05-09.md"
    note.save(target)
    raw_path = tmp_path / "daily_notes" / "_raw" / "2026-05-09.txt"
    assert raw_path.exists()
    assert raw_path.read_text(encoding="utf-8") == note.raw_llm_text
