"""daily_trigger 단위 테스트 — KRX·DART 호출은 mock."""
from dataclasses import dataclass

from pipeline import daily_trigger as dt


# ───── 데이터 모델 ─────


def test_trigger_hit_score_weights_decoupling_highest():
    """페르소나 ★★★ 디커플링이 가장 무거운 점수."""
    price_hit = dt.TriggerHit(
        ticker="000660", company_name="SK하이닉스",
        trigger_type=dt.TRIGGER_PRICE_MOVE, severity=1.0, detail={},
    )
    decouple_hit = dt.TriggerHit(
        ticker="000660", company_name="SK하이닉스",
        trigger_type=dt.TRIGGER_DECOUPLING, severity=1.0, detail={},
    )
    assert decouple_hit.score() > price_hit.score()
    assert decouple_hit.score() == 50.0  # 50·1.0
    assert price_hit.score() == 20.0


def test_trigger_report_should_publish():
    empty = dt.TriggerReport(fetch_date="2026-05-09")
    assert not empty.should_publish()

    with_hit = dt.TriggerReport(
        fetch_date="2026-05-09",
        hits=[dt.TriggerHit("000660", "SK하이닉스", dt.TRIGGER_PRICE_MOVE, 1.5, {})],
    )
    assert with_hit.should_publish()


def test_top_n_tickers_aggregates_by_ticker():
    """한 종목이 여러 트리거 맞으면 점수 합산."""
    hits = [
        dt.TriggerHit("000660", "SK하이닉스", dt.TRIGGER_PRICE_MOVE, 1.0, {}),  # 20
        dt.TriggerHit("000660", "SK하이닉스", dt.TRIGGER_DART_DISCLOSURE, 1.0, {}),  # 30
        # 합계 50, 1위
        dt.TriggerHit("005930", "삼성전자", dt.TRIGGER_PRICE_MOVE, 2.0, {}),  # 40, 2위
        dt.TriggerHit("373220", "LG에너지솔루션", dt.TRIGGER_PRICE_MOVE, 1.0, {}),  # 20, 3위
    ]
    report = dt.TriggerReport(fetch_date="2026-05-09", hits=hits)
    top3 = report.top_n_tickers(3)
    assert top3 == ["000660", "005930", "373220"]


# ───── 가격 변동 ─────


def test_check_price_movement_below_threshold(monkeypatch):
    """등락률 ±5% 미만 → None."""
    def _mock_ohlcv(ticker, days):
        return {
            "today_close": 100000,
            "yesterday_close": 99000,
            "today_pct_change": 1.01,  # +1% 미달
            "today_volume": 1_000_000,
            "avg_volume_60d": 950_000,
            "today_date": "2026-05-09",
        }
    monkeypatch.setattr(dt, "_fetch_recent_ohlcv", _mock_ohlcv)
    hit = dt.check_price_movement("000660", "SK하이닉스")
    assert hit is None


def test_check_price_movement_above_threshold(monkeypatch):
    """등락률 ±5% 초과 → TriggerHit, severity 정확."""
    def _mock_ohlcv(ticker, days):
        return {
            "today_close": 110000,
            "yesterday_close": 100000,
            "today_pct_change": 10.0,  # +10% — 임계치 5% 대비 2배
            "today_volume": 2_000_000,
            "avg_volume_60d": 1_000_000,
            "today_date": "2026-05-09",
        }
    monkeypatch.setattr(dt, "_fetch_recent_ohlcv", _mock_ohlcv)
    hit = dt.check_price_movement("000660", "SK하이닉스")
    assert hit is not None
    assert hit.trigger_type == dt.TRIGGER_PRICE_MOVE
    assert hit.severity == 2.0  # 10% / 5% threshold
    assert hit.detail["pct_change"] == 10.0


def test_check_price_movement_negative_direction(monkeypatch):
    """하락 -7%도 절대값 기준으로 트리거."""
    def _mock_ohlcv(ticker, days):
        return {
            "today_close": 93000,
            "yesterday_close": 100000,
            "today_pct_change": -7.0,
            "today_volume": 0, "avg_volume_60d": 0, "today_date": "2026-05-09",
        }
    monkeypatch.setattr(dt, "_fetch_recent_ohlcv", _mock_ohlcv)
    hit = dt.check_price_movement("000660", "SK하이닉스")
    assert hit is not None
    assert hit.severity == 1.4  # 7% / 5%


