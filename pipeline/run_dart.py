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
from pipeline.business_report_extractor import extract_from_filing_dir
from pipeline.corp_code_mapper import fetch_corp_code_mapping, update_watchlist_md
from pipeline.cross_section_consistency import build_authoritative_facts
from pipeline.dart_client import DartClient, REPRT_CODE_LABELS
from pipeline.foreign_holdings import load_foreign_holding_snapshot
from pipeline.frame_loader import load_frame
from pipeline.local_data_loader import load_local_dart_data
from pipeline.macro_data import load_macro_snapshot
from pipeline.prompt_builder import SECTION_SPECS, DataTimestamps
from pipeline.quarterly_disclosure import load_quarterly_disclosures
from pipeline import cross_section_consistency, report_quality
from pipeline.report_assembler import assemble_report
from pipeline.section_builder import (
    SectionBuildError,
    generate_section_with_validation,
)
from pipeline.source_pack import SourcePack, build_source_pack
from pipeline.ticker_market_data import load_ticker_snapshot
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

    annual_rcept_dt: str | None = None
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
        annual_rcept_dt = filing.rcept_dt

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

    dart_data = load_local_dart_data(
        dart_dir,
        max_chars=args.max_chars,
        max_total_chars=args.max_total_chars,
    )
    print(f"\nDART 데이터: {len(dart_data['filings'])} 파일")
    for f in dart_data["filings"]:
        flag = " [TRUNCATED]" if f["truncated"] else ""
        loaded = f.get("loaded_chars", len(f.get("text", "")))
        print(f"  - {f['name']}: {loaded:,}/{f['text_chars']:,} chars{flag}")

    source_pack: SourcePack | None = None
    if xbrl_dir.exists() and any(xbrl_dir.glob("*.xbrl")):
        print(f"\nXBRL source_pack 빌드")
        source_pack = build_source_pack(xbrl_dir, company, args.period)
        print(f"  facts: {len(source_pack.facts):,}, labels: {len(source_pack.xbrl.label_map):,}")
    else:
        print(f"\nXBRL 없음")

    input_guard = report_quality.validate_generation_inputs(
        dart_data,
        source_pack,
        require_xbrl=not args.allow_missing_xbrl,
    )
    if not input_guard.passed:
        print(f"\nERROR: 입력 품질 가드 실패")
        print(input_guard.render())
        return 1
    if input_guard.warnings:
        print(f"\n입력 품질 가드 경고")
        print(input_guard.render())

    cache_dir = config.REPO_ROOT / "pipeline" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    ticker_cache = cache_dir / f"ticker_market_{args.ticker}.json"
    foreign_cache = cache_dir / f"foreign_holdings_{args.ticker}.json"

    market_snapshot = None
    foreign_snapshot = None
    market_snap = None
    try:
        market_snap = load_ticker_snapshot(
            ticker_cache,
            ticker_krx=args.ticker,
            company_name=company,
            corp_code=entry.corp_code,
            bsns_year=args.bsns_year,
            reprt_code=args.reprt_code,
        )
        market_snapshot = market_snap.to_prompt_dict()
        if market_snap.issued_shares_common:
            print(
                f"\n발행주식수(보통주): {market_snap.issued_shares_common:,} | "
                f"자기주식: {market_snap.treasury_shares or '-'}"
            )
        else:
            print(f"\n발행주식수: 확인되지 않음 (DART stockTotqySttus 응답 미흡)")
        if market_snap.market_cap_trillion_krw:
            d60 = (
                f"{market_snap.close_60d_pct_change:+.1f}%"
                if market_snap.close_60d_pct_change is not None
                else "n/a"
            )
            d1y = (
                f"{market_snap.close_1y_pct_change:+.1f}%"
                if market_snap.close_1y_pct_change is not None
                else "n/a"
            )
            print(
                f"종가: {market_snap.latest_close_krw:,.0f}원 ({market_snap.latest_close_date}) | "
                f"시가총액: {market_snap.market_cap_trillion_krw:.2f}조 "
                f"(60d {d60} / 1y {d1y})"
            )
        elif market_snap.latest_close_krw:
            print(f"종가: {market_snap.latest_close_krw:,.0f}원 (시총 계산 불가)")
        else:
            print("종가·시총: 확인되지 않음 (KRX OHLCV fetch 실패)")
    except Exception as e:
        print(f"\n[market] fetch 실패 — owner-valuation에서 '확인되지 않음'으로 처리: {e}")

    foreign_snap = None
    try:
        foreign_snap = load_foreign_holding_snapshot(
            foreign_cache,
            ticker_krx=args.ticker,
            company_name=company,
            corp_code=entry.corp_code,
        )
        foreign_snapshot = foreign_snap.to_prompt_dict()
        print(f"외인 보유 (DART 5%↑): {foreign_snap.foreign_major_holders_count}건")
    except Exception as e:
        print(f"[foreign] fetch 실패: {e}")

    business_extraction = None
    try:
        extraction = extract_from_filing_dir(dart_dir)
        if extraction.sections:
            # 섹션당 max 3000자로 제한 — 10개 섹션 합 ~30KB. claude CLI timeout 회피.
            # 섹션당 max 2000자 (10개 섹션 합 ~20KB). claude CLI 600~1800s timeout 안전 마진.
            business_extraction = extraction.to_prompt_dict(max_chars_per_section=2000)
            print(f"사업보고서 섹션 추출: {list(extraction.sections.keys())}")
    except Exception as e:
        print(f"[business_report] 추출 실패: {e}")

    # --skip-fetch면 캐시 디렉토리에서 첫 8자리(YYYYMMDD) 추출
    if annual_rcept_dt is None:
        for p in sorted(dart_dir.glob("*.xml")):
            stem = p.stem
            if len(stem) >= 8 and stem[:8].isdigit():
                annual_rcept_dt = stem[:8]
                break

    quarterly_snapshot = None
    if annual_rcept_dt:
        quarterly_cache = cache_dir / f"quarterly_disclosure_{args.ticker}.json"
        try:
            qd_snap = load_quarterly_disclosures(
                quarterly_cache,
                company=company,
                corp_code=entry.corp_code,
                annual_rcept_dt=annual_rcept_dt,
            )
            quarterly_snapshot = qd_snap.to_prompt_dict()
            n = len(qd_snap.interim_filings)
            if n:
                latest = qd_snap.interim_filings[0]
                print(
                    f"분기 잠정실적·분기보고서: {n}건, 최신 = "
                    f"{latest.report_nm} ({latest.rcept_dt}, +{latest.days_after_annual}d)"
                )
            else:
                print("분기 잠정실적: 사업보고서 이후 0건 (시점 그대로)")
        except Exception as e:
            print(f"[quarterly_disclosure] fetch 실패: {e}")
    else:
        print("annual_rcept_dt 미확보 — 분기 잠정실적 fetch skip")

    macro_snaps = []
    try:
        macro_cache = cache_dir / "macro_snapshot.json"
        macro_snaps = load_macro_snapshot(macro_cache)
        if macro_snaps:
            print(f"매크로 지표: {len(macro_snaps)}개 ({', '.join(s.label for s in macro_snaps)})")
    except Exception as e:
        print(f"[macro] fetch 실패: {e}")

    market_data: dict = {"note": "auto mode v0.4 — 시장·외인·사업보고서·분기잠정실적·매크로 통합"}
    if market_snapshot:
        market_data["ticker_snapshot"] = market_snapshot
    if foreign_snapshot:
        market_data["foreign_holding"] = foreign_snapshot
    if business_extraction:
        market_data["business_report_sections"] = business_extraction
    if quarterly_snapshot:
        market_data["quarterly_disclosures"] = quarterly_snapshot
    if macro_snaps:
        market_data["macro_indicators"] = {
            "note": "페르소나 §6 매크로 의무 5종 (환율·유가·미국 금리·외인·지정학) 중 시장 시세 부분",
            "indicators": [
                {
                    "label": s.label,
                    "latest": s.latest_str,
                    "change_pct_1d": s.change_pct_1d,
                    "change_pct_1y": s.change_pct_1y,
                    "period": f"{s.period_start} ~ {s.period_end}",
                }
                for s in macro_snaps
            ],
            "usage_rule": (
                "환율(USD/KRW), 유가(WTI), KOSPI 지수는 페르소나 매크로 의무 5종 중 일부. "
                "보고서 본문에서 *학습 지식 추정 금지* — 위 latest·change_pct_1y 수치만 인용. "
                "값이 없으면 '확인되지 않음'."
            ),
        }

    today = datetime.now().strftime("%Y-%m-%d")
    if market_snap and market_snap.latest_close_krw:
        market_price_str = (
            f"KRX {market_snap.latest_close_date} 종가 "
            f"{market_snap.latest_close_krw:,.0f}원 "
            f"(시총 {market_snap.market_cap_trillion_krw:.2f}조)"
            if market_snap.market_cap_trillion_krw
            else f"KRX {market_snap.latest_close_date} 종가 {market_snap.latest_close_krw:,.0f}원"
        )
    elif market_snapshot:
        market_price_str = "(KRX 종가 fetch 실패 — 사업보고서 본문에서 추출 시도)"
    else:
        market_price_str = "(시장 데이터 fetch 실패 — 확인되지 않음)"
    foreign_str = (
        f"DART 5%↑ 보유공시 {foreign_snap.foreign_major_holders_count}건 — KRX 일별잔고 미통합"
        if foreign_snapshot
        else "(외인 데이터 fetch 실패)"
    )
    timestamps = DataTimestamps(
        written_at=today,
        dart_query_at=f"DART API ({today})",
        financial_basis=f"{args.bsns_year} {REPRT_CODE_LABELS.get(args.reprt_code, '?')}",
        market_price=market_price_str,
        foreign_holding=foreign_str,
        macro_data="(별도 매크로 데이터 미포함)",
    )

    # 권위 사실 dict 빌드 (V4 cross-section consistency용) — 시총·매출·영업이익·잠정실적
    auth_facts = []
    if source_pack is not None:
        rev = next(
            (f.value for f in source_pack.facts if f.concept == "ifrs-full:Revenue"
             and f.period_end == f"{args.bsns_year}-12-31"
             and (not f.dimensions or "ConsolidatedMember" in str(f.dimensions))),
            None,
        )
        oi = next(
            (f.value for f in source_pack.facts if f.concept == "dart:OperatingIncomeLoss"
             and f.period_end == f"{args.bsns_year}-12-31"
             and (not f.dimensions or "ConsolidatedMember" in str(f.dimensions))),
            None,
        )
        ocf = next(
            (f.value for f in source_pack.facts if f.concept == "ifrs-full:CashFlowsFromUsedInOperatingActivities"
             and f.period_end == f"{args.bsns_year}-12-31"
             and (not f.dimensions or "ConsolidatedMember" in str(f.dimensions))),
            None,
        )
        capex = next(
            (f.value for f in source_pack.facts
             if f.concept == "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"
             and f.period_end == f"{args.bsns_year}-12-31"
             and (not f.dimensions or "ConsolidatedMember" in str(f.dimensions))),
            None,
        )
        market_cap = market_snap.market_cap_krw if market_snap else None
        auth_facts = build_authoritative_facts(
            market_cap_krw=market_cap,
            revenue_krw=rev,
            operating_income_krw=oi,
            operating_cash_flow_krw=ocf,
            capex_krw=capex,
        )
        if auth_facts:
            print(f"권위 사실 dict: {len(auth_facts)}개 항목 (V4 cross-section 검증용)")

    sections = list(SECTION_SPECS.keys()) if args.section == "all" else [args.section]
    if args.section != "all" and args.section not in SECTION_SPECS:
        print(f"unknown section: {args.section}")
        return 1

    # incremental 모드: sections_final/<id>.md 이미 있으면 skip (LLM 호출 절약).
    # batch에서 timeout/rate-limit으로 partial 진전 후 재시작 시 progress 누적.
    incremental = getattr(args, "incremental", False)
    if incremental:
        skipped = [s for s in sections if (report_dir / f"{s}.md").exists()]
        if skipped:
            print(f"[incremental] sections_final 이미 존재 — skip: {', '.join(skipped)}")
        sections = [s for s in sections if not (report_dir / f"{s}.md").exists()]

    if not sections:
        print(f"[incremental] 모든 섹션 sections_final에 존재 — 합본 단계로 직행")
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
                authoritative_facts=auth_facts,
            )
        except SectionBuildError as e:
            v2_passed = e.v2.passed if e.v2 is not None else True
            v4_passed = len(e.v4) == 0
            print(f"  FAILED. V1: {e.v1.passed}, V2: {v2_passed}, V3: {e.v3.passed}, V4: {v4_passed}")
            if not e.v1.passed:
                print(f"  V1 detail: {e.v1.render()[:1500]}")
            if not e.v3.passed:
                print(f"  V3 detail: {e.v3.render()[:1500]}")
            if e.v2 is not None and not e.v2.passed:
                print(f"  V2 fails ({len(e.v2.failures)}):")
                for f in e.v2.failures[:10]:
                    print(f"    L{f.line} [{f.category}] {f.snippet[:80]}")
                    print(f"      → {f.message[:600]}")
            if e.v4:
                print(f"  V4 fails ({len(e.v4)}):")
                for v in e.v4[:10]:
                    print(
                        f"    L{v.line_no} '{v.fact_label}' "
                        f"기대 {v.expected_krw/1e12:.2f}조, 발견 '{v.found_text}' "
                        f"({v.found_value_krw/1e12:.2f}조, 편차 {v.deviation_pct:+.1f}%)"
                    )
            for i, raw in enumerate(e.raw_outputs, 1):
                snapshot.save_section_raw(report_dir, f"{sec}.attempt-{i}.failed", raw)
            failed_any = True
            continue

        text_guard = report_quality.validate_generated_text(result.final_text)
        if not text_guard.passed:
            print(f"  FAILED quality guard")
            print(text_guard.render())
            for i, raw in enumerate(result.raw_outputs, 1):
                snapshot.save_section_raw(report_dir, f"{sec}.attempt-{i}.quality_failed", raw)
            failed_any = True
            continue

        # best_effort 섹션은 V2 scale guard 우회 (이미 retry 한도 초과)
        if result.v2_validation and not result.best_effort:
            scale_warnings = [
                w for w in result.v2_validation.warnings
                if w.category == "numeric_scale_mismatch"
            ]
            if scale_warnings:
                print(f"  FAILED numeric scale guard: {len(scale_warnings)} signal(s)")
                for w in scale_warnings[:5]:
                    print(f"    L{w.line}: {w.message}")
                for i, raw in enumerate(result.raw_outputs, 1):
                    snapshot.save_section_raw(report_dir, f"{sec}.attempt-{i}.numeric_failed", raw)
                failed_any = True
                continue

        if result.best_effort:
            print(f"  ⚠ BEST-EFFORT (validator {result.attempts}회 모두 reject — last attempt 채택)")
            # validator warnings를 별도 파일로 사용자 review용 저장
            v_warnings_lines = ["# Validator Warnings — best-effort fallback\n"]
            v_warnings_lines.append(f"이 섹션은 V1~V4 검증 {result.attempts}회 모두 실패. ")
            v_warnings_lines.append("무한 retry 방지를 위해 마지막 attempt를 채택. 수동 review 권장.\n\n")
            if not result.v1_validation.passed:
                v_warnings_lines.append(f"## V1 (출처/형식)\n{result.v1_validation.render()}\n\n")
            if not result.v3_validation.passed:
                v_warnings_lines.append(f"## V3 (산술)\n{result.v3_validation.render()}\n\n")
            if result.v2_validation and not result.v2_validation.passed:
                v_warnings_lines.append(f"## V2 (자릿수)\n{result.v2_validation.render()}\n\n")
            if result.v4_violations:
                v_warnings_lines.append(
                    f"## V4 (cross-section)\n{cross_section_consistency.render_violations(result.v4_violations)}\n\n"
                )
            (report_dir / f"{sec}.v_warnings.md").write_text(
                "".join(v_warnings_lines), encoding="utf-8"
            )
        else:
            print(f"  PASSED in {result.attempts} attempt(s)")

        for i, raw in enumerate(result.raw_outputs, 1):
            snapshot.save_section_raw(report_dir, f"{sec}.attempt-{i}", raw)
        snapshot.save_section_final(report_dir, sec, result.final_text)
        if result.v2_validation and result.v2_validation.warnings:
            print(f"  V2 warnings: {len(result.v2_validation.warnings)}")

    if failed_any:
        print(f"\n일부 섹션 실패 — 합본 skip")
        return 2

    if args.section != "all" and not args.assemble:
        print(f"\n단일 섹션 생성 완료 — stale 합본 방지를 위해 00_종합진단.md 재조립은 skip")
        return 0

    print(f"\n=== 합본 작성 ===")
    target = assemble_report(
        report_dir=report_dir,
        company=company,
        period=args.period,
        timestamps=timestamps,
        frame=frame,
        write_owner_summary=not args.skip_owner_summary,
        market_snapshot=market_snapshot,
        foreign_snapshot=foreign_snapshot,
    )
    assembled_guard = report_quality.validate_generated_text(
        target.read_text(encoding="utf-8")
    )
    if not assembled_guard.passed:
        print(f"ERROR: 합본 품질 가드 실패")
        print(assembled_guard.render())
        return 2
    print(f"saved: {target}")
    return 0


