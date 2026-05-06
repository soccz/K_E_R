"""DART API 없이 수동 다운로드한 PDF/HTML을 sub-agent용 데이터로 변환.

사용 시나리오:
  - DART 인증키 발급 전 수동 시범 단계
  - 너 컴퓨터에 dart_filings/ 폴더에 PDF/HTML/XML 넣어두면 자동으로 텍스트 추출
  - PDF는 pdftotext (poppler-utils) 사용, HTML은 그대로 읽음
"""
from __future__ import annotations

import subprocess
from html.parser import HTMLParser
from pathlib import Path


class _DartMarkupTextExtractor(HTMLParser):
    """DART XML/HTML 원문에서 사람이 읽을 텍스트만 추출."""

    _BLOCK_TAGS = {"br", "p", "table", "tr", "section", "title"}
    _CELL_TAGS = {"td", "th", "tu"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in self._BLOCK_TAGS:
            self._parts.append("\n")
        elif tag in self._CELL_TAGS:
            self._parts.append("\t")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._BLOCK_TAGS or tag in self._CELL_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        text = " ".join(data.replace("\xa0", " ").split())
        if text:
            self._parts.append(text)
            self._parts.append(" ")

    def text(self) -> str:
        lines = []
        for line in "".join(self._parts).splitlines():
            line = " ".join(line.replace("\t", " | ").split())
            if line:
                lines.append(line)
        return "\n".join(lines)


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


def _read_markup_file(path: Path) -> str:
    raw = _read_text_file(path)
    parser = _DartMarkupTextExtractor()
    parser.feed(raw)
    parser.close()
    text = parser.text()
    return text if text else raw


def _allocate_budgets(
    lengths: list[int],
    *,
    max_chars: int,
    max_total_chars: int | None,
) -> list[int]:
    if max_total_chars is None:
        return [min(n, max_chars) for n in lengths]
    if not lengths:
        return []

    base = max(1, max_total_chars // len(lengths))
    budgets = [min(n, max_chars, base) for n in lengths]
    remaining = max_total_chars - sum(budgets)
    for i, n in enumerate(lengths):
        if remaining <= 0:
            break
        extra_capacity = min(n, max_chars) - budgets[i]
        extra = min(extra_capacity, remaining)
        budgets[i] += extra
        remaining -= extra
    return budgets


def load_local_dart_data(
    dir_path: Path,
    max_chars: int = 400_000,
    max_total_chars: int | None = None,
) -> dict:
    if not dir_path.exists():
        raise FileNotFoundError(f"{dir_path} 없음")

    skipped_files: list[str] = []
    loaded: list[tuple[Path, str]] = []
    for path in sorted(dir_path.iterdir()):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            text = _pdf_to_text(path)
        elif suffix in {".html", ".htm", ".xhtml", ".xml"}:
            text = _read_markup_file(path)
        elif suffix in {".txt", ".md"}:
            text = _read_text_file(path)
        elif suffix == ".zip":
            print(f"  [skip] {path.name} — zip은 먼저 압축 해제 필요")
            skipped_files.append(path.name)
            continue
        else:
            print(f"  [skip] {path.name} — 미지원 확장자 ({suffix})")
            skipped_files.append(path.name)
            continue

        loaded.append((path, text))

    budgets = _allocate_budgets(
        [len(text) for _, text in loaded],
        max_chars=max_chars,
        max_total_chars=max_total_chars,
    )

    filings: list[dict] = []
    for (path, text), budget in zip(loaded, budgets):
        truncated = len(text) > budget
        filings.append(
            {
                "name": path.name,
                "text_chars": len(text),
                "loaded_chars": min(len(text), budget),
                "text": text[:budget] if truncated else text,
                "truncated": truncated,
            }
        )
    return {
        "filings": filings,
        "source": "manual_download",
        "skipped_files": skipped_files,
    }
