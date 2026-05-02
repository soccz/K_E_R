"""K_E_R 보고서 → soccz.github.io 시각화 HTML 렌더러.

소스: companies/<기업명>/<period>/00_종합진단.md (또는 섹션별 .md)
타깃: <site_root>/projects/k-e-r/<기업명>/<period>/index.html

디자인 언어: soccz.github.io의 warm beige/cream + terracotta 액센트.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path

import markdown


SITE_K_E_R_PATH = Path("/home/soccz/22tb/soccz.github.io/projects/k-e-r")


@dataclass(frozen=True)
class ReportEntry:
    company: str
    period: str
    title: str
    summary: str
    md_path: Path
    html_rel_path: str
    written_at: str
    sector: str | None = None


# ---------------- shared CSS (matches soccz.github.io palette) ----------------

_SHARED_CSS = """
*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
:root {
  /* 기업 리서치 보고서 톤 — cool, professional */
  --bg: #f8f9fb;
  --surface: #ffffff;
  --surface-alt: #fbfcfd;
  --surface-hover: #f3f5f9;
  --border: #e3e8ef;
  --border-light: #eef1f6;
  --border-strong: #cbd5e1;
  --text: #0f172a;
  --text-secondary: #334155;
  --text-muted: #64748b;
  --text-light: #94a3b8;
  --accent: #1e3a8a;
  --accent-light: #eff6ff;
  --accent-hover: #1e40af;
  --accent-soft: #93c5fd;
  --positive: #15803d;
  --positive-light: #f0fdf4;
  --negative: #b91c1c;
  --negative-light: #fef2f2;
  --warn: #b45309;
  --warn-light: #fefce8;
  --tag-bg: #eef1f6;
  --tag-text: #475569;
  --max-w: 1080px;
  --content-w: 820px;
  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 8px;
  --shadow-sm: 0 1px 2px rgba(15,23,42,0.04);
  --shadow-md: 0 2px 8px rgba(15,23,42,0.06);
  --shadow-lg: 0 8px 24px rgba(15,23,42,0.08);
}
html { scroll-behavior: smooth; }
body {
  font-family: 'Inter', 'Noto Sans KR', -apple-system, BlinkMacSystemFont, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.7;
  padding-bottom: 80px;
  -webkit-font-smoothing: antialiased;
  font-feature-settings: 'cv11', 'ss01';
}
::selection { background: var(--accent-light); color: var(--accent); }
a { color: var(--accent); text-decoration: none; transition: color 0.15s; }
a:hover { color: var(--accent-hover); text-decoration: underline; }

.site-header {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  position: sticky; top: 0; z-index: 100;
  padding: 14px 24px;
}
.site-header .inner {
  max-width: var(--max-w); margin: 0 auto;
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
}
.site-header .brand {
  font-family: 'IBM Plex Sans', 'Inter', sans-serif;
  font-weight: 700; font-size: 16px; letter-spacing: -0.01em;
  display: flex; align-items: center; gap: 10px;
  color: var(--text);
}
.site-header .brand .badge {
  background: var(--accent-light); color: var(--accent);
  padding: 2px 10px; border-radius: 4px;
  font-size: 11px; font-weight: 600; letter-spacing: 0.05em;
  text-transform: uppercase;
}
.site-header nav a {
  color: var(--text-secondary); margin-left: 18px; font-size: 13px;
  font-weight: 500;
}
.site-header nav a:hover { color: var(--accent); text-decoration: none; }

.container { max-width: var(--max-w); margin: 0 auto; padding: 28px 24px; }

/* HERO — 보고서 표지 */
.page-hero {
  margin: 8px 0 32px;
  padding: 32px 36px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-top: 3px solid var(--accent);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}
