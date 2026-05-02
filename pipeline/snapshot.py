"""raw_inputs 저장 — 보고서 역추적용 입력 스냅샷.

각 보고서 폴더 아래에:
  raw_inputs/dart_filings/        # 공시 원문 (HTML/JSON)
  raw_inputs/xbrl_financials.json # 재무 raw
  raw_inputs/market_data.json     # KRX·외인·거래대금
  raw_inputs/prompts/             # 시스템·유저 프롬프트 그대로
  raw_inputs/system_state.txt     # env, model 정보
  sections_raw/                   # LLM 1차 출력 (validator 전)
  sections_final/                 # validator 통과 후
  _meta.json                      # 모델·실행시각·validator 결과
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def ensure_report_dir(companies_dir: Path, company_name: str, period_label: str) -> Path:
    base = companies_dir / company_name / period_label
    for sub in ["raw_inputs", "raw_inputs/dart_filings", "raw_inputs/prompts", "sections_raw", "sections_final"]:
        (base / sub).mkdir(parents=True, exist_ok=True)
    return base


def save_dart_filing(report_dir: Path, filing_name: str, content: str | bytes) -> Path:
    target = report_dir / "raw_inputs" / "dart_filings" / filing_name
    if isinstance(content, bytes):
        target.write_bytes(content)
    else:
        target.write_text(content, encoding="utf-8")
    return target


def save_xbrl(report_dir: Path, data: dict[str, Any]) -> Path:
    target = report_dir / "raw_inputs" / "xbrl_financials.json"
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def save_market_data(report_dir: Path, data: dict[str, Any]) -> Path:
    target = report_dir / "raw_inputs" / "market_data.json"
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def save_prompt(report_dir: Path, section_id: str, system_prompt: str, user_prompt: str) -> None:
    base = report_dir / "raw_inputs" / "prompts"
    (base / f"{section_id}.system.md").write_text(system_prompt, encoding="utf-8")
    (base / f"{section_id}.user.md").write_text(user_prompt, encoding="utf-8")


def save_section_raw(report_dir: Path, section_id: str, text: str) -> None:
    (report_dir / "sections_raw" / f"{section_id}.md").write_text(text, encoding="utf-8")


def save_section_final(report_dir: Path, section_id: str, text: str) -> None:
    (report_dir / "sections_final" / f"{section_id}.md").write_text(text, encoding="utf-8")
    (report_dir / f"{section_id}.md").write_text(text, encoding="utf-8")


def save_assembled_report(report_dir: Path, text: str) -> Path:
    target = report_dir / "00_종합진단.md"
    target.write_text(text, encoding="utf-8")
    return target


def save_meta(report_dir: Path, meta: dict[str, Any]) -> Path:
    meta = dict(meta)
    meta.setdefault("saved_at", datetime.now(timezone.utc).isoformat())
    target = report_dir / "_meta.json"
    target.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def save_system_state(report_dir: Path, state: dict[str, Any]) -> Path:
    lines = [f"{k}: {v}" for k, v in state.items()]
    target = report_dir / "raw_inputs" / "system_state.txt"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target
