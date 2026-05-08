"""산업노트 generator 테스트 (LLM·KRX·DART는 mock)."""
import json
from dataclasses import dataclass
from pathlib import Path

from pipeline import industry_note_builder as inb


@dataclass
class _MockEntry:
    ticker: str
    name: str
    sector: str | None = None


def test_pick_sector_excludes_singletons(tmp_path):
    """단일 종목 섹터는 페어 비교 불가 → 제외."""
    watchlist = [
        _MockEntry("000660", "SK하이닉스", "반도체"),
        _MockEntry("005930", "삼성전자", "반도체"),
        _MockEntry("003490", "대한항공", "항공"),  # 단일 → 제외
    ]
    pick = inb.pick_sector(watchlist, tmp_path)
    assert pick is not None
    assert pick.sector == "반도체"


def test_pick_sector_returns_none_when_all_single(tmp_path):
    watchlist = [_MockEntry("003490", "대한항공", "항공")]
    assert inb.pick_sector(watchlist, tmp_path) is None


def test_pick_sector_prefers_oldest_uncovered(tmp_path):
    """오래 안 다룬 섹터 우선."""
    # 섹터 A는 W18에 다뤘고, 섹터 B는 한 번도 안 다룸
    (tmp_path / "2026-W18-A.md").write_text("...", encoding="utf-8")
    watchlist = [
        _MockEntry("100", "a1", "A"),
        _MockEntry("101", "a2", "A"),
        _MockEntry("200", "b1", "B"),
        _MockEntry("201", "b2", "B"),
    ]
    pick = inb.pick_sector(watchlist, tmp_path)
    # B가 더 오래 안 다뤘으므로 score ↑
    assert pick.sector == "B"


def test_pick_sector_with_dart_count_boost(tmp_path):
    watchlist = [
        _MockEntry("100", "a1", "A"),
        _MockEntry("101", "a2", "A"),
        _MockEntry("200", "b1", "B"),
        _MockEntry("201", "b2", "B"),
    ]
    # 둘 다 history 없음. B에 DART 공시 가산점
    pick = inb.pick_sector(watchlist, tmp_path, sector_dart_counts={"B": 5, "A": 1})
    assert pick.sector == "B"


def test_iso_week_format():
    iso = inb._current_iso_week()
    assert iso.startswith("20")
    assert "-W" in iso


def test_weeks_between():
    assert inb._weeks_between("2026-W10", "2026-W12") == 2
    assert inb._weeks_between("2025-W52", "2026-W02") in (2, 3)


def test_fetch_sector_ticker_data_handles_missing_cache(tmp_path):
    """캐시 없으면 available=False."""
    out = inb.fetch_sector_ticker_data(["000999"], cache_dir=tmp_path)
    assert out[0]["available"] is False


def test_fetch_sector_ticker_data_reads_cache(tmp_path):
    cache = {
        "company_name": "Test",
        "latest_close_krw": 100000,
        "market_cap_trillion_krw": 50.5,
        "close_60d_pct_change": 12.3,
        "close_1y_pct_change": -5.0,
    }
    (tmp_path / "ticker_market_000660.json").write_text(
        json.dumps(cache, ensure_ascii=False), encoding="utf-8"
    )
    out = inb.fetch_sector_ticker_data(["000660"], cache_dir=tmp_path)
    assert out[0]["available"]
    assert out[0]["market_cap_trillion_krw"] == 50.5
    assert out[0]["change_60d_pct"] == 12.3