def test_check_price_movement_handles_fetch_failure(monkeypatch):
    """KRX fetch 실패 → None."""
    monkeypatch.setattr(dt, "_fetch_recent_ohlcv", lambda *a, **kw: None)
    hit = dt.check_price_movement("000660", "SK하이닉스")
    assert hit is None


# ───── 외인 수급 ─────


def _make_flow_day(date, pct, foreign_krw, source="krx", close=100000):
    """test fixture — ForeignFlowDay 생성."""
    from pipeline.foreign_flow import ForeignFlowDay
    return ForeignFlowDay(
        date=date, close=close, pct_change=pct, volume=0,
        foreign_net_krw=foreign_krw, source=source,
    )


def test_check_foreign_flow_below_threshold(monkeypatch):
    """3일 누적 외인 ±500억 미만 → 미트리거."""
    from pipeline import foreign_flow
    monkeypatch.setattr(
        foreign_flow, "fetch_foreign_flow",
        lambda t, days, **kw: [
            _make_flow_day("2026-05-08", -1.0, -100e8),
            _make_flow_day("2026-05-07", -0.5, -150e8),
            _make_flow_day("2026-05-06", +0.3, +200e8),
        ],
    )
    hit = dt.check_foreign_flow("000660", "SK하이닉스")
    assert hit is None  # 3일 누적 -50억, 임계 미달


def test_check_foreign_flow_sell_hit(monkeypatch):
    """3일 누적 외인 -2,000억 → 매도 트리거 발현."""
    from pipeline import foreign_flow
    monkeypatch.setattr(
        foreign_flow, "fetch_foreign_flow",
        lambda t, days, **kw: [
            _make_flow_day("2026-05-08", -1.5, -800e8),
            _make_flow_day("2026-05-07", -0.5, -700e8),
            _make_flow_day("2026-05-06", +0.3, -500e8),
        ],
    )
    hit = dt.check_foreign_flow("000660", "SK하이닉스")
    assert hit is not None
    assert hit.trigger_type == dt.TRIGGER_FOREIGN_FLOW
    assert hit.detail["direction"] == "매도"
    assert hit.detail["cumulative_eok"] == -2000.0
    assert hit.severity == 4.0  # 2000억 / 500억


def test_check_foreign_flow_insufficient_data(monkeypatch):
    """N영업일 데이터 부족 → None."""
    from pipeline import foreign_flow
    monkeypatch.setattr(
        foreign_flow, "fetch_foreign_flow",
        lambda t, days, **kw: [_make_flow_day("2026-05-08", -1.5, -800e8)],
    )
    assert dt.check_foreign_flow("000660", "SK하이닉스") is None


# ───── DART 공시 ─────


def test_disclosure_impact_score_quarterly_results():
    assert dt._disclosure_impact_score("연결재무제표기준영업(잠정)실적(공정공시)") == 1.5
    assert dt._disclosure_impact_score("영업(잠정)실적공시(공정공시)") == 1.5


def test_disclosure_impact_score_major_event():
    assert dt._disclosure_impact_score("주요사항보고서(자기주식취득결정)") == 1.3
    # "M&A" 직접 매치는 흔치 않으니 우선 합병으로
    assert dt._disclosure_impact_score("합병종료보고서") == 1.3


def test_disclosure_impact_score_correction():
    assert dt._disclosure_impact_score("[정정]사업보고서") == 1.2


def test_disclosure_impact_score_treasury():
    assert dt._disclosure_impact_score("자기주식소각결정") == 1.1


def test_disclosure_impact_score_no_match():
    assert dt._disclosure_impact_score("기타공시") == 0.0
    assert dt._disclosure_impact_score("") == 0.0


