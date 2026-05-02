"""DART API 자동 모드 — 키 사용해서 모든 데이터 fetch + 8섹션 생성 + 합본.

키만 .env에 있으면 한 줄 명령으로 보고서 1편 완성.

Usage:
  # 환경변수 또는 .env에 DART_API_KEY=... 설정 필수

  # 워치리스트 24종목 corp_code 일괄 업데이트 (1회만)
  python -m pipeline.run_dart map-corps

  # 한 회사 한 보고서 자동 생성 (fetch → 8섹션 → 합본)
  python -m pipeline.run_dart generate \\
    --ticker 005930 --bsns-year 2025 --reprt-code 11011 \\
    --period 2025-annual

  # 이미 다운로드된 데이터 사용 (재실행)
  python -m pipeline.run_dart generate \\
    --ticker 005930 --bsns-year 2025 --reprt-code 11011 \\
    --period 2025-annual --skip-fetch
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from pipeline import config, snapshot
from pipeline.corp_code_mapper import fetch_corp_code_mapping, update_watchlist_md
from pipeline.dart_client import DartClient, REPRT_CODE_LABELS
from pipeline.frame_loader import load_frame
from pipeline.local_data_loader import load_local_dart_data
from pipeline.prompt_builder import SECTION_SPECS, DataTimestamps
from pipeline.report_assembler import assemble_report
from pipeline.section_builder import (
    SectionBuildError,
    generate_section_with_validation,
)
from pipeline.source_pack import SourcePack, build_source_pack
from pipeline.watchlist_parser import find_by_ticker, parse_watchlist


def _cmd_map_corps(args: argparse.Namespace) -> int:
    client = DartClient()
    cache_dir = config.REPO_ROOT / "pipeline" / "cache"
    print(f"corpCode.xml 다운로드 → {cache_dir}")
    mapping = fetch_corp_code_mapping(client, cache_dir)
    print(f"전체 상장사 매핑: {len(mapping):,} 종목")

    updated, missing = update_watchlist_md(config.WATCHLIST_PATH, mapping)
    print(f"_watchlist.md 업데이트: {updated} 종목 corp_code 채워짐")
    if missing:
        print(f"매핑 못 찾은 종목 ({len(missing)}개):")
        for m in missing:
            print(f"  - {m}")
        return 1
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    if not config.DART_API_KEY:
        print("ERROR: DART_API_KEY 환경변수 없음. .env 또는 환경에 설정 필요.")
        return 1

    client = DartClient()

    watchlist_text = config.WATCHLIST_PATH.read_text(encoding="utf-8")
    watchlist = parse_watchlist(watchlist_text)
    entry = find_by_ticker(watchlist, args.ticker)
    if not entry:
        print(f"ERROR: ticker {args.ticker} _watchlist.md에 없음")
        return 1

    if not entry.corp_code:
        print(f"corp_code 없음 → 자동 매핑 시도")
        cache_dir = config.REPO_ROOT / "pipeline" / "cache"
        mapping = fetch_corp_code_mapping(client, cache_dir)
        update_watchlist_md(config.WATCHLIST_PATH, mapping)
        watchlist = parse_watchlist(config.WATCHLIST_PATH.read_text(encoding="utf-8"))
        entry = find_by_ticker(watchlist, args.ticker)
        if not entry or not entry.corp_code:
            print(f"ERROR: 매핑 후에도 corp_code 없음")
            return 1

    company = entry.name
    print(f"company: {company} ({entry.ticker} → corp_code {entry.corp_code})")
    print(f"period: {args.period}, reprt_code: {args.reprt_code} ({REPRT_CODE_LABELS.get(args.reprt_code, '?')})")

    report_dir = snapshot.ensure_report_dir(config.COMPANIES_DIR, company, args.period)
    dart_dir = report_dir / "raw_inputs" / "dart_filings"
    xbrl_dir = report_dir / "raw_inputs" / "xbrl"

    if not args.skip_fetch:
        print(f"\nDART에서 정기보고서 검색 중...")
        filing = client.find_periodic_report(
            corp_code=entry.corp_code,
            bsns_year=args.bsns_year,
            reprt_code=args.reprt_code,
        )
        if not filing:
            print(f"ERROR: {company} {args.bsns_year} {args.reprt_code} 보고서 못 찾음")
            return 1
        print(f"  발견: {filing.report_nm} (rcept_no={filing.rcept_no}, 접수일={filing.rcept_dt})")

        print(f"\n공시 원문 다운로드 → {dart_dir}")
        docs = client.download_filing_document(filing.rcept_no, dart_dir)
        print(f"  {len(docs)} 파일")

        print(f"\nXBRL 패키지 다운로드 → {xbrl_dir}")
        xbrl_files = client.download_xbrl(filing.rcept_no, args.reprt_code, xbrl_dir)
        if xbrl_files is None:
            print("  XBRL 미제공 (잠정실적 등)")
        else:
            print(f"  {len(xbrl_files)} 파일")

    frame = load_frame()
    print(f"\nframe/persona/watchlist 로드 완료")

    if not any(p for p in dart_dir.iterdir() if p.is_file()):
        print(f"ERROR: {dart_dir} 비어있음 (--skip-fetch 사용 시 미리 데이터 필요)")
        return 1

    dart_data = load_local_dart_data(dart_dir, max_chars=args.max_chars)
    print(f"\nDART 데이터: {len(dart_data['filings'])} 파일")
    for f in dart_data["filings"]:
        flag = " [TRUNCATED]" if f["truncated"] else ""
        print(f"  - {f['name']}: {f['text_chars']:,} chars{flag}")

    source_pack: SourcePack | None = None
    if xbrl_dir.exists() and any(xbrl_dir.glob("*.xbrl")):
        print(f"\nXBRL source_pack 빌드")
        source_pack = build_source_pack(xbrl_dir, company, args.period)
        print(f"  facts: {len(source_pack.facts):,}, labels: {len(source_pack.xbrl.label_map):,}")
    else:
        print(f"\nXBRL 없음 → V2 validator skip")

    market_data = {"note": "auto mode (DART only) — 시장 데이터는 별도 보강"}
    today = datetime.now().strftime("%Y-%m-%d")
    timestamps = DataTimestamps(
        written_at=today,
        dart_query_at=f"DART API ({today})",
        financial_basis=f"{args.bsns_year} {REPRT_CODE_LABELS.get(args.reprt_code, '?')}",
        market_price="(별도 시장 데이터 미포함 — 자동 모드 v0.1)",
        foreign_holding="(별도 외인 데이터 미포함)",
        macro_data="(별도 매크로 데이터 미포함)",
    )

    sections = list(SECTION_SPECS.keys()) if args.section == "all" else [args.section]
    if args.section != "all" and args.section not in SECTION_SPECS:
        print(f"unknown section: {args.section}")
        return 1

    failed_any = False
    for sec in sections:
        print(f"\n--- {sec} ---")
        try:
            result = generate_section_with_validation(
                frame=frame,
                section_id=sec,
                company_name=company,
                timestamps=timestamps,
                dart_data=dart_data,
                market_data=market_data,
                source_pack=source_pack,
            )
        except SectionBuildError as e:
            print(f"  FAILED. V1: {e.v1.passed}, V3: {e.v3.passed}")
            print(f"  V3 detail: {e.v3.render()}")
            for i, raw in enumerate(getattr(e, "raw_outputs", []), 1):
                snapshot.save_section_raw(report_dir, f"{sec}.attempt-{i}.failed", raw)
            failed_any = True
            continue

        print(f"  PASSED in {result.attempts} attempt(s)")
        for i, raw in enumerate(result.raw_outputs, 1):
            snapshot.save_section_raw(report_dir, f"{sec}.attempt-{i}", raw)
        snapshot.save_section_final(report_dir, sec, result.final_text)
        if result.v2_validation and result.v2_validation.warnings:
            print(f"  V2 warnings: {len(result.v2_validation.warnings)}")

    if failed_any:
        print(f"\n일부 섹션 실패 — 합본 skip")
        return 2

    print(f"\n=== 합본 작성 ===")
    target = assemble_report(
        report_dir=report_dir,
        company=company,
        period=args.period,
        timestamps=timestamps,
        frame=frame,
        write_owner_summary=not args.skip_owner_summary,
    )
    print(f"saved: {target}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_map = sub.add_parser("map-corps", help="워치리스트 24종목 corp_code 일괄 매핑")

    p_gen = sub.add_parser("generate", help="한 회사 한 보고서 자동 생성")
    p_gen.add_argument("--ticker", required=True, help="KRX 6자리 (예: 005930)")
    p_gen.add_argument("--bsns-year", type=int, required=True)
    p_gen.add_argument(
        "--reprt-code",
        required=True,
        choices=["11011", "11012", "11013", "11014"],
        help="11011=사업, 11012=반기, 11013=1Q, 11014=3Q",
    )
    p_gen.add_argument("--period", required=True, help="폴더명 (예: 2025-annual)")
    p_gen.add_argument("--section", default="all")
    p_gen.add_argument("--max-chars", type=int, default=300_000)
    p_gen.add_argument("--skip-fetch", action="store_true", help="이미 받은 데이터 재사용")
    p_gen.add_argument("--skip-owner-summary", action="store_true", help="합본의 owner-valuation 한 페이지 LLM 호출 skip")

    args = parser.parse_args()
    if args.cmd == "map-corps":
        return _cmd_map_corps(args)
    if args.cmd == "generate":
        return _cmd_generate(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