def test_industry_note_to_markdown_basic():
    note = inb.IndustryNote(
        iso_week="2026-W19",
        sector="반도체",
        fetch_date="2026-05-09",
        headline="HBM 슈퍼사이클",
        summary_one_line="2026 1Q 반도체 섹터 사이클 정점 신호 관찰",
        sector_intro_30s="반도체는 ...",
        weekly_trigger="이번 주 SK하이닉스 잠정실적 ...",
        ticker_comparison_table=[
            {"종목": "SK하이닉스", "코드": "000660", "시총(조)": "1227.4", "60일": "+12.5%", "1년": "+200%"},
            {"종목": "삼성전자", "코드": "005930", "시총(조)": "1589.4", "60일": "+8.0%", "1년": "+15%"},
        ],
        differentiating_factors=["HBM 양산 시점", "고객 다변화", "공정 격차"],
        cycle_position="정점 근처 — 사이클 상단의 가격 발견 단계",
        analogy="HBM 4세대 양산 첫 분기는 반도체 슈퍼사이클의 *2분기 골*에 해당",
        next_milestones=["삼성 HBM4 양산 시점 (2026 4Q 추정)", "Micron HBM3E 12단 출하"],
    )
    md = note.to_markdown()
    assert "2026-W19" in md
    assert "반도체 산업노트" in md
    assert "HBM 양산 시점" in md
    assert "비유로 이해하기" in md
    assert "섹터 페어 비교 관찰" in md
    assert "| 종목 |" in md
    assert "+12.5%" in md
    assert note.is_valid


def test_industry_note_is_valid_false_on_llm_failure():
    note = inb.IndustryNote(
        iso_week="2026-W19", sector="반도체", fetch_date="2026-05-09",
        headline="x",
        summary_one_line="(LLM 호출 실패 — network)",
        sector_intro_30s="", weekly_trigger="",
        ticker_comparison_table=[],
        differentiating_factors=[],
        cycle_position="", analogy="", next_milestones=[],
    )
    assert note.is_valid is False


def test_build_industry_note_with_mocked_llm(monkeypatch, tmp_path):
    cache_dir = tmp_path
    # 2종목 캐시
    for t, name, mc in [("000660", "SK하이닉스", 1227.4), ("005930", "삼성전자", 1589.4)]:
        (cache_dir / f"ticker_market_{t}.json").write_text(
            json.dumps({
                "company_name": name, "latest_close_krw": 1000000,
                "market_cap_trillion_krw": mc,
                "close_60d_pct_change": 12.0,
                "close_1y_pct_change": 100.0,
            }, ensure_ascii=False),
            encoding="utf-8",
        )
    pick = inb.SectorPickResult(
        sector="반도체", tickers=["000660", "005930"],
        company_names=["SK하이닉스", "삼성전자"],
        last_covered_iso_week=None, weeks_since_last=999,
        recent_dart_count=3, score=999.0 + 3 * 2.0,
    )
    mock_llm_response = json.dumps({
        "headline": "HBM 슈퍼사이클",
        "summary_one_line": "관찰된 신호: HBM4 양산 본격화",
        "sector_intro_30s": "반도체는 ...",
        "weekly_trigger": "이번 주 ...",
        "differentiating_factors": ["A", "B", "C"],
        "cycle_position": "정점 근처",
        "analogy": "비유 1줄",
        "next_milestones": ["m1", "m2"],
    })
    note = inb.build_industry_note(
        pick, cache_dir=cache_dir,
        weekly_dart_summary="잠정실적 2건",
        llm_call=lambda s, u, max_tokens=2400: f"```json\n{mock_llm_response}\n```",
    )
    assert note is not None
    assert note.is_valid
    assert len(note.ticker_comparison_table) == 2
    assert note.differentiating_factors == ["A", "B", "C"]


def test_existing_iso_weeks_by_sector(tmp_path):
    (tmp_path / "2026-W18-반도체.md").write_text("...", encoding="utf-8")
    (tmp_path / "2026-W17-반도체.md").write_text("...", encoding="utf-8")
    (tmp_path / "2026-W18-자동차.md").write_text("...", encoding="utf-8")
    (tmp_path / "junk.md").write_text("...", encoding="utf-8")
    h = inb._existing_iso_weeks_by_sector(tmp_path)
    assert "반도체" in h
    assert len(h["반도체"]) == 2
    assert "자동차" in h