def _cmd_assemble(args: argparse.Namespace) -> int:
    watchlist = parse_watchlist(config.WATCHLIST_PATH.read_text(encoding="utf-8"))
    entry = find_by_ticker(watchlist, args.ticker)
    if not entry:
        print(f"ERROR: ticker {args.ticker} _watchlist.md에 없음")
        return 1

    company = entry.name
    report_dir = config.COMPANIES_DIR / company / args.period
    missing = [
        sec for sec in SECTION_SPECS
        if not (report_dir / f"{sec}.md").exists()
    ]
    if missing:
        print("ERROR: 합본에 필요한 섹션이 없습니다:")
        for sec in missing:
            print(f"  - {sec}")
        return 1

    failed_sections: list[str] = []
    for sec in SECTION_SPECS:
        text = (report_dir / f"{sec}.md").read_text(encoding="utf-8")
        guard = report_quality.validate_generated_text(text)
        if not guard.passed:
            failed_sections.append(sec)
            print(f"ERROR: {sec} 품질 가드 실패")
            print(guard.render())
    if failed_sections:
        return 2

    today = datetime.now().strftime("%Y-%m-%d")
    timestamps = DataTimestamps(
        written_at=today,
        dart_query_at=args.dart_query_at or f"DART API ({today})",
        financial_basis=args.financial_basis or f"{args.period} 보고서",
        market_price=args.market_price,
        foreign_holding=args.foreign_holding,
        macro_data=args.macro_data,
    )
    target = assemble_report(
        report_dir=report_dir,
        company=company,
        period=args.period,
        timestamps=timestamps,
        frame=load_frame(),
        write_owner_summary=not args.skip_owner_summary,
    )
    assembled_guard = report_quality.validate_generated_text(
        target.read_text(encoding="utf-8")
    )
    if not assembled_guard.passed:
        print(f"ERROR: 합본 품질 가드 실패")
        print(assembled_guard.render())
        return 2
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
    p_gen.add_argument("--max-chars", type=int, default=200_000, help="단일 DART 원문 파일 최대")
    p_gen.add_argument(
        "--max-total-chars",
        type=int,
        default=120_000,
        help="전체 DART 원문 합산 예산. 200KB 초과 시 LLM timeout 위험 — 120KB로 절감.",
    )
    p_gen.add_argument("--skip-fetch", action="store_true", help="이미 받은 데이터 재사용")
    p_gen.add_argument("--skip-owner-summary", action="store_true", help="합본의 owner-valuation 한 페이지 LLM 호출 skip")
    p_gen.add_argument(
        "--incremental", action="store_true",
        help="sections_final/<id>.md 이미 있으면 skip — batch 재시작 시 progress 누적"
    )
    p_gen.add_argument("--allow-missing-xbrl", action="store_true", help="XBRL 없어도 생성 허용 (기본은 정기보고서에서 hard fail)")
    p_gen.add_argument("--assemble", action="store_true", help="단일 섹션 실행 후에도 합본 재조립")

    p_assemble = sub.add_parser("assemble", help="이미 생성된 섹션들로 00_종합진단.md 합본 작성")
    p_assemble.add_argument("--ticker", required=True, help="KRX 6자리 (예: 005930)")
    p_assemble.add_argument("--period", required=True, help="폴더명 (예: 2025-annual)")
    p_assemble.add_argument("--financial-basis", default=None)
    p_assemble.add_argument("--dart-query-at", default=None)
    p_assemble.add_argument("--market-price", default="(별도 시장 데이터 미포함 — 자동 모드 v0.1)")
    p_assemble.add_argument("--foreign-holding", default="(별도 외인 데이터 미포함)")
    p_assemble.add_argument("--macro-data", default="(별도 매크로 데이터 미포함)")
    p_assemble.add_argument("--skip-owner-summary", action="store_true")

    args = parser.parse_args()
    if args.cmd == "map-corps":
        return _cmd_map_corps(args)
    if args.cmd == "generate":
        return _cmd_generate(args)
    if args.cmd == "assemble":
        return _cmd_assemble(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