.page-hero .doc-tag {
  display: inline-block;
  background: var(--accent-light); color: var(--accent);
  padding: 3px 10px; border-radius: 4px;
  font-size: 11px; font-weight: 600; letter-spacing: 0.08em;
  text-transform: uppercase; margin-bottom: 14px;
}
.page-hero h1 {
  font-family: 'IBM Plex Sans', 'Inter', sans-serif;
  font-size: 30px; font-weight: 700; line-height: 1.2;
  margin-bottom: 6px; letter-spacing: -0.02em;
}
.page-hero .subtitle {
  color: var(--text-muted); font-size: 15px;
}
.page-hero .meta {
  display: flex; gap: 24px; flex-wrap: wrap;
  margin-top: 20px; padding-top: 16px;
  border-top: 1px dashed var(--border);
  font-size: 13px;
}
.page-hero .meta .item {
  display: inline-flex; flex-direction: column; gap: 2px;
}
.page-hero .meta .item .label {
  color: var(--text-light); font-size: 11px;
  text-transform: uppercase; letter-spacing: 0.06em;
}
.page-hero .meta .item .value {
  color: var(--text-secondary); font-weight: 500;
}

/* ARTICLE — 본문 */
article.report {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 56px 64px;
  box-shadow: var(--shadow-sm);
  max-width: var(--content-w); margin: 0 auto;
}
article.report > h1:first-child { margin-top: 0; }
article.report h1 {
  font-family: 'IBM Plex Sans', 'Inter', sans-serif;
  font-size: 26px; font-weight: 700; letter-spacing: -0.015em;
  margin: 36px 0 16px;
  padding-bottom: 12px;
  border-bottom: 2px solid var(--accent);
}
article.report h2 {
  font-family: 'IBM Plex Sans', 'Inter', sans-serif;
  font-size: 20px; font-weight: 700; letter-spacing: -0.01em;
  margin: 40px 0 14px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
  color: var(--text);
}
article.report h3 {
  font-size: 16px; font-weight: 600;
  margin: 28px 0 10px;
  color: var(--text);
}
article.report h4 {
  font-size: 14px; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.05em; color: var(--text-secondary);
  margin: 22px 0 8px;
}
article.report p { margin: 12px 0; }
article.report ul, article.report ol { margin: 12px 0 12px 24px; }
article.report li { margin: 4px 0; }

/* 데이터 기준시점 박스 (blockquote 첫 위치) */
article.report blockquote {
  border-left: 3px solid var(--accent);
  background: var(--surface-alt);
  padding: 14px 20px;
  margin: 20px 0;
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  font-size: 13px;
  color: var(--text-secondary);
}
article.report blockquote strong { color: var(--accent); }
article.report blockquote p { margin: 4px 0; }
article.report blockquote ul { margin: 6px 0 0 20px; }

/* 코드 — 출처 인용 [...] 형식 */
article.report code {
  background: var(--tag-bg); color: var(--tag-text);
  padding: 1px 6px; border-radius: 3px;
  font-family: 'IBM Plex Mono', 'Menlo', monospace;
  font-size: 88%; font-weight: 500;
}
article.report pre {
  background: var(--surface-alt); border: 1px solid var(--border);
  padding: 16px; border-radius: var(--radius-sm);
  overflow-x: auto; margin: 16px 0;
  font-size: 13px;
}
article.report pre code { background: transparent; padding: 0; }

/* 표 — 재무 데이터 스타일 */
article.report table {
  width: 100%; border-collapse: collapse; margin: 20px 0;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm); overflow: hidden;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}
article.report table th, article.report table td {
  padding: 9px 14px; text-align: left;
  border-bottom: 1px solid var(--border-light);
}
article.report table th {
  background: var(--surface-alt);
  font-weight: 600; color: var(--text);
  border-bottom: 1.5px solid var(--border-strong);
  font-size: 12px; letter-spacing: 0.02em;
}
article.report table td:not(:first-child) { text-align: right; font-feature-settings: 'tnum'; }
article.report table th:not(:first-child) { text-align: right; }
article.report table tr:last-child td { border-bottom: none; }
article.report table tr:hover { background: var(--surface-hover); }
article.report table strong { color: var(--text); }

