"""사업보고서 섹션 추출 테스트 — synthetic HTML로 동작 확인."""
from pathlib import Path

from pipeline import business_report_extractor as bre


def test_strip_html_basic():
    html = "<p>테스트 <b>볼드</b></p>\n\n<div>두 번째 <span>줄</span></div>"
    out = bre._strip_html(html)
    assert "테스트" in out
    assert "<" not in out
    assert "볼드" in out


def test_slice_around_pattern_finds_window():
    text = "I. 회사 개요\n  본문 본문\n\nII. 사업의 내용\n  4. 매출 및 수주상황\n  국내 50%, 해외 50%\n\nIII. 재무\n  무관"
    sliced = bre._slice_around_pattern(text, "매출 및 수주상황")
    assert sliced is not None
    assert "국내 50%" in sliced
    assert "III. 재무" not in sliced


def test_slice_returns_none_when_pattern_missing():
    text = "I. 회사 개요\n  무관 본문"
    assert bre._slice_around_pattern(text, "매출 및 수주상황") is None


def test_extract_from_html_finds_section(tmp_path: Path):
    html = (
        "<html><body>"
        "<h2>I. 회사의 개요</h2><p>회사명 SK하이닉스</p>"
        "<h2>II. 사업의 내용</h2>"
        "<h3>4. 매출 및 수주상황</h3>"
        "<table><tr><td>지역별 매출</td></tr><tr><td>미국 35%, 중국 25%, 한국 10%</td></tr></table>"
        "<h2>III. 재무</h2><p>...</p>"
        "</body></html>"
    )
    p = tmp_path / "report.html"
    p.write_text(html, encoding="utf-8")
    secs = bre.extract_from_html(p)
    by_key = {s.section_key: s for s in secs}
    assert "II.4_매출및수주상황" in by_key
    matched = by_key["II.4_매출및수주상황"]
    assert "미국 35%" in matched.text
    assert matched.char_count > 0


def test_extract_from_filing_dir_aggregates(tmp_path: Path):
    f1 = tmp_path / "doc1.html"
    f1.write_text(
        "<html><body><h2>II.4 매출 및 수주상황</h2><p>지역별 매출 표</p></body></html>",
        encoding="utf-8",
    )
    f2 = tmp_path / "doc2.html"
    f2.write_text(
        "<html><body><h2>I. 회사의 개요</h2><p>4. 신용평가에 관한 사항</p>"
        "<p>S&amp;P BBB+, Moody's Baa1, KIS AA+</p></body></html>",
        encoding="utf-8",
    )
    f_skip = tmp_path / "image.png"
    f_skip.write_text("not parseable", encoding="utf-8")

    extraction = bre.extract_from_filing_dir(tmp_path)
    assert "II.4_매출및수주상황" in extraction.sections
    assert "I.4_신용평가" in extraction.sections
    assert all(
        s.source_file != "image.png"
        for hits in extraction.sections.values()
        for s in hits
    )


def test_to_prompt_dict_truncates_long_sections(tmp_path: Path):
    long_text = "지역별 매출 표 " + "x" * 20000
    html = f"<html><body><h2>II.4 매출 및 수주상황</h2><p>{long_text}</p></body></html>"
    p = tmp_path / "report.html"
    p.write_text(html, encoding="utf-8")
    extraction = bre.extract_from_filing_dir(tmp_path)
    pd = extraction.to_prompt_dict(max_chars_per_section=500)
    assert len(pd["II.4_매출및수주상황"]) <= 600  # 500 + 잘림 마커
    assert "잘림" in pd["II.4_매출및수주상황"] or len(pd["II.4_매출및수주상황"]) <= 510
    assert "확인되지 않음" in pd["_usage_rule"]
