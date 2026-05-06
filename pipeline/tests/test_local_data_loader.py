"""DART 원문 파일 로더 테스트."""
from pipeline.local_data_loader import load_local_dart_data


def test_loads_dart_xml_files(tmp_path):
    xml = tmp_path / "report.xml"
    xml.write_text("<DOCUMENT><TITLE>사업보고서</TITLE></DOCUMENT>", encoding="utf-8")

    data = load_local_dart_data(tmp_path)

    assert data["source"] == "manual_download"
    assert len(data["filings"]) == 1
    assert data["filings"][0]["name"] == "report.xml"
    assert "사업보고서" in data["filings"][0]["text"]
    assert "<TITLE>" not in data["filings"][0]["text"]


def test_applies_total_text_budget_across_files(tmp_path):
    (tmp_path / "a.txt").write_text("a" * 100, encoding="utf-8")
    (tmp_path / "b.txt").write_text("b" * 100, encoding="utf-8")

    data = load_local_dart_data(tmp_path, max_chars=100, max_total_chars=120)

    assert sum(f["loaded_chars"] for f in data["filings"]) == 120
    assert all(f["truncated"] for f in data["filings"])