article.report hr {
  border: none; border-top: 1px solid var(--border-light);
  margin: 32px 0;
}

article.report em { color: var(--text-muted); font-style: normal; }

/* INDEX — 카드 그리드 */
.section-title {
  font-family: 'IBM Plex Sans', 'Inter', sans-serif;
  font-weight: 700; font-size: 18px;
  margin: 32px 0 14px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
  color: var(--text);
  display: flex; align-items: baseline; justify-content: space-between;
}
.section-title .more {
  font-size: 13px; font-weight: 500;
  color: var(--accent);
}
.report-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
  margin: 16px 0;
}
.report-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 20px 22px;
  transition: transform 0.16s, box-shadow 0.16s, border-color 0.16s;
  position: relative;
}
.report-card:hover {
  transform: translateY(-1px);
  border-color: var(--border-strong);
  box-shadow: var(--shadow-md);
}
.report-card .badge {
  display: inline-block;
  background: var(--accent-light); color: var(--accent);
  padding: 3px 8px; border-radius: 3px;
  font-size: 10px; font-weight: 700; letter-spacing: 0.06em;
  text-transform: uppercase;
  margin-bottom: 10px;
}
.report-card h3 {
  font-family: 'IBM Plex Sans', 'Inter', sans-serif;
  font-size: 16px; font-weight: 600;
  margin-bottom: 6px; letter-spacing: -0.01em;
}
.report-card .desc {
  color: var(--text-secondary); font-size: 13px;
  line-height: 1.6;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
  overflow: hidden;
}
.report-card .meta {
  margin-top: 14px; padding-top: 10px;
  border-top: 1px solid var(--border-light);
  font-size: 11px; color: var(--text-muted);
  display: flex; justify-content: space-between;
  letter-spacing: 0.02em;
}

footer.site-footer {
  margin-top: 60px;
  padding: 20px 24px;
  text-align: center;
  color: var(--text-muted); font-size: 12px;
  border-top: 1px solid var(--border);
  background: var(--surface);
}
footer.site-footer p { margin: 3px 0; }

/* 모바일 */
@media (max-width: 720px) {
  article.report { padding: 28px 22px; }
  article.report h1 { font-size: 22px; }
  .page-hero { padding: 24px; }
  .page-hero h1 { font-size: 24px; }
  article.report table { font-size: 12px; }
  article.report table th, article.report table td { padding: 7px 10px; }
}
"""


def _wrap_html(title: str, body: str, breadcrumb: str = "") -> str:
    head_extra = ""
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape(title)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@300;400;500;600;700&family=Noto+Sans+KR:wght@300;400;500;700&display=swap" rel="stylesheet">
  <style>{_SHARED_CSS}</style>
</head>
<body>
  <header class="site-header">
    <div class="inner">
      <div class="brand">
        <span>K_E_R</span>
        <span class="badge">Korea Equity Reports</span>
      </div>
      <nav>
        <a href="/">soccz.github.io</a>
        <a href="/projects/k-e-r/">전체 보고서</a>
      </nav>
    </div>
  </header>
  {breadcrumb}
  <div class="container">
    {body}
  </div>
  <footer class="site-footer">
    <p>K_E_R · DART 기반 자동 생성 · 출처 검증 + 추론 명시 + XBRL ground truth</p>
    <p style="margin-top:6px">생성: {datetime.now().strftime('%Y-%m-%d %H:%M %Z')}</p>
  </footer>
</body>
</html>"""


def _md_to_html(md_text: str) -> str:
    md = markdown.Markdown(
        extensions=[
            "fenced_code", "tables", "footnotes", "attr_list",
            "toc", "sane_lists", "smarty",
        ],
        extension_configs={"toc": {"toc_depth": "2-3"}},
    )
    return md.convert(md_text)


