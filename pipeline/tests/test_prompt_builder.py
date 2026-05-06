"""prompt_builder 동작 확인. LLM 호출은 안 함."""
from pipeline.frame_loader import load_frame
from pipeline.prompt_builder import (
    SECTION_SPECS,
    DataTimestamps,
    build_section_system_prompt,
    build_section_user_prompt,
    build_retry_user_prompt,
)


def test_section_specs_cover_all_sections():
    expected = {
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
    }
    assert set(SECTION_SPECS.keys()) == expected


def test_system_prompt_includes_frame_and_persona():
    frame = load_frame()
    prompt = build_section_system_prompt(frame, "01_사업구조진단")
    assert "DART 기업 종합 진단 프레임" in prompt
    assert "사용자 투자 성향" in prompt
    assert "01_사업구조진단" in prompt
    assert "출처가 없거나 모호하면" in prompt


def test_user_prompt_renders_timestamps_box():
    ts = DataTimestamps(
        written_at="2026-05-02",
        dart_query_at="2026-05-02 21:10 KST",
        financial_basis="2025 사업보고서 + 2026 1Q 잠정실적",
        market_price="KRX 2026-05-02 종가",
        foreign_holding="KRX 2026-05-02 외국인 보유잔고",
        macro_data="ECOS 2026-05-02",
    )
    user = build_section_user_prompt(
        company_name="삼성전자",
        timestamps=ts,
        dart_data={"filings": []},
        market_data={"close": 70000},
    )
    assert "데이터 기준시점" in user
    assert "삼성전자" in user
    assert "2026-05-02 21:10 KST" in user


def test_user_prompt_includes_xbrl_summary_when_given():
    ts = DataTimestamps(
        written_at="2026-05-02",
        dart_query_at="2026-05-02 21:10 KST",
        financial_basis="2025 사업보고서",
        market_price="(미포함)",
        foreign_holding="(미포함)",
        macro_data="(미포함)",
    )
    user = build_section_user_prompt(
        company_name="SK하이닉스",
        timestamps=ts,
        dart_data={"filings": [{"name": "report.xml", "text": "본문"}]},
        market_data={},
        source_pack_summary={
            "core_consolidated_facts": [
                {"label": "수익(매출액)", "value_trillion_krw": 97.1467}
            ]
        },
    )
    assert "XBRL 핵심 재무 데이터" in user
    assert "97.1467" in user


def test_retry_prompt_appends_feedback():
    original = "원본 유저 프롬프트"
    feedback = "vague_source 위반"
    retry = build_retry_user_prompt(original, feedback)
    assert original in retry
    assert "vague_source" in retry
    assert "재작성" in retry


def test_unknown_section_raises():
    frame = load_frame()
    try:
        build_section_system_prompt(frame, "99_invalid")
        assert False, "should have raised"
    except KeyError:
        pass
