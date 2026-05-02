"""커밋 전 secret 스캐너.

Usage:
  python -m pipeline.security_check                    # 모든 staged 파일 검사 (git add 후)
  python -m pipeline.security_check --all              # 워킹디렉토리 전체 검사
  python -m pipeline.security_check path/to/file.md    # 특정 파일 검사

검출 패턴:
  - DART API 키 (40자리 hex)
  - Anthropic API 키 (sk-ant-...)
  - AWS 액세스 키
  - GitHub Personal Access Token (ghp_, gho_, ghu_, ghs_, ghr_)
  - Private 키 헤더 (-----BEGIN ... PRIVATE KEY-----)
  - 일반 secret 패턴 (password=, api_key=, token=)

위반 발견 시 exit code 1 + 위반 위치 출력.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("DART API key (40+ char hex)", re.compile(r"\b[a-f0-9]{40,}\b")),
    ("Anthropic API key", re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("AWS secret access key", re.compile(r"(?i)aws[_-]?secret[_-]?access[_-]?key\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{30,}")),
    ("GitHub Personal Access Token", re.compile(r"\bgh[pousr]_[a-zA-Z0-9]{30,}\b")),
    ("Slack token", re.compile(r"xox[baprs]-[a-zA-Z0-9-]{10,}")),
    ("Generic private key header", re.compile(r"-----BEGIN (RSA |EC |DSA |OPENSSH |ENCRYPTED |)?PRIVATE KEY-----")),
    ("Hardcoded password assignment", re.compile(r"(?i)\bpassword\s*[=:]\s*['\"][^'\"]{6,}['\"]")),
    ("API key assignment", re.compile(r"(?i)\bapi[_-]?key\s*[=:]\s*['\"][^'\"]{20,}['\"]")),
]

# 화이트리스트: 의도적으로 패턴이 들어간 곳 (예: 정규식 자체, 문서, 테스트)
WHITELIST_FILES = {
    "pipeline/security_check.py",                     # 이 파일 자체 (정규식)
    "pipeline/tests/test_security_check.py",          # 스캐너 테스트 (fake 패턴)
    ".env.example",                                    # 템플릿 placeholder
    "SECURITY.md",                                     # 보안 문서의 예시
}


def _is_whitelisted(path: Path) -> bool:
    rel = str(path)
    return any(rel.endswith(w) for w in WHITELIST_FILES)


def scan_file(path: Path) -> list[tuple[str, int, str]]:
    """파일 한 개 스캔. 반환: (위반종류, 라인번호, snippet) 리스트."""
    if _is_whitelisted(path):
        return []
    if not path.exists() or not path.is_file():
        return []
    if path.suffix.lower() in {".pdf", ".zip", ".png", ".jpg", ".jpeg", ".gif", ".so", ".dylib", ".bin"}:
        return []

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return []

    violations: list[tuple[str, int, str]] = []
    lines = content.splitlines()
    for i, line in enumerate(lines, 1):
        for label, pattern in PATTERNS:
            for m in pattern.finditer(line):
                snippet = line.strip()[:120]
                # placeholder 제외 (PUT_YOUR_..._HERE 같은)
                if "PUT_YOUR" in line or "REPLACE_WITH" in line or "EXAMPLE" in line.upper():
                    continue
                violations.append((label, i, snippet))
    return violations


def scan_paths(paths: list[Path]) -> tuple[dict[Path, list], int]:
    """Returns (violations_per_file, total_files_scanned)."""
    out: dict[Path, list] = {}
    total = 0
    for p in paths:
        if p.is_file():
            total += 1
            v = scan_file(p)
            if v:
                out[p] = v
        elif p.is_dir():
            for f in p.rglob("*"):
                if not f.is_file():
                    continue
                s = str(f)
                if ".git/" in s or ".venv/" in s or "__pycache__" in s or ".pytest_cache" in s:
                    continue
                total += 1
                v = scan_file(f)
                if v:
                    out[f] = v
    return out, total


def get_staged_files() -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [Path(line) for line in result.stdout.strip().split("\n") if line]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", help="검사할 파일/디렉토리 (생략 시 git staged)")
    parser.add_argument("--all", action="store_true", help="repo 전체 검사")
    args = parser.parse_args()

    if args.all:
        targets = [Path(".")]
    elif args.paths:
        targets = [Path(p) for p in args.paths]
    else:
        targets = get_staged_files()
        if not targets:
            print("git staged 파일 없음. (--all 또는 path 인자 사용)")
            return 0

    violations, total_scanned = scan_paths(targets)
    if not violations:
        print(f"OK: {total_scanned} 파일 검사, secret 의심 패턴 없음.")
        return 0

    print(f"\n[ALERT] SECRET 의심 패턴 {sum(len(v) for v in violations.values())}건 발견 ({total_scanned} 파일 검사):\n")
    for path, viols in violations.items():
        for label, line_no, snippet in viols:
            print(f"  {path}:{line_no}  [{label}]")
            print(f"    > {snippet}")
            print()

    print("위 패턴이 *진짜* 키라면:")
    print("  1. 즉시 rotate (해당 서비스에서 키 재발급)")
    print("  2. .env 또는 환경변수로 이동 후 코드에서 제거")
    print("  3. git history에서도 제거 (git filter-repo 등)")
    print()
    print("의도적 패턴이라면 pipeline/security_check.py의 WHITELIST_FILES 또는 라인에 'EXAMPLE' 마커 추가.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
