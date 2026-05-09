"""외국인 보유 동향 fetcher — 페르소나 ★★★ 항목 데이터 보강.

페르소나는 다음 4가지를 우선시한다:
  1. 외인 보유 비중 절대값
  2. 추세 (4분기 이상)
  3. 장기 외인(연기금·SWF·패시브) vs 단기 외인 구분
  4. 국내 인기 vs 외인 동향 디커플링

데이터 소스:
  - DART majorstock.json: 5% 이상 보유공시 — 일부 글로벌 패시브 펀드(Vanguard·BlackRock 등) 잡힘
  - DART 사업보고서 IV. 주주현황: SK스퀘어 등 최대주주 + '기타주주' 합산만, 외국인 별도 분리 X
  - KRX 외국인 보유 한도소진률 (pykrx, KRX_ID/KRX_PW 인증):
    - 일별 외인 보유 비중·보유주식수·한도수량 — 1·2·4 항목 직접 데이터
    - 장기 vs 단기 외인 구분은 여전히 미통합 (KRX 투자자유형별 거래 OpenAPI 별도 필요)

v0.2: DART majorstock + KRX 일별 외인 비중 통합. KRX_ID/KRX_PW 미설정 시
KRX 부분 자동 skip (DART만으로도 동작).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class MajorHolder:
    """5% 이상 보유공시 1건."""

    holder_name: str
    nationality: str  # "KR" | "FOREIGN" | "UNKNOWN" — 이름 패턴 휴리스틱
    holding_pct: float | None  # 최근 보고된 보유 비중
    purpose: str  # 보유목적 (단순투자/일반투자/경영참여)
    report_date: str  # 보고서 접수일


@dataclass(frozen=True)
class ForeignHoldingSnapshot:
    ticker: str
    company_name: str
    fetch_date: str
    major_holders: list[MajorHolder] = field(default_factory=list)
    foreign_major_holders_count: int = 0
    foreign_major_holders_pct_sum: float | None = None  # 외국인 5%이상 보유 합산 (참고치)
    # KRX 일별 외인 보유 (pykrx 인증 필요)
    krx_daily_foreign_pct: float | None = None  # 가장 최근 영업일 외인 보유 비중
    krx_daily_foreign_history: list[dict] = field(default_factory=list)  # 최근 N영업일 추이
    krx_foreign_pct_change_5d: float | None = None  # 5영업일 전 대비 변동 (pp)
    sources: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_prompt_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "company": self.company_name,
            "fetch_date": self.fetch_date,
            "major_holders": [asdict(h) for h in self.major_holders],
            "foreign_major_holders_count": self.foreign_major_holders_count,
            "foreign_major_holders_pct_sum_note": (
                "DART 5%이상 보유공시 기준 외국인 합산 — 추세 데이터 아님, 시점 스냅샷."
            ),
            "foreign_major_holders_pct_sum": self.foreign_major_holders_pct_sum,
            "krx_daily_foreign_pct": self.krx_daily_foreign_pct,
            "krx_foreign_pct_change_5d": self.krx_foreign_pct_change_5d,
            "krx_daily_foreign_history": self.krx_daily_foreign_history,
            "sources": self.sources,
            "notes": self.notes,
            "usage_rule": (
                "★★★ 페르소나 외인 동향 항목. major_holders는 DART 5% 이상 보유공시에서 잡히는 "
                "장기 외인(글로벌 패시브) 표본. krx_daily_foreign_pct는 KRX 정식 외인 보유 비중 "
                "(전체 외인 — 5% 미만 포함). krx_foreign_pct_change_5d는 5영업일 전 대비 pp 변동. "
                "'장기 vs 단기 외인 구분'만 여전히 KRX 미통합 → 그 부분은 '확인되지 않음'으로 처리."
            ),
        }


# 외국인 패턴 휴리스틱: 이름에 영문/한자가 많거나 알려진 글로벌 펀드명
_FOREIGN_NAME_KEYWORDS = (
    "BlackRock", "Vanguard", "State Street", "Capital", "Schwab",
    "Norges", "GIC", "ADIA", "JPMorgan", "Fidelity", "Wellington",
    "Aberdeen", "Schroder", "Nuveen", "Geode", "Northern Trust",
    "Sumitomo", "Mizuho", "Nomura", "Mitsubishi",
    "Inc", "Ltd", "Corp", "AG", "S.A.", "N.V.", "Pte",
    "Limited", "Trust",
)


def _classify_nationality(holder_name: str) -> str:
    name = (holder_name or "").strip()
    if not name:
        return "UNKNOWN"
    # 한국 법인·개인 휴리스틱: 한글이 다수 + (주식회사/㈜/주) 표기
    has_korean = any("가" <= c <= "힯" for c in name)
    has_latin_alpha = any(c.isascii() and c.isalpha() for c in name)
    matches_foreign = any(kw in name for kw in _FOREIGN_NAME_KEYWORDS)
    if matches_foreign:
        return "FOREIGN"
    if has_korean and not matches_foreign:
        # 한국계 외국인 펀드 (예: '국민연금공단')도 한글이지만 외국인 아님
        return "KR"
    if has_latin_alpha and not has_korean:
        return "FOREIGN"
    return "UNKNOWN"


def _fetch_dart_majorstock(corp_code: str) -> list[dict]:
    """DART majorstock.json — 대량보유 5% 보고 list.

    실패 시 빈 list. 결과는 raw item dict 그대로.
    """
    try:
        from pipeline import config
        from pipeline.dart_client import DartClient, DartApiError
    except ImportError:
        return []
    if not config.DART_API_KEY:
        return []
    try:
        client = DartClient()
        r = client._get("majorstock.json", {"corp_code": corp_code})
        data = r.json()
    except Exception:
        return []
    if data.get("status") not in ("000", None):
        return []
    return list(data.get("list") or [])


def _fetch_krx_foreign_holdings(ticker_krx: str, days: int = 30) -> list[dict]:
    """KRX 일별 외인 보유 비중 (pykrx 인증).

    반환: [{date, holding_pct, holding_shares, listed_shares, exhaustion_pct}, ...]
    최신 → 과거 순. 인증 실패 또는 pykrx 미설치 시 빈 리스트.
    """
    import os

    if not (os.getenv("KRX_ID") and os.getenv("KRX_PW")):
        return []
    try:
        from pykrx import stock
    except ImportError:
        return []
    end = datetime.now()
    from datetime import timedelta as _td

    start = end - _td(days=int(days * 1.6) + 5)
    try:
        df = stock.get_exhaustion_rates_of_foreign_investment_by_date(
            start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), ticker_krx
        )
    except Exception:
        return []
    if df is None or df.empty:
        return []
    out: list[dict] = []
    for idx, row in df.iterrows():
        try:
            out.append(
                {
                    "date": idx.strftime("%Y-%m-%d"),
                    "holding_pct": float(row["지분율"]),
                    "holding_shares": int(row["보유수량"]),
                    "listed_shares": int(row["상장주식수"]),
                    "exhaustion_pct": float(row["한도소진률"]),
                }
            )
        except (KeyError, ValueError, TypeError):
            continue
    out.sort(key=lambda d: d["date"], reverse=True)
    return out[:days]


def fetch_foreign_holding_snapshot(
    ticker_krx: str,
    company_name: str,
    corp_code: str | None,
) -> ForeignHoldingSnapshot:
    sources: dict[str, str] = {}
    notes: list[str] = []
    holders: list[MajorHolder] = []

    if corp_code:
        raw = _fetch_dart_majorstock(corp_code)
        # DART 응답은 보고 시점별 누적 — 가장 최근 보고만 holder별로 keep
        latest_by_name: dict[str, dict] = {}
        for item in raw:
            name = (item.get("repror") or item.get("repor_nm") or "").strip()
            rcept = item.get("rcept_dt", "")
            if not name:
                continue
            cur = latest_by_name.get(name)
            if cur is None or rcept > cur.get("rcept_dt", ""):
                latest_by_name[name] = item
        for name, item in latest_by_name.items():
            try:
                pct = float(item.get("stkrt") or 0) if item.get("stkrt") else None
            except ValueError:
                pct = None
            holders.append(
                MajorHolder(
                    holder_name=name,
                    nationality=_classify_nationality(name),
                    holding_pct=pct,
                    purpose=(item.get("repror_nm_cd_nm") or item.get("repor_nm") or ""),
                    report_date=item.get("rcept_dt", ""),
                )
            )
        if raw:
            sources["major_holders"] = "DART majorstock.json"
        else:
            notes.append("DART majorstock.json에서 5% 이상 보유공시 0건 — 외인 패시브 펀드가 5% 미만일 수 있음")
    else:
        notes.append("corp_code 미제공 — DART majorstock fetch skip")

    foreign_holders = [h for h in holders if h.nationality == "FOREIGN"]
    foreign_count = len(foreign_holders)
    foreign_pct_sum = (
        sum(h.holding_pct for h in foreign_holders if h.holding_pct is not None)
        if foreign_holders
        else None
    )
    if foreign_pct_sum is not None and foreign_pct_sum == 0:
        foreign_pct_sum = None

    # KRX 일별 외인 보유 비중 (KRX_ID/KRX_PW 인증 필요)
    krx_history = _fetch_krx_foreign_holdings(ticker_krx, days=30)
    krx_latest_pct: float | None = None
    krx_change_5d: float | None = None
    if krx_history:
        krx_latest_pct = krx_history[0]["holding_pct"]
        # 5영업일 전 대비 변동 (pp)
        if len(krx_history) >= 6:
            krx_change_5d = round(
                krx_history[0]["holding_pct"] - krx_history[5]["holding_pct"], 3
            )
        sources["krx_foreign_pct"] = "KRX 외국인 보유 한도소진률 (pykrx 인증)"
    else:
        notes.append(
            "KRX 일별 외인 보유 비중 미수집 — KRX_ID/KRX_PW 미설정 또는 인증 실패. "
            "DART 5% 이상 보유공시(major_holders)만 제공."
        )

    return ForeignHoldingSnapshot(
        ticker=ticker_krx,
        company_name=company_name,
        fetch_date=datetime.now().strftime("%Y-%m-%d"),
        major_holders=holders,
        foreign_major_holders_count=foreign_count,
        foreign_major_holders_pct_sum=foreign_pct_sum,
        krx_daily_foreign_pct=krx_latest_pct,
        krx_daily_foreign_history=krx_history,
        krx_foreign_pct_change_5d=krx_change_5d,
        sources=sources,
        notes=notes,
    )


def load_foreign_holding_snapshot(
    cache_path: Path,
    ticker_krx: str,
    company_name: str,
    corp_code: str | None,
    max_age_hours: int = 24,
) -> ForeignHoldingSnapshot:
    if cache_path.exists():
        age_h = (
            datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
        ).total_seconds() / 3600
        if age_h < max_age_hours:
            try:
                data = json.loads(cache_path.read_text(encoding="utf-8"))
                holders_data = data.pop("major_holders", [])
                # 구버전 cache 호환 (krx_daily_foreign_history / change_5d 미존재)
                data.setdefault("krx_daily_foreign_history", [])
                data.setdefault("krx_foreign_pct_change_5d", None)
                snap = ForeignHoldingSnapshot(
                    **data,
                    major_holders=[MajorHolder(**h) for h in holders_data],
                )
                return snap
            except (json.JSONDecodeError, TypeError, KeyError):
                pass

    snap = fetch_foreign_holding_snapshot(ticker_krx, company_name, corp_code)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(snap)
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return snap
