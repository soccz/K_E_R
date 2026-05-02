"""security_check 테스트 — 가짜 secret 패턴 detection 확인."""
from pathlib import Path

from pipeline.security_check import scan_file, scan_paths


def test_detects_anthropic_key(tmp_path: Path):
    f = tmp_path / "leak.py"
    f.write_text("ANTHROPIC_KEY = 'sk-ant-aBcDeFgHiJkLmNoPqRsTuVwXyZ12'", encoding="utf-8")
    violations = scan_file(f)
    assert any("Anthropic" in v[0] for v in violations)


def test_detects_aws_access_key(tmp_path: Path):
    f = tmp_path / "config.txt"
    f.write_text("aws_key = AKIAIOSFODNN7EXAMPLE", encoding="utf-8")
    violations = scan_file(f)
    # AWS access key는 EXAMPLE 마커로 화이트리스트됨 → 검출 안 됨이 맞음
    assert not any("AWS access key" in v[0] for v in violations)


def test_detects_aws_without_example_marker(tmp_path: Path):
    f = tmp_path / "config.txt"
    f.write_text("real_key = AKIAIOSFODNN7XYZ1234", encoding="utf-8")
    violations = scan_file(f)
    assert any("AWS access key" in v[0] for v in violations)


def test_detects_github_pat(tmp_path: Path):
    f = tmp_path / "leak.txt"
    f.write_text("token: ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ123456", encoding="utf-8")
    violations = scan_file(f)
    assert any("GitHub Personal Access Token" in v[0] for v in violations)


def test_detects_private_key_header(tmp_path: Path):
    f = tmp_path / "leak.pem"
    f.write_text(
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQ...\n-----END RSA PRIVATE KEY-----",
        encoding="utf-8",
    )
    violations = scan_file(f)
    assert any("private key" in v[0].lower() for v in violations)


def test_placeholder_not_flagged(tmp_path: Path):
    f = tmp_path / ".env.template"
    f.write_text("DART_API_KEY=PUT_YOUR_40_CHAR_DART_KEY_HERE", encoding="utf-8")
    violations = scan_file(f)
    # PUT_YOUR placeholder는 화이트리스트
    assert not violations


def test_scan_paths_recurses(tmp_path: Path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "clean.md").write_text("# all good", encoding="utf-8")
    (tmp_path / "sub" / "leak.txt").write_text("sk-ant-aBcDeFgHiJkLmNoPqRsTuVwXyZ12", encoding="utf-8")

    violations, total = scan_paths([tmp_path])
    assert total == 2
    assert len(violations) == 1
    assert any("leak.txt" in str(p) for p in violations)


def test_clean_file_no_violations(tmp_path: Path):
    f = tmp_path / "code.py"
    f.write_text("def hello():\n    return 'world'\n", encoding="utf-8")
    assert scan_file(f) == []


def test_binary_files_skipped(tmp_path: Path):
    f = tmp_path / "image.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    assert scan_file(f) == []
