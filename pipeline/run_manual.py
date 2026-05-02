"""수동 데이터로 보고서 섹션 생성 (DART API 없이).

전체 파이프라인의 end-to-end 시범 — frame loader, prompt builder, claude CLI,
validator, snapshot 모두 함께 작동하는지 확인.

Usage:
  # 한 섹션만
  python -m pipeline.run_manual \\
    --company 삼성전자 \\
    --period 2025-annual \\
    --section 01_사업구조진단

  # 8개 섹션 전부
  python -m pipeline.run_manual \\
    --company 삼성전자 \\
    --period 2025-annual \\
    --section all
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from pipeline import config, snapshot
from pipeline.frame_loader import load_frame
from pipeline.local_data_loader import load_local_dart_data
from pipeline.prompt_builder import (
    SECTION_SPECS,
    DataTimestamps,
    build_section_system_prompt,
    build_section_user_prompt,
)
from pipeline.report_assembler import assemble_report
from pipeline.section_builder import (
    SectionBuildError,
    generate_section_with_validation,
)
from pipeline.source_pack import SourcePack, build_source_pack


def _default_timestamps(financial_basis: str) -> DataTimestamps:
    today = datetime.now().strftime("%Y-%m-%d")
    return DataTimestamps(
        written_at=today,
        dart_query_at=f"수동 다운로드 ({today})",
        financial_basis=financial_basis,
        market_price="(수동 모드 — 시장 데이터 없음)",
        foreign_holding="(수동 모드 — 외인 데이터 없음)",
        macro_data="(수동 모드 — 매크로 데이터 없음)",
    )


def _run_one_section(
    section_id: str,
    company: str,
    frame,
    dart_data: dict,
    market_data: dict,
    timestamps: DataTimestamps,
    report_dir: Path,
    source_pack: SourcePack | None = None,
) -> bool:
    print(f"\n--- {section_id} ---")
    sys_prompt = build_section_system_prompt(frame, section_id)
    user_prompt = build_section_user_prompt(
        company_name=company,
        timestamps=timestamps,
        dart_data=dart_data,
        market_data=market_data,
    )
    print(f"  system prompt: {len(sys_prompt):,} chars")
    print(f"  user prompt:   {len(user_prompt):,} chars")

    snapshot.save_prompt(report_dir, section_id, sys_prompt, user_prompt)

    try:
        result = generate_section_with_validation(
            frame=frame,
            section_id=section_id,
            company_name=company,
            timestamps=timestamps,
            dart_data=dart_data,
            market_data=market_data,
            source_pack=source_pack,
        )
    except SectionBuildError as e:
        print(f"  FAILED after retries.")
        print(f"  V1 (style/source):\n{e.v1.render()}")
        print(f"  V3 (arithmetic):\n{e.v3.render()}")
        return False

    print(f"  PASSED in {result.attempts} attempt(s)")
    print(f"    V1 (style/source): pass")
    print(f"    V3 (arithmetic):   pass")
    if result.v2_validation is not None:
        v2_warns = len(result.v2_validation.warnings)
        print(f"    V2 (numeric vs XBRL): warn-only, {v2_warns} signal(s)")
    else:
        print(f"    V2 (numeric vs XBRL): skipped (no source_pack)")

    for i, raw in enumerate(result.raw_outputs, 1):
        snapshot.save_section_raw(report_dir, f"{section_id}.attempt-{i}", raw)
    snapshot.save_section_final(report_dir, section_id, result.final_text)
    print(f"  saved: {report_dir / f'{section_id}.md'}")

    if result.v2_validation and result.v2_validation.warnings:
        v2_path = report_dir / f"{section_id}.v2_warnings.md"
        lines = [
            f"# V2 numeric warnings — {section_id}",
            "",
            f"총 {len(result.v2_validation.warnings)}건 — 분석가 검토 권고.",
            "",
        ]
        for w in result.v2_validation.warnings:
            lines.append(f"- **L{w.line}** [{w.category}] {w.message}")
            lines.append(f"  > {w.snippet}")
            lines.append("")
        v2_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"  V2 warnings → {v2_path.name}")

    return True

    for i, raw in enumerate(result.raw_outputs, 1):
        snapshot.save_section_raw(report_dir, f"{section_id}.attempt-{i}", raw)
    snapshot.save_section_final(report_dir, section_id, result.final_text)
    print(f"  saved: {report_dir / f'{section_id}.md'}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", required=True, help="기업명 (예: 삼성전자)")
    parser.add_argument(
        "--period", required=True, help="회계연도-주기 (예: 2025-annual, 2026-Q1)"
    )
    parser.add_argument(
        "--section",
        default="01_사업구조진단",
        help="단일 섹션 또는 'all'",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=400_000,
        help="user prompt에 포함할 DART 텍스트 최대 길이 (기본 400K)",
    )
    parser.add_argument(
        "--financial-basis",
        default=None,
        help="데이터 기준시점 박스의 재무제표 표기 (기본: period에서 유추)",
    )
    parser.add_argument(
        "--assemble",
        action="store_true",
        help="모든 섹션 성공 후 00_종합진단.md 합본 작성 (--section all 시 자동 ON)",
    )
    parser.add_argument(
        "--no-owner-summary",
        action="store_true",
        help="합본의 owner-valuation 한 페이지 LLM 호출 skip (속도용)",
    )
    args = parser.parse_args()
    if args.section == "all":
        args.assemble = True

    print(f"provider: {config.LLM_PROVIDER}")
    print(f"model:    {config.CLAUDE_CODE_MODEL if config.LLM_PROVIDER == 'claude_code' else config.ANTHROPIC_MODEL}")

    frame = load_frame()
    print(f"frame.md:    {len(frame.frame_md):,} chars")
    print(f"persona.md:  {len(frame.persona_md):,} chars")
    print(f"watchlist.md:{len(frame.watchlist_md):,} chars")

    report_dir = snapshot.ensure_report_dir(
        config.COMPANIES_DIR, args.company, args.period
    )
    raw_inputs_dir = report_dir / "raw_inputs" / "dart_filings"
    files_present = [p for p in raw_inputs_dir.iterdir() if p.is_file()]
    if not files_present:
        print(
            f"\nERROR: {raw_inputs_dir} 가 비어있음.\n"
            f"먼저 dart.fss.or.kr 에서 {args.company} {args.period} 보고서를 "
            f"다운받아 위 폴더에 넣어줘."
        )
        return 1

    dart_data = load_local_dart_data(raw_inputs_dir, max_chars=args.max_chars)
    print(f"\nDART 데이터 ({len(dart_data['filings'])} 파일):")
    for f in dart_data["filings"]:
        flag = " [TRUNCATED]" if f["truncated"] else ""
        print(f"  - {f['name']}: {f['text_chars']:,} chars{flag}")

    market_data = {"note": "manual mode — 시장 데이터는 다음 실행에서 추가"}
    fb = args.financial_basis or f"{args.period} 보고서 (수동 다운로드)"
    timestamps = _default_timestamps(fb)

    # Source pack from XBRL (optional — V2 validator 사용)
    xbrl_dir = report_dir / "raw_inputs" / "xbrl"
    source_pack = None
    if xbrl_dir.exists() and any(xbrl_dir.iterdir()):
        print(f"\nXBRL source_pack 빌드: {xbrl_dir}")
        source_pack = build_source_pack(xbrl_dir, args.company, args.period)
        print(f"  facts: {len(source_pack.facts):,}")
        print(f"  Korean labels: {len(source_pack.xbrl.label_map):,}")
    else:
        print(f"\nXBRL 없음 → V2 validator skip")

    sections = (
        list(SECTION_SPECS.keys()) if args.section == "all" else [args.section]
    )
    for s in sections:
        if s not in SECTION_SPECS:
            print(f"unknown section: {s}")
            return 2

    all_passed = True
    for sec in sections:
        ok = _run_one_section(
            section_id=sec,
            company=args.company,
            frame=frame,
            dart_data=dart_data,
            market_data=market_data,
            timestamps=timestamps,
            report_dir=report_dir,
            source_pack=source_pack,
        )
        if not ok:
            all_passed = False
            print(f"\n중단: {sec} 가 검증 통과 못함. 재실행하거나 frame.md 점검.")
            return 3

    print(f"\n{'='*50}")
    print(f"완료: {len(sections)}개 섹션 모두 검증 통과")
    print(f"위치: {report_dir}")

    if args.assemble:
        print(f"\n{'='*50}")
        print(f"합본 작성 중...")
        target = assemble_report(
            report_dir=report_dir,
            company=args.company,
            period=args.period,
            timestamps=timestamps,
            frame=frame,
            write_owner_summary=not args.no_owner_summary,
        )
        print(f"합본 완료: {target}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
