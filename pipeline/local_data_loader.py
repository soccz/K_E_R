"""DART API 없이 수동 다운로드한 PDF/HTML을 sub-agent용 데이터로 변환.

사용 시나리오:
  - DART 인증키 발급 전 수동 시범 단계
  - 너 컴퓨터에 dart_filings/ 폴더에 PDF/HTML 넣어두면 자동으로 텍스트 추출
  - PDF는 pdftotext (poppler-utils) 사용, HTML은 그대로 읽음
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def _pdf_to_text(pdf_path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def load_local_dart_data(dir_path: Path, max_chars: int = 400_000) -> dict:
    if not dir_path.exists():
        raise FileNotFoundError(f"{dir_path} 없음")

    filings: list[dict] = []
    for path in sorted(dir_path.iterdir()):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            text = _pdf_to_text(path)
        elif suffix in {".html", ".htm", ".txt", ".md"}:
            text = _read_text_file(path)
        elif suffix == ".zip":
            print(f"  [skip] {path.name} — zip은 먼저 압축 해제 필요")
            continue
        else:
            print(f"  [skip] {path.name} — 미지원 확장자 ({suffix})")
            continue

        truncated = len(text) > max_chars
        filings.append(
            {
                "name": path.name,
                "text_chars": len(text),
                "text": text[:max_chars] if truncated else text,
                "truncated": truncated,
            }
        )
    return {"filings": filings, "source": "manual_download"}
