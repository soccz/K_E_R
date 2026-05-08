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

from pipeline.watchlist_parser import WatchlistEntry, parse_watchlist
from pipeline.macro_data import IndicatorSnapshot, load_macro_snapshot


SITE_K_E_R_PATH = Path("/home/soccz/22tb/soccz.github.io/projects/k-e-r")
MACRO_CACHE_PATH = Path("/home/soccz/22tb/report/pipeline/cache/macro_snapshot.json")


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


import hashlib

from pipeline.site_styles import SHARED_CSS as _SHARED_CSS


SITE_BASE_URL = "https://soccz.github.io/projects/k-e-r"
SITE_OG_IMAGE = "https://soccz.github.io/assets/og-image.svg"

# CSS 외부화 — 페이지마다 35KB 인라인 중복 → 1회 캐시.
# query string에 content-hash로 cache busting (CSS 변경 시 자동 무효화).
_CSS_HASH = hashlib.md5(_SHARED_CSS.encode("utf-8")).hexdigest()[:8]
_CSS_HREF = f"/projects/k-e-r/assets/k-e-r.css?v={_CSS_HASH}"


def _wrap_html(
    title: str,
    body: str,
    breadcrumb: str = "",
    description: str = "",
    canonical_path: str = "",
    og_type: str = "website",
    published_time: str | None = None,
) -> str:
    desc = description or "DART 기반 한국 상장사 종합 진단. 출처 검증 + 추론 명시 + XBRL ground truth."
    canonical_url = f"{SITE_BASE_URL}/{canonical_path.lstrip('/')}" if canonical_path else SITE_BASE_URL
    pub_meta = (
        f'<meta property="article:published_time" content="{escape(published_time)}">'
        if og_type == "article" and published_time
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="{escape(desc)}">
  <meta name="theme-color" content="#14213d">
  <title>{escape(title)}</title>
  <meta property="og:title" content="{escape(title)}">
  <meta property="og:description" content="{escape(desc)}">
  <meta property="og:type" content="{escape(og_type)}">
  <meta property="og:site_name" content="K_E_R — Korea Equity Reports">
  <meta property="og:url" content="{escape(canonical_url)}">
  <meta property="og:image" content="{SITE_OG_IMAGE}">
  <meta property="og:locale" content="ko_KR">
  {pub_meta}
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{escape(title)}">
  <meta name="twitter:description" content="{escape(desc)}">
  <meta name="twitter:image" content="{SITE_OG_IMAGE}">
  <link rel="canonical" href="{escape(canonical_url)}">
  <link rel="icon" type="image/svg+xml" href="/assets/favicon.svg">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&family=Inter:wght@400;500;600;700&family=Noto+Sans+KR:wght@400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{_CSS_HREF}">
  <script>
    // 테마 — localStorage > prefers-color-scheme 순. inline으로 첫 페인트 전 적용 (FOUC 방지).
    (function(){{
      try {{
        var t = localStorage.getItem('ker-theme');
        if (t === 'dark' || t === 'light') document.documentElement.setAttribute('data-theme', t);
      }} catch(e) {{}}
    }})();
    window.kerToggleTheme = function() {{
      var cur = document.documentElement.getAttribute('data-theme');
      var next;
      if (cur === 'dark') next = 'light';
      else if (cur === 'light') next = 'dark';
      else {{
        // 시스템 따라가는 상태에서 토글 → 시스템과 반대로
        var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        next = prefersDark ? 'light' : 'dark';
      }}
      document.documentElement.setAttribute('data-theme', next);
      try {{ localStorage.setItem('ker-theme', next); }} catch(e) {{}}
    }};
  </script>
</head>
<body>
  <header class="site-header">
    <div class="inner">
      <a class="brand" href="/projects/k-e-r/" title="전체 보고서">
        <span>K_E_R</span>
        <span class="divider"></span>
        <span class="badge">Korea Equity Reports</span>
      </a>
      <nav>
        <a href="/">soccz.github.io</a>
        <button class="theme-toggle" onclick="window.kerToggleTheme()" aria-label="테마 변경" title="라이트/다크 모드">
          <span class="sun">☀</span><span class="moon">☾</span>
        </button>
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
  <button class="scroll-top" onclick="window.scrollTo({{top:0,behavior:'smooth'}})" aria-label="맨 위로">↑</button>
  <script>
    // scroll-to-top 버튼 visibility + smooth anchor scroll offset
    (function(){{
      var st = document.querySelector('.scroll-top');
      if (st) window.addEventListener('scroll', function(){{
        st.classList.toggle('visible', window.scrollY > 400);
      }});
      // anchor link → smooth scroll (with header offset)
      document.querySelectorAll('a[href^="#"]').forEach(function(a){{
        a.addEventListener('click', function(e){{
          var id = a.getAttribute('href').slice(1);
          if (!id) return;
          var t = document.getElementById(id) || document.querySelector('[id="'+id+'"]');
          if (!t) return;
          e.preventDefault();
          var top = t.getBoundingClientRect().top + window.scrollY - 70;
          window.scrollTo({{top: top, behavior: 'smooth'}});
          history.replaceState(null, '', '#'+id);
          // close drawer if open
          var dr = document.getElementById('tocDrawer');
          if (dr) dr.classList.remove('open');
        }});
      }});

      // 보고서 표 셀 자동 색칠 — 등락률·증감 패턴 감지 → .num-up/.num-down/.num-neg 클래스
      document.querySelectorAll('article.report table td').forEach(function(td){{
        var t = td.textContent.trim();
        if (!t || t === '—' || t === '-' || t === 'n/a') return;
        // "+12.3%", "-5.1%", "+1.5%p" 등 변화율
        if (/^[+]\\s*\\d/.test(t) && t.indexOf('%') >= 0) {{
          td.classList.add('num-up', 'num-with-bar');
        }} else if (/^[-−△▼]\\s*\\d/.test(t) && t.indexOf('%') >= 0) {{
          td.classList.add('num-down', 'num-with-bar');
        }} else if (/^[△▼]/.test(t) || /\\(적자\\)|\\(loss\\)/i.test(t)) {{
          td.classList.add('num-neg');
        }}
      }});
    }})();
  </script>
</body>
</html>"""


def _make_md() -> "markdown.Markdown":
    """동일 인스턴스 재사용 (TOC 슬러그 일관성).

    한글 헤더 보존을 위해 slugify_unicode 명시.
    기본 slugify는 unicodedata.normalize로 한글을 ASCII로 변환해서 깨짐.
    """
    from markdown.extensions.toc import slugify_unicode
    return markdown.Markdown(
        extensions=[
            "fenced_code", "tables", "footnotes", "attr_list",
            "toc", "sane_lists", "smarty",
        ],
        extension_configs={
            "toc": {
                "toc_depth": "2-3",
                "anchorlink": False,
                "slugify": slugify_unicode,
            }
        },
    )


def _md_to_html(md_text: str) -> str:
    md = _make_md()
    return md.convert(md_text)


def _slugify_for_toc(title: str) -> str:
    """markdown.extensions.toc.slugify_unicode와 동일 — 한글 보존."""
    from markdown.extensions.toc import slugify_unicode
    return slugify_unicode(title, "-")


def _period_to_friendly(period: str) -> str:
    """폴더명 → 친근한 라벨.

    2025-annual  → 사업보고서 (2025)
    2025-H1      → 반기보고서 (2025)
    2026-Q1      → 1분기보고서 (2026)
    2026-Q3      → 3분기보고서 (2026)
    그 외        → period 원본
    """
    import re
    m = re.match(r"^(\d{4})-(annual|H1|Q1|Q3)$", period.strip())
    if not m:
        return period
    year, kind = m.group(1), m.group(2)
    label = {
        "annual": "사업보고서",
        "H1": "반기보고서",
        "Q1": "1분기보고서",
        "Q3": "3분기보고서",
    }[kind]
    return f"{label} ({year})"


def _extract_one_liner(md_text: str, max_len: int = 200) -> str:
    """첫 *의미 단락* — 헤더·메타박스·TOC·코드블럭 모두 스킵하고 실제 산문 추출.

    합본의 "30초 회사 소개" 단락이 가장 유용. 그게 안 잡히면 첫 산문.
    """
    import re

    # 1. "30초 회사 소개" 또는 "회사 소개" 섹션 *이후*의 첫 단락 우선 시도
    soco_match = re.search(
        r"(?:30초\s*회사\s*소개|회사\s*소개)\s*\n+([^\n#].+?)(?:\n\n|\n#)",
        md_text, re.DOTALL,
    )
    if soco_match:
        para = soco_match.group(1).strip()
        # 마크다운 링크 [text](url) → text만
        para = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", para)
        if len(para) >= 20:
            return para[:max_len] + ("…" if len(para) > max_len else "")

    # 2. 일반 fallback — 첫 산문 단락
    in_box = False
    in_code = False
    for raw in md_text.splitlines():
        s = raw.strip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if s.startswith("> **데이터 기준시점**") or (in_box and s.startswith(">")):
            in_box = True
            continue
        if in_box and not s.startswith(">"):
            in_box = False
        if not s or s.startswith("#") or s.startswith("---") or s.startswith(">"):
            continue
        # TOC-like 링크 list 스킵: "- [text](url)" 형식
        if re.match(r"^[-*+]\s*\[.+\]\(.+\)\s*$", s):
            continue
        # 일반 list item이지만 짧은 건 스킵
        if s.startswith(("-", "*", "+")) and len(s) < 40:
            continue
        # 마크다운 링크 → 텍스트로 변환
        s_clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
        if len(s_clean) >= 20:
            return s_clean[:max_len] + ("…" if len(s_clean) > max_len else "")
    return ""


def _build_toc(md_text: str) -> str:
    """본문 헤더(##, ###)에서 TOC sidebar HTML 생성. markdown TOC와 동일 슬러그."""
    import re
    items: list[tuple[int, str, str]] = []
    in_code = False
    for line in md_text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = re.match(r"^(#{2,3})\s+(.+)$", line)
        if not m:
            continue
        level = len(m.group(1))
        title = m.group(2).strip().rstrip("#").strip()
        anchor = _slugify_for_toc(title)
        items.append((level, anchor, title))

    if not items:
        return ""

    def render_list(items: list, sidebar: bool = True) -> str:
        out: list[str] = ["<ul>"]
        current_level = 2
        for lvl, anchor, title in items:
            if lvl > current_level:
                out.append("<ul>")
            elif lvl < current_level:
                out.append("</ul>")
            current_level = lvl
            out.append(f'<li><a href="#{escape(anchor)}">{escape(title)}</a></li>')
        while current_level > 2:
            out.append("</ul>")
            current_level -= 1
        out.append("</ul>")
        return "".join(out)

    sidebar_html = (
        '<aside class="report-toc">'
        '<div class="toc-title">목차</div>'
        + render_list(items)
        + "</aside>"
    )
    drawer_html = (
        '<div class="toc-drawer" id="tocDrawer" aria-hidden="true">'
        '<div class="toc-drawer-inner">'
        '<div class="toc-drawer-head">'
        '<span class="toc-title">목차</span>'
        '<button class="toc-close" onclick="document.getElementById(\'tocDrawer\').classList.remove(\'open\')" aria-label="닫기">×</button>'
        '</div>'
        + render_list(items)
        + '</div></div>'
        '<button class="toc-fab" onclick="document.getElementById(\'tocDrawer\').classList.toggle(\'open\')" aria-label="목차">'
        '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="13" y2="18"/></svg>'
        '</button>'
    )
    return sidebar_html + drawer_html


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
    friendly = _period_to_friendly(period)
    toc_html = _build_toc(md_text)

    breadcrumb = f"""
<div class="container" style="padding-top:24px; padding-bottom:0; font-size:12px; color:var(--text-muted); letter-spacing:0.04em;">
  <a href="../../index.html" style="color:var(--text-muted)">K_E_R</a>
  &nbsp;/&nbsp;
  <a href="../index.html" style="color:var(--text-muted)">{escape(company)}</a>
  &nbsp;/&nbsp;
  <span style="color:var(--text-secondary)">{escape(friendly)}</span>
</div>"""

    hero = f"""
<div class="page-hero">
  <span class="doc-tag">Equity Diagnosis Report</span>
  <h1>{escape(company)} <span class="secondary">· {escape(friendly)}</span></h1>
  <p class="subtitle">DART 공시 기반 종합 검진 — 출처 검증 + 추론 명시 + XBRL ground truth</p>
  <div class="meta">
    <div class="item"><span class="label">Issuer</span><span class="value">{escape(company)}</span></div>
    <div class="item"><span class="label">Period</span><span class="value">{escape(friendly)}</span></div>
    <div class="item"><span class="label">Written</span><span class="value">{escape(written)}</span></div>
    <div class="item"><span class="label">Source</span><span class="value">DART OpenAPI · XBRL</span></div>
  </div>
</div>"""

    body = hero + f"""
<div class="report-layout">
  <article class="report">{body_md}</article>
  {toc_html}
</div>"""

    title = f"{company} {friendly} — K_E_R"
    summary_for_meta = _extract_one_liner(md_text, max_len=160)
    out_html_path.parent.mkdir(parents=True, exist_ok=True)
    out_html_path.write_text(
        _wrap_html(title, body, breadcrumb, description=summary_for_meta),
        encoding="utf-8",
    )


def render_company_index(
    company: str,
    company_dir: Path,
    out_html_path: Path,
    entries: list[ReportEntry],
) -> None:
    """회사별 보고서 목록 — 정렬 토글(최신순/과거순) 포함."""
    sorted_entries = sorted(entries, key=lambda x: x.period, reverse=True)
    cards: list[str] = []
    for idx, e in enumerate(sorted_entries):
        friendly = _period_to_friendly(e.period)
        cards.append(
            f"""
<a href="{escape(e.html_rel_path)}"
   class="report-card-link"
   data-period="{escape(e.period)}"
   data-written="{escape(e.written_at)}"
   data-order="{idx}">
  <div class="report-card">
    <span class="badge">{escape(e.period)}</span>
    <h3>{escape(friendly)}</h3>
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
  <span class="doc-tag">Issuer Coverage</span>
  <h1>{escape(company)}</h1>
  <p class="subtitle">분기·연간 종합 진단 — 누적 {len(entries)}건</p>
</div>

<div class="list-controls">
  <span class="list-controls-label">정렬</span>
  <div class="sort-toggle" role="tablist">
    <button class="sort-btn active" data-sort="newest" onclick="window.kerSort('newest')">최신순</button>
    <button class="sort-btn" data-sort="oldest" onclick="window.kerSort('oldest')">과거순</button>
  </div>
  <span class="list-controls-count">{len(entries)}건</span>
</div>

<div class="report-grid" id="reportGrid">
  {''.join(cards)}
</div>

<script>
  window.kerSort = function(mode) {{
    var grid = document.getElementById('reportGrid');
    var items = Array.from(grid.querySelectorAll('.report-card-link'));
    items.sort(function(a, b) {{
      var pa = a.dataset.period, pb = b.dataset.period;
      return mode === 'oldest' ? pa.localeCompare(pb) : pb.localeCompare(pa);
    }});
    items.forEach(function(el) {{ grid.appendChild(el); }});
    document.querySelectorAll('.sort-btn').forEach(function(b) {{
      b.classList.toggle('active', b.dataset.sort === mode);
    }});
  }};
</script>"""

    breadcrumb = f"""
<div class="container" style="padding-top:24px; padding-bottom:0; font-size:12px; color:var(--text-muted); letter-spacing:0.04em;">
  <a href="../index.html" style="color:var(--text-muted)">K_E_R</a>
  &nbsp;/&nbsp;
  <span style="color:var(--text-secondary)">{escape(company)}</span>
</div>"""

    title = f"{company} — K_E_R"
    out_html_path.parent.mkdir(parents=True, exist_ok=True)
    out_html_path.write_text(_wrap_html(title, body, breadcrumb), encoding="utf-8")


def _render_sparkline_svg(values: list[float], up: bool, w: int = 140, h: int = 32) -> str:
    """SVG 스파크라인 — 가벼운 인라인 차트."""
    if not values or len(values) < 2:
        return ""
    vmin, vmax = min(values), max(values)
    rng = vmax - vmin or 1.0
    n = len(values)
    pts: list[str] = []
    for i, v in enumerate(values):
        x = i / (n - 1) * w
        y = h - ((v - vmin) / rng) * h
        pts.append(f"{x:.1f},{y:.1f}")
    poly_pts = " ".join(pts)
    # area fill
    area_pts = f"0,{h} " + poly_pts + f" {w},{h}"
    color_class = "spark-up" if up else "spark-down"
    return (
        f'<svg viewBox="0 0 {w} {h}" class="sparkline {color_class}" '
        f'preserveAspectRatio="none">'
        f'<polygon points="{area_pts}" class="spark-area"/>'
        f'<polyline points="{poly_pts}" class="spark-line" fill="none"/>'
        f'</svg>'
    )


def _render_macro_bar(snapshots: list[IndicatorSnapshot]) -> str:
    """매크로 4지표 한 줄 — KOSPI/KOSPI200/USDKRW/WTI 인라인 SVG 스파크라인.

    데이터: yfinance fetch + 24h 캐시. 일일 cron(18:00 KST)으로 자동 refresh.
    """
    if not snapshots:
        return ""
    cells: list[str] = []
    for s in snapshots:
        up = (s.change_pct_1d or 0) >= 0
        spark = _render_sparkline_svg(s.sparkline, up=up)
        change_color = "macro-up" if up else "macro-down"
        change_1d_str = (
            f"{'▲' if up else '▼'} {abs(s.change_pct_1d or 0):.2f}%"
            if s.change_pct_1d is not None else "—"
        )
        change_1y_str = (
            f"{s.change_pct_1y:+.1f}% (1Y)"
            if s.change_pct_1y is not None else ""
        )
        cells.append(f"""
<div class="macro-cell">
  <div class="macro-head">
    <span class="macro-label">{escape(s.label)}</span>
    <span class="macro-symbol">{escape(s.symbol)}</span>
  </div>
  <div class="macro-value">{escape(s.latest_str)}</div>
  {spark}
  <div class="macro-changes">
    <span class="{change_color}">{change_1d_str}</span>
    <span class="macro-1y">{change_1y_str}</span>
  </div>
</div>""")
    return f'<div class="macro-bar">{"".join(cells)}</div>'


def _empty_card_html(company: str) -> str:
    """보고서 아직 없는 종목용 placeholder 카드."""
    return f"""
<div class="report-card report-card-empty">
  <span class="badge badge-empty">추적 중</span>
  <h3>{escape(company)}</h3>
  <p class="desc">첫 정기공시 도착 시 자동 진단 시작.</p>
  <div class="meta">
    <span>—</span>
    <span style="opacity:0.5">대기</span>
  </div>
</div>"""


def _company_card_html(company: str, entries: list[ReportEntry]) -> str:
    """마스터 카드 — 회사 인덱스(보고서 목록)로 이동.

    개별 보고서는 회사 인덱스에서 선택해서 들어감 (정렬·필터 가능한 단계).
    """
    latest = sorted(entries, key=lambda x: x.period, reverse=True)[0]
    friendly = _period_to_friendly(latest.period)
    href = f"{company}/index.html"
    sub_count = len(entries)
    count_label = f"{sub_count}건 누적" if sub_count > 1 else "1건"
    return f"""
<a href="{escape(href)}" style="text-decoration:none;color:inherit;">
  <div class="report-card">
    <span class="badge">{escape(latest.period)} · {escape(friendly)}</span>
    <h3>{escape(company)}</h3>
    <p class="desc">{escape(latest.summary)}</p>
    <div class="meta">
      <span>최신 {escape(latest.written_at)}</span>
      <span>→ {count_label} 모두 보기</span>
    </div>
  </div>
</a>"""


def render_master_index(
    out_html_path: Path,
    companies: dict[str, list[ReportEntry]],
    watchlist: list[WatchlistEntry] | None = None,
    daily_count: int = 0,
) -> None:
    """마스터 인덱스 — dashboard 표 레이아웃, 섹터 필터 포함.

    24종목 전부 한 페이지에 압축 표시. 카드 그리드보다 훨씬 짧음.
    daily_count > 0이면 상단에 "일간 메모" 카드 노출.
    """
    if watchlist is None:
        watchlist = []
        for company, entries in sorted(companies.items()):
            watchlist.append(
                WatchlistEntry(
                    name=company, ticker="", corp_code=None,
                    sector="기타", note="",
                )
            )

    from collections import OrderedDict
    sector_groups: OrderedDict[str, list[WatchlistEntry]] = OrderedDict()
    for w in watchlist:
        sector_groups.setdefault(w.sector, []).append(w)

    n_total = len(watchlist)
    n_with_reports = sum(1 for w in watchlist if w.name in companies)
    n_total_reports = sum(len(v) for v in companies.values())

    # 섹터 필터 pills (sticky)
    pills_html = ['<button class="filter-pill active" data-sector="all" onclick="window.kerFilter(\'all\')">전체 <span class="pill-count">{0}</span></button>'.format(n_total)]
    for sector, sector_entries in sector_groups.items():
        count = len(sector_entries)
        with_reports = sum(1 for w in sector_entries if w.name in companies)
        active_marker = ''
        pills_html.append(
            f'<button class="filter-pill" data-sector="{escape(sector)}" '
            f'onclick="window.kerFilter(\'{escape(sector)}\')">'
            f'{escape(sector)} <span class="pill-count">{with_reports}/{count}</span></button>'
        )

    # Compact dashboard 표
    # 24종목 ticker_market 캐시 읽기 (없으면 빈 dict)
    ticker_data: dict[str, dict] = {}
    cache_dir = Path("/home/soccz/22tb/report/pipeline/cache")
    if cache_dir.exists():
        import json as _json
        for w in watchlist:
            if not w.ticker:
                continue
            cache_path = cache_dir / f"ticker_market_{w.ticker}.json"
            if cache_path.exists():
                try:
                    ticker_data[w.ticker] = _json.loads(cache_path.read_text(encoding="utf-8"))
                except Exception:
                    pass

    # 시총 bar 정규화용 (24종목 중 최대 시총 기준)
    max_market_cap = max(
        (
            d.get("market_cap_trillion_krw") or 0
            for d in ticker_data.values()
        ),
        default=1.0,
    ) or 1.0

    def _spark_cell(d: dict | None) -> str:
        """60일 종가 → 60x20 SVG polyline. 등락률에 따라 색."""
        if not d or not d.get("closes_60d"):
            return '<td class="spark"></td>'
        closes = d["closes_60d"]
        if len(closes) < 2:
            return '<td class="spark"></td>'
        mn, mx = min(closes), max(closes)
        rng = mx - mn if mx > mn else 1.0
        n = len(closes)
        W, H = 80, 22
        pts = " ".join(
            f"{i / (n - 1) * W:.1f},{H - (c - mn) / rng * H:.1f}"
            for i, c in enumerate(closes)
        )
        pct = d.get("close_60d_pct_change") or 0
        cls = "spark-up" if pct > 0.5 else "spark-down" if pct < -0.5 else "spark-flat"
        return (
            f'<td class="spark">'
            f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" class="{cls}">'
            f'<polyline points="{pts}" fill="none" stroke-width="1.3" '
            f'vector-effect="non-scaling-stroke"/></svg></td>'
        )

    def _change_cell(d: dict | None) -> str:
        if not d or d.get("close_60d_pct_change") is None:
            return '<td class="change">—</td>'
        pct = d["close_60d_pct_change"]
        if pct > 0.5:
            cls, sign = "change-up", "+"
        elif pct < -0.5:
            cls, sign = "change-down", ""
        else:
            cls, sign = "change-flat", ""
        return f'<td class="change {cls}">{sign}{pct:.1f}%</td>'

    def _market_cap_cell(d: dict | None) -> str:
        if not d or not d.get("market_cap_trillion_krw"):
            return '<td class="mcap">—</td>'
        mc = d["market_cap_trillion_krw"]
        bar_pct = min(mc / max_market_cap * 100, 100)
        return (
            f'<td class="mcap">'
            f'<span class="mcap-val">{mc:,.0f}조</span>'
            f'<span class="mcap-bar"><span class="mcap-fill" style="width:{bar_pct:.1f}%"></span></span>'
            f'</td>'
        )

    rows_html: list[str] = []
    for sector, sector_entries in sector_groups.items():
        # 섹터 헤더 행
        with_reports = sum(1 for w in sector_entries if w.name in companies)
        rows_html.append(
            f'<tr class="sector-header" data-sector="{escape(sector)}">'
            f'<td colspan="7">'
            f'<span class="sector-name">{escape(sector)}</span>'
            f'<span class="sector-stat">{with_reports}/{len(sector_entries)}</span>'
            f'</td></tr>'
        )
        for w in sector_entries:
            tdata = ticker_data.get(w.ticker)
            change_cell = _change_cell(tdata)
            spark_cell = _spark_cell(tdata)
            mcap_cell = _market_cap_cell(tdata)
            if w.name in companies:
                latest = sorted(companies[w.name], key=lambda x: x.period, reverse=True)[0]
                friendly = _period_to_friendly(latest.period)
                href = f"{w.name}/index.html"
                report_count = len(companies[w.name])
                report_label = f"{report_count}건" if report_count > 1 else "1건"
                rows_html.append(
                    f'<tr class="stock-row stock-active" data-sector="{escape(sector)}" '
                    f'onclick="location.href=\'{escape(href)}\'">'
                    f'<td class="status"><span class="dot dot-active"></span></td>'
                    f'<td class="name"><strong>{escape(w.name)}</strong>'
                    f'<span class="ticker">{escape(w.ticker) if w.ticker else ""}</span></td>'
                    f'{spark_cell}'
                    f'{change_cell}'
                    f'{mcap_cell}'
                    f'<td class="latest">{escape(friendly)} · {escape(latest.written_at)}</td>'
                    f'<td class="action">{report_label} →</td>'
                    f'</tr>'
                )
            else:
                rows_html.append(
                    f'<tr class="stock-row stock-empty" data-sector="{escape(sector)}">'
                    f'<td class="status"><span class="dot dot-empty"></span></td>'
                    f'<td class="name">{escape(w.name)}'
                    f'<span class="ticker">{escape(w.ticker) if w.ticker else ""}</span></td>'
                    f'{spark_cell}'
                    f'{change_cell}'
                    f'{mcap_cell}'
                    f'<td class="latest"><em class="empty-text">추적 중</em></td>'
                    f'<td class="action">대기</td>'
                    f'</tr>'
                )

    macro_snaps = load_macro_snapshot(MACRO_CACHE_PATH)
    macro_html = _render_macro_bar(macro_snaps)

    body = f"""
<div class="page-hero">
  <span class="doc-tag">Equity Research Pipeline</span>
  <h1>K_E_R — Korea Equity Reports</h1>
  <p class="subtitle">DART 기반 한국 상장사 종합 진단. 출처 엄격주의 + 추론 명시 + XBRL ground truth.</p>
  {macro_html}
  <div class="hero-stats">
    <div class="stat"><span class="stat-num">{n_total}</span><span class="stat-lbl">종목</span></div>
    <div class="stat"><span class="stat-num">{n_with_reports}</span><span class="stat-lbl">진단 완료</span></div>
    <div class="stat"><span class="stat-num">{n_total_reports}</span><span class="stat-lbl">누적 보고서</span></div>
    <div class="stat"><span class="stat-num">{len(sector_groups)}</span><span class="stat-lbl">섹터</span></div>
  </div>
  <div class="daily-link-banner"><a href="daily/"><span class="daily-banner-label">Observation log</span><span class="daily-banner-count{' has-notes' if daily_count > 0 else ''}">{daily_count}편</span><span class="daily-banner-meta">트리거 기반 일간 관찰 · 평일 16:00 KST 검사</span><span class="daily-banner-arrow">→</span></a></div>
</div>

<div class="filter-bar">
  <div class="filter-pills" id="filterPills">
    {''.join(pills_html)}
  </div>
</div>

<div class="watchlist-table">
<table id="watchlistTable">
  <thead>
    <tr>
      <th class="status">●</th>
      <th class="name">종목</th>
      <th class="spark">60d 추세</th>
      <th class="change">변화</th>
      <th class="mcap">시가총액</th>
      <th class="latest">최신 보고서</th>
      <th class="action"></th>
    </tr>
  </thead>
  <tbody>
    {''.join(rows_html)}
  </tbody>
</table>
</div>

<script>
  window.kerFilter = function(sector) {{
    document.querySelectorAll('.filter-pill').forEach(function(b) {{
      b.classList.toggle('active', b.dataset.sector === sector);
    }});
    document.querySelectorAll('#watchlistTable tr[data-sector]').forEach(function(tr) {{
      tr.style.display = (sector === 'all' || tr.dataset.sector === sector) ? '' : 'none';
    }});
  }};
</script>"""

    title = "K_E_R — Korea Equity Reports"
    description = (
        "DART 기반 한국 상장사 자동 진단. 워치리스트 24종목 + 일간 관찰. "
        "페르소나 owner mindset + 4단 검증 (V1·V2·V3·V4) + cross-section consistency."
    )
    out_html_path.parent.mkdir(parents=True, exist_ok=True)
    out_html_path.write_text(
        _wrap_html(title, body, description=description, canonical_path="", og_type="website"),
        encoding="utf-8",
    )


def discover_reports(companies_dir: Path) -> dict[str, list[ReportEntry]]:
    """companies/<기업명>/<period>/ 트리에서 합본(00) 또는 첫 섹션(01)만 찾기.

    *명시적 제외*: .v2_warnings.md, _meta.json, raw_inputs/, sections_*/
    site에 노출되는 건 *최종 deliverable*만.
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
            # 합본 우선, 없으면 첫 섹션. v2_warnings는 절대 picked up되지 않게.
            md_candidates = [
                period_dir / "00_종합진단.md",
                period_dir / "01_사업구조진단.md",
            ]
            md_path = next(
                (p for p in md_candidates if p.exists() and ".v2_warnings" not in p.name),
                None,
            )
            if md_path is None:
                continue

            md_text = md_path.read_text(encoding="utf-8")
            summary = _extract_one_liner(md_text)
            written_at = datetime.fromtimestamp(md_path.stat().st_mtime).strftime("%Y-%m-%d")
            html_rel = f"{period}/index.html"
            is_assembled = md_path.name.startswith("00_")
            title = (
                f"{company} {period} 종합진단" if is_assembled
                else f"{company} {period} (부분)"
            )
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


def _file_needs_rerender(src: Path, dst: Path) -> bool:
    """src(.md)가 dst(.html)보다 새로우면 rerender 필요."""
    if not dst.exists():
        return True
    return src.stat().st_mtime > dst.stat().st_mtime


def render_all(
    companies_dir: Path,
    site_root: Path,
    watchlist_path: Path | None = None,
    incremental: bool = True,
    daily_notes_dir: Path | None = None,
) -> tuple[int, int, int]:
    """전체 변환 — companies → site_root/projects/k-e-r/.

    incremental=True: MD가 HTML보다 새로운 것만 다시 렌더 (대량 보고서 시 빠름).
    워치리스트 path 주면 마스터 인덱스에 24종목 전부 표시 (placeholder 포함).
    daily_notes_dir 주면 site_root/daily/에 일간 메모도 함께 렌더.
    반환: (회사 수, 발견된 보고서 수, 실제 렌더된 수)
    """
    discovered = discover_reports(companies_dir)
    site_root.mkdir(parents=True, exist_ok=True)

    total_reports = 0
    rendered = 0
    for company, entries in discovered.items():
        company_html_dir = site_root / company
        for entry in entries:
            html_path = company_html_dir / entry.period / "index.html"
            total_reports += 1
            if incremental and not _file_needs_rerender(entry.md_path, html_path):
                continue
            render_report_to_html(
                md_path=entry.md_path,
                out_html_path=html_path,
                company=company,
                period=entry.period,
                written_at=entry.written_at,
            )
            rendered += 1
        # 회사 인덱스는 항상 다시 (정렬·count 변경 가능)
        company_index = company_html_dir / "index.html"
        render_company_index(company, company_html_dir, company_index, entries)

    watchlist: list[WatchlistEntry] | None = None
    if watchlist_path and watchlist_path.exists():
        watchlist = parse_watchlist(watchlist_path.read_text(encoding="utf-8"))

    # 일간 메모 렌더 (옵션)
    daily_count = 0
    if daily_notes_dir is not None and daily_notes_dir.exists():
        daily_count = render_all_daily_notes(daily_notes_dir, site_root, incremental=incremental)

    # 마스터 인덱스는 항상 다시 (워치리스트 placeholder + 일간 메모 카드 포함)
    master = site_root / "index.html"
    render_master_index(master, discovered, watchlist=watchlist, daily_count=daily_count)

    # 외부 CSS + sitemap + robots
    _write_static_assets(site_root)

    return len(discovered), total_reports, rendered


def _write_static_assets(site_root: Path) -> None:
    """외부 CSS, sitemap.xml, robots.txt 작성.

    CSS는 query string content-hash로 cache busting (변경 시 즉시 무효화).
    sitemap.xml은 site_root 안의 모든 .html을 lastmod와 함께 등록.
    robots.txt는 도메인 루트(soccz.github.io/)에만 의미가 있으므로,
    site_root의 부모(soccz.github.io)에 없을 때만 생성.
    """
    # 1) CSS
    assets_dir = site_root / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "k-e-r.css").write_text(_SHARED_CSS, encoding="utf-8")

    # 2) sitemap.xml
    urls: list[tuple[str, str]] = []
    for html in sorted(site_root.rglob("*.html")):
        rel = html.relative_to(site_root).as_posix()
        if rel.endswith("index.html"):
            url_path = rel[: -len("index.html")]
        else:
            url_path = rel
        loc = f"{SITE_BASE_URL}/{url_path}".rstrip("/") + ("/" if url_path.endswith("/") or url_path == "" else "")
        if not url_path:
            loc = SITE_BASE_URL + "/"
        lastmod = datetime.fromtimestamp(html.stat().st_mtime).strftime("%Y-%m-%d")
        urls.append((loc, lastmod))

    sitemap_xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap_xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for loc, lastmod in urls:
        sitemap_xml += f"  <url><loc>{escape(loc)}</loc><lastmod>{lastmod}</lastmod></url>\n"
    sitemap_xml += "</urlset>\n"
    (site_root / "sitemap.xml").write_text(sitemap_xml, encoding="utf-8")

    # 3) robots.txt — 도메인 루트에만 (soccz.github.io 루트 = site_root.parent.parent)
    domain_root = site_root.parent.parent
    robots_path = domain_root / "robots.txt"
    if domain_root.is_dir() and not robots_path.exists():
        robots_path.write_text(
            "User-agent: *\nAllow: /\n\n"
            f"Sitemap: {SITE_BASE_URL}/sitemap.xml\n",
            encoding="utf-8",
        )


# ════════════════════════════════════════════════════════════════════
# 일간 메모 렌더링 (Phase D)
# ════════════════════════════════════════════════════════════════════


def render_daily_note_to_html(
    md_path: Path,
    out_html_path: Path,
    fetch_date: str,
) -> None:
    """단일 일간 메모 MD → HTML.

    마크다운 안의 인라인 SVG는 그대로 통과 (markdown 라이브러리가 raw HTML 보존).
    """
    md_text = md_path.read_text(encoding="utf-8")
    body_html = _md_to_html(md_text)
    title = f"{fetch_date} 일간 메모 — K_E_R"
    breadcrumb = f"""
<div class="container" style="padding-top:24px; padding-bottom:0; font-size:12px; color:var(--text-muted); letter-spacing:0.04em;">
  <a href="../" style="color:var(--text-muted)">K_E_R</a>
  &nbsp;/&nbsp;
  <a href="./" style="color:var(--text-muted)">Daily Notes</a>
  &nbsp;/&nbsp;
  <span style="color:var(--text-secondary)">{fetch_date}</span>
</div>"""
    description = (
        f"K_E_R {fetch_date} 일간 관찰 노트 — 페르소나 + 학술 톤. "
        f"매수·매도 권고가 아닌 공개 관찰 기록."
    )
    full_html = _wrap_html(
        title,
        body_html,
        breadcrumb=breadcrumb,
        description=description,
        canonical_path=f"daily/{fetch_date}.html",
        og_type="article",
        published_time=f"{fetch_date}T16:00:00+09:00",
    )
    out_html_path.parent.mkdir(parents=True, exist_ok=True)
    out_html_path.write_text(full_html, encoding="utf-8")


def render_daily_index(
    daily_html_dir: Path,
    notes_md: list[Path],
) -> None:
    """일간 메모 시계열 인덱스 — 트리거 기반 관찰 일지 톤."""
    from datetime import datetime, timedelta

    notes_sorted = sorted(notes_md, key=lambda p: p.stem, reverse=True)
    items_html: list[str] = []
    for md in notes_sorted:
        date = md.stem
        text = md.read_text(encoding="utf-8")
        first_line = next(
            (
                ln.lstrip("# ").strip()
                for ln in text.splitlines()
                if ln.startswith("# ")
            ),
            date,
        )
        if "일간 메모" in first_line:
            parts = first_line.split("일간 메모", 1)
            headline = parts[1].strip() if len(parts) > 1 else ""
        else:
            headline = first_line
        # 본문에서 트리거 메타 추출 ('> **트리거**: ...')
        trigger_meta = ""
        for ln in text.splitlines():
            if ln.startswith("> **트리거**:"):
                trigger_meta = ln.replace("> **트리거**:", "").strip()
                break
        # 종목 카드 N개 추출 ('### ' 카운트)
        ticker_count = sum(1 for ln in text.splitlines() if ln.startswith("### "))
        items_html.append(
            f'<li class="dn-item">'
            f'<a href="{date}.html" class="dn-row">'
            f'<span class="dn-date">{date}</span>'
            f'<span class="dn-body">'
            f'<span class="dn-headline">{headline or "(no headline)"}</span>'
            + (f'<span class="dn-meta">{trigger_meta} · 종목 {ticker_count}</span>' if trigger_meta or ticker_count else '')
            + f'</span>'
            f'</a></li>'
        )

    # 다음 자동 실행 시점 — 평일(Mon..Fri) 16:00 KST. 토·일은 KRX 휴장 → skip.
    now = datetime.now()
    next_run = now.replace(hour=16, minute=0, second=0, microsecond=0)
    if now >= next_run:
        next_run += timedelta(days=1)
    while next_run.weekday() >= 5:  # 5=토, 6=일
        next_run += timedelta(days=1)
    weekday_kr = ["월", "화", "수", "목", "금", "토", "일"][next_run.weekday()]
    next_run_str = next_run.strftime("%Y-%m-%d") + f"({weekday_kr}) " + next_run.strftime("%H:%M KST")

    n_notes = len(notes_sorted)

    if n_notes == 0:
        body_inner = (
            '<div class="dn-empty-state">'
            '<p class="dn-empty-headline">아직 발행된 메모 없음.</p>'
            '<p class="dn-empty-meta">'
            f'다음 자동 검사 시점: <code>{next_run_str}</code>. '
            '워치리스트 24종목 + KOSPI200 동향에서 임계치 통과 시 자동 발행.'
            '</p>'
            '</div>'
        )
    else:
        body_inner = f'<ul class="dn-list">{"".join(items_html)}</ul>'

    body = f'''<div class="dn-page">
  <header class="dn-header">
    <div class="dn-header-meta">
      <span class="dn-tag">Observation log · trigger-based</span>
      <span class="dn-stat">{n_notes}편 · 다음 검사 {next_run_str}</span>
    </div>
    <h1 class="dn-title">Daily Notes</h1>
    <p class="dn-sub">
      DART 공시 / KRX 가격 / 외인 수급 / 외인-국내 디커플링 — 4종 임계치 검사 후
      통과 시 1면 관찰 메모. 매수·매도 권고 아님.
    </p>
  </header>

  <section class="dn-archive">
    {body_inner}
  </section>

  <section class="dn-method">
    <h2>운영 원칙</h2>
    <ul>
      <li><strong>트리거</strong> 가격 ±5% / 외인 ±500억 3일 / DART 주요 공시 / 디커플링</li>
      <li><strong>출처</strong> XBRL · DART OpenAPI · KRX OHLCV (1순위만)</li>
      <li><strong>금지</strong> 목표주가 · % 예측 · 양다리 결론</li>
      <li><strong>구조</strong> 매크로 · 관찰 · 종목 카드 1~3 · 섹터 톤</li>
    </ul>
    <p class="dn-method-meta">
      <a href="https://github.com/soccz/K_E_R/blob/main/_persona.md">페르소나</a> ·
      <a href="https://github.com/soccz/K_E_R/blob/main/_daily_note_spec.md">spec</a> ·
      <a href="https://github.com/soccz/K_E_R">K_E_R repo</a>
    </p>
  </section>
</div>'''

    breadcrumb = """
<div class="container" style="padding-top:24px; padding-bottom:0; font-size:12px; color:var(--text-muted); letter-spacing:0.04em;">
  <a href="../" style="color:var(--text-muted)">K_E_R</a>
  &nbsp;/&nbsp;
  <span style="color:var(--text-secondary)">Daily Notes</span>
</div>"""
    description = (
        "K_E_R 일간 관찰 노트 시계열. DART 공시·KRX 가격·외인 수급·디커플링 "
        "4종 임계치 통과 시 자동 발행. 매수·매도 권고 아님."
    )
    full = _wrap_html(
        "Daily Notes — K_E_R",
        body,
        breadcrumb=breadcrumb,
        description=description,
        canonical_path="daily/",
        og_type="website",
    )
    daily_html_dir.mkdir(parents=True, exist_ok=True)
    (daily_html_dir / "index.html").write_text(full, encoding="utf-8")


def render_all_daily_notes(
    daily_notes_dir: Path,
    site_root: Path,
    incremental: bool = True,
) -> int:
    """daily_notes/*.md → site_root/daily/*.html. 반환: 총 발행된 메모 수."""
    daily_html_dir = site_root / "daily"
    daily_html_dir.mkdir(parents=True, exist_ok=True)

    notes_md = sorted(daily_notes_dir.glob("*.md"))
    notes_md = [p for p in notes_md if p.stem != "_index"]  # _index는 제외

    # MD가 사라진 stale HTML 청소 (stub 삭제·이름 변경 시 잔재 방지).
    valid_dates = {md.stem for md in notes_md}
    for stale_html in daily_html_dir.glob("*.html"):
        if stale_html.name == "index.html":
            continue
        if stale_html.stem not in valid_dates:
            stale_html.unlink()

    for md in notes_md:
        date = md.stem
        html_path = daily_html_dir / f"{date}.html"
        if incremental and not _file_needs_rerender(md, html_path):
            continue
        render_daily_note_to_html(md, html_path, fetch_date=date)

    render_daily_index(daily_html_dir, notes_md)
    return len(notes_md)
