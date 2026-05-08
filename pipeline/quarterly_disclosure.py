"""사업보고서 이후 발표된 최신 분기 잠정실적·분기보고서 자동 통합.

프레임 5.3은 "데이터 기준시점"을 의무로 두지만, 사업보고서(annual)만 다루면
1Q 잠정실적 발표 후 시점이 어긋난다. 셀사이드 IB는 잠정실적 즉시 반영하는데
우리 시스템도 같은 시점성을 가져야 owner-valuation의 X 값이 stale하지 않음.

본 모듈은 DART OpenAPI list.json에서 (corp_code, 사업보고서 접수일 이후)의
**잠정실적 / 분기보고서 / 영업(잠정)실적** 공시를 검색해 메타·요약을 source_pack과
별도 영역으로 LLM에 주입한다. 본문 다운로드는 옵션.

페르소나 부합:
  - 1Q 잠정실적 = "이번 분기 변화" 섹션의 최신 데이터
  - 사업보고서 시점에 묶어두면 owner-valuation의 X(시총·FCF)가 stale
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from pathlib import Path


_INTERIM_KEYWORDS = (
    "잠정실적",
    "영업(잠정)실적",
    "영업잠정실적",
    "연결재무제표기준영업(잠정)실적",
    "분기보고서",
    "반기보고서",
    "주요사항보고서(영업정지)",
    "주요사항보고서",
)


@dataclass(frozen=True)
class InterimFiling:
    rcept_no: str
    report_nm: str
    rcept_dt: str  # YYYYMMDD
    days_after_annual: int  # 사업보고서 접수 이후 며칠
    likely_period_end: str | None  # 추정 — 보고서명에서 분기 끝 추정
    body_excerpt: str | None = None  # 본문 다운로드 후 일부 발췌 (선택)


@dataclass(frozen=True)
class QuarterlyDisclosure:
    company: str
    annual_rcept_dt: str
    fetched_at: str
    interim_filings: list[InterimFiling] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_prompt_dict(self) -> dict:
        return {
            "company": self.company,
            "annual_rcept_dt": self.annual_rcept_dt,
            "fetched_at": self.fetched_at,
            "interim_filings": [asdict(f) for f in self.interim_filings],
            "sources": self.sources,
            "notes": self.notes,
            "usage_rule": (
                "사업보고서 이후 시점에 발표된 잠정실적/분기보고서가 있으면 "
                "**08_이번분기변화 + 02_재무건강진단 + 03_수익성진단 + owner-valuation 종합 페이지**에 반드시 반영해라. "
                "사업보고서 숫자만으로 stale하게 결론을 내지 마라.\n"
                "\n"
                "**body_excerpt 인용 절대 규칙** (02·08 환각 차단):\n"
                "- interim_filings[0].body_excerpt가 비어있지 않으면 그 안의 정확한 매출·영업이익·영업이익률 수치를 **그대로 그대로 인용**해라.\n"
                "- 학습 데이터 기반 추정 금지. 1Q 영업이익을 'X조'로 추측하지 말 것.\n"
                "- 본문에 '연결재무제표기준영업(잠정)실적'이라고 적혀 있으면 그게 1Q 잠정실적이며, 그 안의 수치가 1순위.\n"
                "- body_excerpt에 수치가 안 보이면 '잠정실적 공시 인지 — 본문에서 정량 수치 미확인'으로 정직 처리.\n"
                "\n"
                "잠정실적이 없으면 '사업보고서 시점 기준 — 이후 분기 데이터 없음'으로 명시."
            ),
        }


def _guess_period_end(report_nm: str, rcept_dt: str) -> str | None:
    """보고서명·접수일로 분기 끝 추정.

    예:
      - "1분기보고서" + 20260515 → 2026-03-31
      - "영업(잠정)실적" + 20260108 → 2025-12-31 (4Q)
    """
    name = report_nm or ""
    try:
        rd = datetime.strptime(rcept_dt, "%Y%m%d")
    except ValueError:
        return None
    year = rd.year
    if "1분기" in name:
        return f"{year}-03-31"
    if "반기" in name or "2분기" in name:
        return f"{year}-06-30"
    if "3분기" in name:
        return f"{year}-09-30"
    if "잠정실적" in name or "영업(잠정)실적" in name or "분기보고서" in name or "반기보고서" in name:
        # 잠정실적·분기보고서: 접수월 기준으로 직전 분기 끝 추정
        m = rd.month
        if m in (1, 2, 3):
            return f"{year - 1}-12-31" if m <= 2 else f"{year}-03-31"
        if m in (4, 5):
            return f"{year}-03-31"
        if m in (6, 7, 8):
            return f"{year}-06-30"
        if m in (9, 10, 11):
            return f"{year}-09-30"
        if m == 12:
            return f"{year}-09-30"
    return None


def _fetch_filing_body_excerpt(rcept_no: str, max_chars: int = 4000) -> str | None:
    """잠정실적 본문 ZIP 다운로드 후 텍스트 추출 일부 (best-effort).

    실패 시 None. 본문은 보통 짧은 공정공시(<10KB)라 다운로드 부담 적음.
    """
    try:
        from pipeline import config
        from pipeline.dart_client import DartClient
    except ImportError:
        return None
    if not config.DART_API_KEY:
        return None

    import io
    import re as _re
    import tempfile
    import zipfile
    from pathlib import Path

    try:
        client = DartClient()
        r = client._get("document.xml", {"rcept_no": rcept_no})
        if not r.content.startswith(b"PK"):
            return None
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                first_text: str | None = None
                for name in z.namelist():
                    if not name.lower().endswith((".xml", ".html", ".htm")):
                        continue
                    with z.open(name) as src:
                        raw = src.read().decode("utf-8", errors="replace")
                    plain = _re.sub(r"<[^>]+>", "", raw)
                    plain = _re.sub(r"\s+", " ", plain).strip()
                    if plain:
                        first_text = plain
                        break
                if first_text:
                    return first_text[:max_chars]
    except Exception:
        return None
    return None


def fetch_quarterly_disclosures(
    company: str,
    corp_code: str,
    annual_rcept_dt: str,
    look_forward_days: int = 400,
    fetch_body_for_latest: bool = True,
) -> QuarterlyDisclosure:
    """DART list.json — 사업보고서 접수일 이후의 잠정실적·분기보고서 검색."""
    sources: dict[str, str] = {}
    notes: list[str] = []
    filings: list[InterimFiling] = []

    try:
        from pipeline import config
        from pipeline.dart_client import DartClient, DartApiError
    except ImportError:
        notes.append("DART 모듈 import 실패")
        return QuarterlyDisclosure(
            company=company,
            annual_rcept_dt=annual_rcept_dt,
            fetched_at=datetime.now().strftime("%Y-%m-%d"),
            interim_filings=filings,
            sources=sources,
            notes=notes,
        )
    if not config.DART_API_KEY:
        notes.append("DART_API_KEY 미설정 — fetch skip")
        return QuarterlyDisclosure(
            company=company,
            annual_rcept_dt=annual_rcept_dt,
            fetched_at=datetime.now().strftime("%Y-%m-%d"),
            interim_filings=filings,
            sources=sources,
            notes=notes,
        )

    try:
        annual_dt = datetime.strptime(annual_rcept_dt, "%Y%m%d")
    except ValueError:
        notes.append(f"annual_rcept_dt 형식 오류: {annual_rcept_dt}")
        return QuarterlyDisclosure(
            company=company,
            annual_rcept_dt=annual_rcept_dt,
            fetched_at=datetime.now().strftime("%Y-%m-%d"),
            interim_filings=filings,
            sources=sources,
            notes=notes,
        )

    bgn = (annual_dt + timedelta(days=1)).strftime("%Y%m%d")
    end = (annual_dt + timedelta(days=look_forward_days)).strftime("%Y%m%d")

    try:
        client = DartClient()
        page = 1
        while True:
            data = client.list_filings(
                corp_code=corp_code,
                bgn_de=bgn,
                end_de=end,
                pblntf_ty=None,  # A=정기, B=주요사항보고 둘 다 잡으려면 필터 X
                page_no=page,
                page_count=100,
                last_reprt_at="Y",
            )
            for item in data.get("list", []):
                report_nm = item.get("report_nm", "") or ""
                if not any(kw in report_nm for kw in _INTERIM_KEYWORDS):
                    continue
                rcept_dt = item.get("rcept_dt", "")
                try:
                    days_after = (datetime.strptime(rcept_dt, "%Y%m%d") - annual_dt).days
                except ValueError:
                    days_after = -1
                filings.append(
                    InterimFiling(
                        rcept_no=item.get("rcept_no", ""),
                        report_nm=report_nm,
                        rcept_dt=rcept_dt,
                        days_after_annual=days_after,
                        likely_period_end=_guess_period_end(report_nm, rcept_dt),
                    )
                )
            total_page = data.get("total_page", 1)
            if page >= total_page:
                break
            page += 1
        sources["interim_filings"] = "DART list.json"
    except Exception as e:
        notes.append(f"DART list.json fetch 실패: {e}")

    if not filings:
        notes.append("사업보고서 접수일 이후 잠정실적·분기보고서 0건 — owner-valuation은 사업보고서 시점 그대로 사용")

    # 최신 순으로 정렬
    filings.sort(key=lambda f: f.rcept_dt, reverse=True)

    # 가장 최신 잠정실적·분기보고서 본문 일부 다운로드 (owner-valuation에 직접 활용)
    if fetch_body_for_latest and filings:
        latest = filings[0]
        body = _fetch_filing_body_excerpt(latest.rcept_no)
        if body:
            filings[0] = InterimFiling(
                rcept_no=latest.rcept_no,
                report_nm=latest.report_nm,
                rcept_dt=latest.rcept_dt,
                days_after_annual=latest.days_after_annual,
                likely_period_end=latest.likely_period_end,
                body_excerpt=body,
            )
            sources["latest_body_excerpt"] = "DART document.xml (최신 1건)"

    return QuarterlyDisclosure(
        company=company,
        annual_rcept_dt=annual_rcept_dt,
        fetched_at=datetime.now().strftime("%Y-%m-%d"),
        interim_filings=filings,
        sources=sources,
        notes=notes,
    )


def load_quarterly_disclosures(
    cache_path: Path,
    company: str,
    corp_code: str,
    annual_rcept_dt: str,
    max_age_hours: int = 12,
) -> QuarterlyDisclosure:
    if cache_path.exists():
        age_h = (
            datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
        ).total_seconds() / 3600
        if age_h < max_age_hours:
            try:
                data = json.loads(cache_path.read_text(encoding="utf-8"))
                interim_data = data.pop("interim_filings", [])
                snap = QuarterlyDisclosure(
                    **data,
                    interim_filings=[InterimFiling(**f) for f in interim_data],
                )
                return snap
            except (json.JSONDecodeError, TypeError, KeyError):
                pass

    snap = fetch_quarterly_disclosures(company, corp_code, annual_rcept_dt)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(asdict(snap), ensure_ascii=False, indent=2), encoding="utf-8")
    return snap
