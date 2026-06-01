"""DART OpenAPI 클라이언트.

opendart.fss.or.kr/guide/main.do 스펙 기반.

핵심 엔드포인트:
  - corpCode.xml   — 전체 회사 ↔ corp_code 매핑 (ZIP)
  - list.json      — 공시 검색
  - document.xml   — 공시 원문 (HTML 본문 ZIP)
  - fnlttXbrl.xml  — 재무제표 XBRL 패키지 (ZIP)
  - fnlttSinglAcntAll.json — 단일 회사 전체 재무 (JSON)

모든 호출에 crtfc_key 필수. 키는 config.DART_API_KEY (환경변수 DART_API_KEY).
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from pipeline import config


REPRT_CODE_ANNUAL = "11011"
REPRT_CODE_H1 = "11012"
REPRT_CODE_Q1 = "11013"
REPRT_CODE_Q3 = "11014"

REPRT_CODE_LABELS = {
    REPRT_CODE_ANNUAL: "사업보고서",
    REPRT_CODE_H1: "반기보고서",
    REPRT_CODE_Q1: "1분기보고서",
    REPRT_CODE_Q3: "3분기보고서",
}

PERIOD_TO_REPRT_CODE = {
    "annual": REPRT_CODE_ANNUAL,
    "H1": REPRT_CODE_H1,
    "Q1": REPRT_CODE_Q1,
    "Q3": REPRT_CODE_Q3,
}


@dataclass(frozen=True)
class FilingMeta:
    rcept_no: str
    corp_code: str
    corp_name: str
    report_nm: str
    rcept_dt: str
    flr_nm: str
    rm: str

    @classmethod
    def from_dict(cls, d: dict) -> "FilingMeta":
        return cls(
            rcept_no=d.get("rcept_no", ""),
            corp_code=d.get("corp_code", ""),
            corp_name=d.get("corp_name", ""),
            report_nm=d.get("report_nm", ""),
            rcept_dt=d.get("rcept_dt", ""),
            flr_nm=d.get("flr_nm", ""),
            rm=d.get("rm", ""),
        )


class DartApiError(Exception):
    pass


class DartClient:
    def __init__(self, api_key: str | None = None, timeout: int = 60):
        self.api_key = api_key or config.DART_API_KEY
        if not self.api_key:
            raise DartApiError(
                "DART_API_KEY 없음. .env에 DART_API_KEY=... 설정 또는 인자로 전달."
            )
        self.timeout = timeout
        self.base_url = config.DART_BASE_URL

    def _redact(self, text: str) -> str:
        """API 키가 텍스트(URL·로그 등)에 포함됐을 때 마스킹."""
        if not self.api_key:
            return text
        return text.replace(self.api_key, "***REDACTED***")

    def _safe_endpoint(self, endpoint: str, params: dict) -> str:
        """로그·에러용 안전한 식별자 — 키 제외."""
        safe_params = {k: v for k, v in params.items() if k != "crtfc_key"}
        return f"{endpoint}({safe_params})"

    def _get(self, endpoint: str, params: dict[str, Any]) -> requests.Response:
        url = f"{self.base_url}/{endpoint}"
        full_params = {"crtfc_key": self.api_key, **params}
        try:
            r = requests.get(url, params=full_params, timeout=self.timeout)
        except requests.RequestException as e:
            # 에러 메시지에 키 포함 가능 — 마스킹
            raise DartApiError(
                f"DART 요청 실패 {self._safe_endpoint(endpoint, params)}: "
                f"{self._redact(str(e))}"
            ) from None
        if r.status_code >= 400:
            raise DartApiError(
                f"DART {endpoint} HTTP {r.status_code} "
                f"params={ {k: v for k, v in params.items()} }"
            )
        return r

    def list_filings(
        self,
        corp_code: str | None = None,
        bgn_de: str | None = None,
        end_de: str | None = None,
        pblntf_ty: str | None = None,
        page_no: int = 1,
        page_count: int = 100,
        last_reprt_at: str = "Y",
    ) -> dict:
        """공시 검색.

        pblntf_ty:
          A=정기공시, B=주요사항보고, C=발행공시, D=지분공시, E=기타공시,
          F=외부감사관련, G=펀드공시, H=자산유동화, I=거래소공시, J=공정위공시
        last_reprt_at='Y' → 정정보고서 있으면 최종본만
        """
        params: dict[str, Any] = {
            "page_no": page_no,
            "page_count": page_count,
            "last_reprt_at": last_reprt_at,
        }
        if corp_code:
            params["corp_code"] = corp_code
        if bgn_de:
            params["bgn_de"] = bgn_de
        if end_de:
            params["end_de"] = end_de
        if pblntf_ty:
            params["pblntf_ty"] = pblntf_ty

        r = self._get("list.json", params)
        data = r.json()
        if data.get("status") not in ("000", None):
            raise DartApiError(
                f"list.json status={data.get('status')} message={data.get('message')}"
            )
        return data

    def find_periodic_report(
        self,
        corp_code: str,
        bsns_year: int,
        reprt_code: str,
    ) -> FilingMeta | None:
        """특정 회사의 특정 연도·주기 정기보고서 찾기 (최신 1건만 — 기존 호환).

        검색 범위: bsns_year 시작 ~ bsns_year+1년 6월 (사업보고서는 다음해 3월말 제출).
        정정공시 fail 등 fallback 필요 시 find_periodic_reports 사용.
        """
        results = self.find_periodic_reports(corp_code, bsns_year, reprt_code)
        return results[0] if results else None

    def find_periodic_reports(
        self,
        corp_code: str,
        bsns_year: int,
        reprt_code: str,
    ) -> list[FilingMeta]:
        """특정 회사의 특정 연도·주기 정기보고서 모두 (정정공시 + 원본 포함).

        반환 순서: 최신(=정정공시) → 과거(=원본) 순.
        정정공시 다운로드 fail 시 원본 fallback 가능.
        """
        bgn = f"{bsns_year}0101"
        end = f"{bsns_year + 1}0630"

        # DART 실제 report_nm format:
        #   사업보고서 (2025.12)
        #   반기보고서 (2026.06)
        #   분기보고서 (2026.03)  ← 1Q
        #   분기보고서 (2026.09)  ← 3Q
        # 분기 보고서는 같은 "분기보고서" label이라 월(MM)로 구분.
        def _matches(item: dict) -> bool:
            name = item.get("report_nm", "")
            if reprt_code == REPRT_CODE_ANNUAL:
                return "사업보고서" in name
            if reprt_code == REPRT_CODE_H1:
                return "반기보고서" in name
            if reprt_code == REPRT_CODE_Q1:
                return "분기보고서" in name and f"({bsns_year}.03)" in name
            if reprt_code == REPRT_CODE_Q3:
                return "분기보고서" in name and f"({bsns_year}.09)" in name
            return False

        out: list[FilingMeta] = []
        page = 1
        while True:
            data = self.list_filings(
                corp_code=corp_code,
                bgn_de=bgn,
                end_de=end,
                pblntf_ty="A",
                page_no=page,
                page_count=100,
            )
            for item in data.get("list", []):
                if _matches(item):
                    out.append(FilingMeta.from_dict(item))
            total_page = data.get("total_page", 1)
            if page >= total_page:
                break
            page += 1
        return out

    def download_corp_code_zip(self, dest_dir: Path) -> Path:
        """전체 회사 코드 ZIP → CORPCODE.xml."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        r = self._get("corpCode.xml", {})
        if not r.content.startswith(b"PK"):
            raise DartApiError(f"corpCode.xml not ZIP: {r.text[:200]}")
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            z.extractall(dest_dir)
        target = dest_dir / "CORPCODE.xml"
        if not target.exists():
            raise DartApiError("CORPCODE.xml not found after extract")
        return target

    def download_filing_document(self, rcept_no: str, dest_dir: Path) -> list[Path]:
        """공시 원문 ZIP 다운로드 → 압축 해제. 보고서 본문 (HTML/XML) 추출."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        r = self._get("document.xml", {"rcept_no": rcept_no})
        if not r.content.startswith(b"PK"):
            raise DartApiError(f"document.xml not ZIP for {rcept_no}: {r.text[:200]}")
        extracted: list[Path] = []
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            for name in z.namelist():
                # CP949 → UTF-8 normalize
                try:
                    safe_name = name.encode("cp437").decode("euc-kr")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    safe_name = name
                target = dest_dir / safe_name
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(name) as src, open(target, "wb") as dst:
                    dst.write(src.read())
                extracted.append(target)
        return extracted

    def download_xbrl(
        self, rcept_no: str, reprt_code: str, dest_dir: Path
    ) -> list[Path] | None:
        """XBRL 패키지 ZIP 다운로드 → 압축 해제.

        없으면 None 반환 (잠정실적 등 일부 보고서는 XBRL 미제공).
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        try:
            r = self._get("fnlttXbrl.xml", {"rcept_no": rcept_no, "reprt_code": reprt_code})
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            raise

        if not r.content.startswith(b"PK"):
            return None  # JSON 에러 또는 빈 응답

        extracted: list[Path] = []
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            for name in z.namelist():
                try:
                    safe_name = name.encode("cp437").decode("euc-kr")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    safe_name = name
                target = dest_dir / safe_name
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(name) as src, open(target, "wb") as dst:
                    dst.write(src.read())
                extracted.append(target)
        return extracted

    def get_financial_statements(
        self,
        corp_code: str,
        bsns_year: int,
        reprt_code: str,
        fs_div: str = "CFS",
    ) -> dict:
        """단일 회사 전체 재무제표 (요약, JSON).

        fs_div: CFS=연결, OFS=별도
        """
        params = {
            "corp_code": corp_code,
            "bsns_year": str(bsns_year),
            "reprt_code": reprt_code,
            "fs_div": fs_div,
        }
        r = self._get("fnlttSinglAcntAll.json", params)
        data = r.json()
        if data.get("status") not in ("000", None):
            return {"status": data.get("status"), "message": data.get("message"), "list": []}
        return data