def test_check_dart_disclosure_with_quarterly(monkeypatch):
    """1Q 잠정실적 공시 → severity 1.5."""
    def _mock_filings(corp_code, days_back):
        return [
            {
                "report_nm": "연결재무제표기준영업(잠정)실적(공정공시)",
                "rcept_no": "20260509000001",
                "rcept_dt": "20260509",
            },
            {"report_nm": "기타공시", "rcept_no": "x", "rcept_dt": "20260509"},
        ]
    monkeypatch.setattr(dt, "_fetch_recent_dart_filings", _mock_filings)
    hit = dt.check_dart_disclosure("000660", "SK하이닉스", "00164779")
    assert hit is not None
    assert hit.trigger_type == dt.TRIGGER_DART_DISCLOSURE
    assert hit.severity == 1.5
    assert "(잠정)실적" in hit.detail["report_nm"]


def test_check_dart_disclosure_no_match(monkeypatch):
    """기타공시만 있으면 트리거 X."""
    def _mock_filings(corp_code, days_back):
        return [{"report_nm": "기타공시", "rcept_no": "x", "rcept_dt": "20260509"}]
    monkeypatch.setattr(dt, "_fetch_recent_dart_filings", _mock_filings)
    hit = dt.check_dart_disclosure("000660", "SK하이닉스", "00164779")
    assert hit is None


def test_check_dart_disclosure_handles_empty(monkeypatch):
    monkeypatch.setattr(dt, "_fetch_recent_dart_filings", lambda *a, **kw: [])
    assert dt.check_dart_disclosure("000660", "SK하이닉스", "00164779") is None


# ───── 디커플링 ─────


def test_check_decoupling_no_data(monkeypatch):
    """fetch 결과 빈 리스트 → None."""
    from pipeline import foreign_flow
    monkeypatch.setattr(foreign_flow, "fetch_foreign_flow", lambda t, days, **kw: [])
    assert dt.check_decoupling("000660", "SK하이닉스") is None


def test_check_decoupling_same_direction(monkeypatch):
    """가격↑ 외인↑ 같은 방향 → 디커플링 아님."""
    from pipeline import foreign_flow
    monkeypatch.setattr(
        foreign_flow, "fetch_foreign_flow",
        lambda t, days, **kw: [_make_flow_day("2026-05-08", +5.0, +500e8)],
    )
    assert dt.check_decoupling("000660", "SK하이닉스") is None


def test_check_decoupling_below_thresholds(monkeypatch):
    """가격 +1% (임계 ±2% 미달) → 디커플링 검사 X."""
    from pipeline import foreign_flow
    monkeypatch.setattr(
        foreign_flow, "fetch_foreign_flow",
        lambda t, days, **kw: [_make_flow_day("2026-05-08", +1.0, -500e8)],
    )
    assert dt.check_decoupling("000660", "SK하이닉스") is None


def test_check_decoupling_korean_euphoria_foreign_sell(monkeypatch):
    """가격 +5% / 외인 -800억 → 국내 환호 / 외인 매도 디커플링."""
    from pipeline import foreign_flow
    monkeypatch.setattr(
        foreign_flow, "fetch_foreign_flow",
        lambda t, days, **kw: [_make_flow_day("2026-05-08", +5.0, -800e8)],
    )
    hit = dt.check_decoupling("000660", "SK하이닉스")
    assert hit is not None
    assert hit.trigger_type == dt.TRIGGER_DECOUPLING
    assert hit.detail["label"] == "국내 환호 / 외인 매도"
    assert hit.detail["pct_change"] == 5.0
    assert hit.detail["foreign_eok"] == -800.0


def test_check_decoupling_panic_foreign_buy(monkeypatch):
    """가격 -3% / 외인 +500억 → 국내 패닉 / 외인 매수."""
    from pipeline import foreign_flow
    monkeypatch.setattr(
        foreign_flow, "fetch_foreign_flow",
        lambda t, days, **kw: [_make_flow_day("2026-05-08", -3.0, +500e8)],
    )
    hit = dt.check_decoupling("000660", "SK하이닉스")
    assert hit is not None
    assert hit.detail["label"] == "국내 패닉 / 외인 매수"


# ───── 종합 평가 ─────


@dataclass
class _MockEntry:
    ticker: str
    name: str
    corp_code: str | None = None