def _extract_one_liner(md_text: str, max_len: int = 200) -> str:
    """첫 의미 단락 (헤더·메타박스 제외)."""
    in_box = False
    for raw in md_text.splitlines():
        s = raw.strip()
        if s.startswith("> **데이터 기준시점**") or (in_box and s.startswith(">")):
            in_box = True
            continue
        if in_box and not s.startswith(">"):
            in_box = False
        if not s or s.startswith("#") or s.startswith("---") or s.startswith(">"):
            continue
        if len(s) >= 20:
            if len(s) > max_len:
                return s[:max_len] + "…"
            return s
    return ""


def render_report_to_html(
    md_path: Path,
    out_html_path: Path,
    company: str,
    period: str,
    written_at: str | None = None,
) -> None:
    md_text = md_path.read_text(encoding="utf-8")
    body_md = _md_to_html(md_text)
    written = written_at or datetime.fromtimestamp(md_path.stat().st_mtime).strftime("%Y-%m-%d")

    breadcrumb = f"""
<div class="container" style="padding-top:20px; padding-bottom:0; font-size:14px; color:var(--text-muted);">
  <a href="../../index.html">← K_E_R 전체 보고서</a> &nbsp;·&nbsp;
  <a href="../index.html">{escape(company)}</a> &nbsp;·&nbsp; {escape(period)}
</div>"""

    hero = f"""
<div class="page-hero">
  <h1>{escape(company)} <span style="color:var(--text-muted);font-weight:400">· {escape(period)}</span></h1>
  <div class="meta">
    <span class="item">📅 작성 {escape(written)}</span>
    <span class="item">🔍 DART 기반 자동 진단</span>
    <span class="item">✓ 출처 검증 + 추론 명시</span>
  </div>
</div>"""

    body = hero + f'<article class="report">{body_md}</article>'
    title = f"{company} {period} 종합진단 — K_E_R"
    out_html_path.parent.mkdir(parents=True, exist_ok=True)
    out_html_path.write_text(_wrap_html(title, body, breadcrumb), encoding="utf-8")


def render_company_index(
    company: str,
    company_dir: Path,
    out_html_path: Path,
    entries: list[ReportEntry],
) -> None:
    cards: list[str] = []
    for e in sorted(entries, key=lambda x: x.period, reverse=True):
        cards.append(
            f"""
<a href="{escape(e.html_rel_path)}" style="text-decoration:none;color:inherit;">
  <div class="report-card">
    <span class="badge">{escape(e.period)}</span>
    <h3>{escape(e.title)}</h3>
    <p class="desc">{escape(e.summary)}</p>
    <div class="meta">
      <span>{escape(e.written_at)}</span>
      <span>→ 본문 보기</span>
    </div>
  </div>
</a>"""
        )

    body = f"""
<div class="page-hero">
  <h1>{escape(company)}</h1>
  <p style="color:var(--text-secondary)">분기·연간 종합 진단 누적 ({len(entries)}건)</p>
</div>

<div class="report-grid">
  {''.join(cards)}
</div>"""

    breadcrumb = f"""
<div class="container" style="padding-top:20px; padding-bottom:0; font-size:14px; color:var(--text-muted);">
  <a href="../index.html">← K_E_R 전체 보고서</a> &nbsp;·&nbsp; {escape(company)}
</div>"""

    title = f"{company} — K_E_R"
    out_html_path.parent.mkdir(parents=True, exist_ok=True)
    out_html_path.write_text(_wrap_html(title, body, breadcrumb), encoding="utf-8")


