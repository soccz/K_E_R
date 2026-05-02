"""frame_loader가 실제 _frame.md / _persona.md / _watchlist.md를 읽어들이는지."""
from pipeline.frame_loader import load_frame


def test_load_frame_reads_all_three():
    spec = load_frame()
    assert "DART 기업 종합 진단 프레임" in spec.frame_md
    assert "사용자 투자 성향" in spec.persona_md
    assert "워치리스트" in spec.watchlist_md


def test_frame_contains_source_rules():
    spec = load_frame()
    assert "출처·추론 규칙" in spec.frame_md
    assert "데이터 기준시점" in spec.frame_md


def test_persona_contains_owner_mindset():
    spec = load_frame()
    assert "통째로 살" in spec.persona_md
    assert "3년" in spec.persona_md