def test_evaluate_all_triggers_combines_hits(monkeypatch):
    """워치리스트 3종목 → 가격·DART 합산."""
    watchlist = [
        _MockEntry("000660", "SK하이닉스", "00164779"),
        _MockEntry("005930", "삼성전자", "00126380"),
        _MockEntry("373220", "LG에너지솔루션", "01515323"),
    ]

    def _mock_ohlcv(ticker, days):
        # SK하이닉스만 -7% 가격 변동
        if ticker == "000660":
            return {
                "today_close": 93000, "yesterday_close": 100000,
                "today_pct_change": -7.0,
                "today_volume": 0, "avg_volume_60d": 0,
                "today_date": "2026-05-09",
            }
        return {
            "today_close": 100000, "yesterday_close": 100000,
            "today_pct_change": 0.0,
            "today_volume": 0, "avg_volume_60d": 0,
            "today_date": "2026-05-09",
        }

    def _mock_filings(corp_code, days_back):
        # 삼성전자만 잠정실적 공시
        if corp_code == "00126380":
            return [{
                "report_nm": "연결재무제표기준영업(잠정)실적(공정공시)",
                "rcept_no": "1", "rcept_dt": "20260509",
            }]
        return []

    monkeypatch.setattr(dt, "_fetch_recent_ohlcv", _mock_ohlcv)
    monkeypatch.setattr(dt, "_fetch_recent_dart_filings", _mock_filings)
    # 외인/디커플링 — 임계 미달 데이터로 mock (트리거 미발현)
    from pipeline import foreign_flow
    monkeypatch.setattr(
        foreign_flow, "fetch_foreign_flow",
        lambda t, days, **kw: [_make_flow_day(f"2026-05-0{i}", 0.0, 0) for i in (8, 7, 6)],
    )

    report = dt.evaluate_all_triggers(watchlist, fetch_date="2026-05-09")
    assert report.should_publish()
    assert len(report.hits) == 2
    types = sorted(h.trigger_type for h in report.hits)
    assert types == [dt.TRIGGER_DART_DISCLOSURE, dt.TRIGGER_PRICE_MOVE]
    # 점수 정렬: DART(45 = 30*1.5) > 가격(28 = 20*1.4)
    assert report.hits[0].trigger_type == dt.TRIGGER_DART_DISCLOSURE
    # 4종 트리거 모두 활성 메시지
    assert any("4종 트리거 모두 활성" in n for n in report.notes)


def test_evaluate_no_triggers_means_no_publish(monkeypatch):
    """모든 종목 정상 (가격 변동 없음, 공시 없음, 외인 0) → 발행 X."""
    monkeypatch.setattr(dt, "_fetch_recent_ohlcv", lambda *a, **kw: {
        "today_close": 100000, "yesterday_close": 100000,
        "today_pct_change": 0.5, "today_volume": 0, "avg_volume_60d": 0,
        "today_date": "2026-05-09",
    })
    monkeypatch.setattr(dt, "_fetch_recent_dart_filings", lambda *a, **kw: [])
    from pipeline import foreign_flow
    monkeypatch.setattr(
        foreign_flow, "fetch_foreign_flow",
        lambda t, days, **kw: [_make_flow_day(f"2026-05-0{i}", 0.0, 0) for i in (8, 7, 6)],
    )

    watchlist = [_MockEntry("000660", "SK하이닉스", "00164779")]
    report = dt.evaluate_all_triggers(watchlist)
    assert not report.should_publish()
    assert report.hits == []


def test_render_report_no_hits(monkeypatch):
    report = dt.TriggerReport(
        fetch_date="2026-05-09",
        hits=[],
        notes=["외인 placeholder"],
    )
    out = dt.render_report(report)
    assert "트리거된 종목 없음" in out
    assert "외인 placeholder" in out


def test_render_report_with_hits():
    report = dt.TriggerReport(
        fetch_date="2026-05-09",
        hits=[
            dt.TriggerHit("000660", "SK하이닉스", dt.TRIGGER_PRICE_MOVE, 1.4,
                         {"pct_change": -7.0, "today_close": 93000,
                          "today_date": "2026-05-09", "threshold_pct": 5.0}),
        ],
    )
    out = dt.render_report(report)
    assert "SK하이닉스" in out
    assert "price_move" in out
    assert "종목 카드 후보" in out