def render_master_index(
    out_html_path: Path,
    companies: dict[str, list[ReportEntry]],
) -> None:
    sections: list[str] = []
    sorted_companies = sorted(companies.items(), key=lambda x: x[0])
    for company, entries in sorted_companies:
        cards: list[str] = []
        for e in sorted(entries, key=lambda x: x.period, reverse=True)[:3]:
            cards.append(
                f"""
<a href="{escape(e.html_rel_path)}" style="text-decoration:none;color:inherit;">
  <div class="report-card">
    <span class="badge">{escape(e.period)}</span>
    <h3>{escape(company)}</h3>
    <p class="desc">{escape(e.summary)}</p>
    <div class="meta">
      <span>{escape(e.written_at)}</span>
      <span>→ 본문 보기</span>
    </div>
  </div>
</a>"""
            )
        if cards:
            sections.append(f"""
<h2 style="font-family:'Space Grotesk';margin:36px 0 14px">{escape(company)}
  <a href="{escape(company)}/index.html" style="font-size:14px;font-weight:400;margin-left:12px">전체 보기 →</a>
</h2>
<div class="report-grid">{''.join(cards)}</div>""")

    body = f"""
<div class="page-hero">
  <h1>K_E_R — Korea Equity Reports</h1>
  <p style="color:var(--text-secondary);margin-top:8px;font-size:15px">
    DART 기반 한국 상장사 종합 진단. 출처 엄격주의 + 추론 명시 + XBRL ground truth.
  </p>
  <div class="meta">
    <span class="item">코스피 24종목 · 섹터별 분산</span>
    <span class="item">분기 단위 누적</span>
    <span class="item">기업 종합 검진 톤</span>
  </div>
</div>

{''.join(sections) if sections else '<p>아직 보고서가 없습니다.</p>'}"""

    title = "K_E_R — Korea Equity Reports"
    out_html_path.parent.mkdir(parents=True, exist_ok=True)
    out_html_path.write_text(_wrap_html(title, body), encoding="utf-8")


def discover_reports(companies_dir: Path) -> dict[str, list[ReportEntry]]:
    """companies/<기업명>/<period>/ 트리에서 00_종합진단.md (또는 01_*.md) 찾기.

    각 보고서의 entry 구성: company, period, title, summary, paths.
    합본 우선, 없으면 첫 섹션.
    """
    out: dict[str, list[ReportEntry]] = {}
    if not companies_dir.exists():
        return out

    for company_dir in sorted(companies_dir.iterdir()):
        if not company_dir.is_dir():
            continue
        company = company_dir.name
        entries: list[ReportEntry] = []
        for period_dir in sorted(company_dir.iterdir()):
            if not period_dir.is_dir():
                continue
            period = period_dir.name
            md_candidates = [
                period_dir / "00_종합진단.md",
                period_dir / "01_사업구조진단.md",
            ]
            md_path = next((p for p in md_candidates if p.exists()), None)
            if md_path is None:
                continue

            md_text = md_path.read_text(encoding="utf-8")
            summary = _extract_one_liner(md_text)
            written_at = datetime.fromtimestamp(md_path.stat().st_mtime).strftime("%Y-%m-%d")
            html_rel = f"{period}/index.html"
            title = f"{company} {period} 종합진단" if md_path.name.startswith("00_") else f"{company} {period} (부분)"
            entries.append(
                ReportEntry(
                    company=company,
                    period=period,
                    title=title,
                    summary=summary,
                    md_path=md_path,
                    html_rel_path=html_rel,
                    written_at=written_at,
                )
            )
        if entries:
            out[company] = entries
    return out


def render_all(companies_dir: Path, site_root: Path) -> tuple[int, int]:
    """전체 변환 — companies → site_root/projects/k-e-r/.
    반환: (회사 수, 보고서 수)
    """
    discovered = discover_reports(companies_dir)
    site_root.mkdir(parents=True, exist_ok=True)

    total_reports = 0
    for company, entries in discovered.items():
        company_html_dir = site_root / company
        for entry in entries:
            html_path = company_html_dir / entry.period / "index.html"
            render_report_to_html(
                md_path=entry.md_path,
                out_html_path=html_path,
                company=company,
                period=entry.period,
                written_at=entry.written_at,
            )
            total_reports += 1
        company_index = company_html_dir / "index.html"
        render_company_index(company, company_html_dir, company_index, entries)

    master = site_root / "index.html"
    render_master_index(master, discovered)
    return len(discovered), total_reports
