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
  /* sell-side equity research report — sophisticated, archival */
  --bg: #f6f7f9;
  --surface: #ffffff;
  --surface-alt: #fafbfc;
  --surface-hover: #f1f3f7;
  --paper: #fcfcfd;
  --border: #dde2ea;
  --border-light: #eaedf2;
  --border-strong: #b8c0cc;
  --text: #0a0e1a;
  --text-secondary: #2c3445;
  --text-muted: #6b7387;
  --text-light: #9aa1b1;
  --accent: #14213d;
  --accent-light: #eef1f7;
  --accent-hover: #0a1228;
  --accent-soft: #5d6d8c;
  --rule: #1a2238;
  --positive: #1f6f4a;
  --positive-light: #ecf7f1;
  --negative: #9a3434;
  --negative-light: #faeded;
  --warn: #8a6109;
  --warn-light: #faf3df;
  --tag-bg: #eef0f4;
  --tag-text: #404a5c;
  --max-w: 1180px;
  --content-w: 760px;
  --sidebar-w: 240px;
  --radius-sm: 3px;
  --radius-md: 4px;
  --radius-lg: 6px;
  --shadow-sm: 0 1px 2px rgba(10,14,26,0.04);
  --shadow-md: 0 2px 8px rgba(10,14,26,0.06);
  --shadow-lg: 0 12px 28px rgba(10,14,26,0.08);
  --serif: 'Source Serif 4', 'IBM Plex Serif', Georgia, serif;
  --sans: 'Inter', 'Noto Sans KR', -apple-system, sans-serif;
  --display: 'IBM Plex Sans', 'Inter', sans-serif;
  --mono: 'IBM Plex Mono', 'JetBrains Mono', Menlo, monospace;
}
html { scroll-behavior: smooth; }
body {
  font-family: var(--sans);
  background: var(--bg);
  color: var(--text);
  line-height: 1.7;
  padding-bottom: 80px;
  -webkit-font-smoothing: antialiased;
  font-feature-settings: 'cv11','ss01','calt';
  background-image:
    linear-gradient(to bottom, transparent 0, transparent 24px, rgba(20,33,61,0.015) 24px, rgba(20,33,61,0.015) 25px, transparent 25px),
    linear-gradient(to right, transparent 0, transparent 240px, rgba(20,33,61,0.015) 240px, rgba(20,33,61,0.015) 241px, transparent 241px);
  background-size: 100% 25px, 240px 100%;
}
::selection { background: var(--accent); color: #fff; }
a { color: var(--accent); text-decoration: none; transition: color 0.15s; }
a:hover { color: var(--accent-hover); text-decoration: underline; text-underline-offset: 2px; }

/* 상단 — 미니멀, 신문 매스트헤드 톤 */
.site-header {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  border-top: 3px solid var(--rule);
  position: sticky; top: 0; z-index: 100;
}
.site-header .inner {
  max-width: var(--max-w); margin: 0 auto;
  padding: 16px 32px;
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
}
.site-header .brand {
  font-family: var(--display);
  font-weight: 700; font-size: 17px; letter-spacing: -0.02em;
  display: flex; align-items: center; gap: 12px;
  color: var(--text);
}
.site-header .brand .divider {
  width: 1px; height: 18px; background: var(--border-strong);
}
.site-header .brand .badge {
  background: transparent; color: var(--text-muted);
  padding: 0; font-size: 11px; font-weight: 500;
  letter-spacing: 0.12em; text-transform: uppercase;
}
.site-header nav a {
  color: var(--text-secondary); margin-left: 22px; font-size: 13px;
  font-weight: 500;
}
.site-header nav a:hover { color: var(--accent); text-decoration: none; }

.container { max-width: var(--max-w); margin: 0 auto; padding: 36px 32px; }

/* HERO — 보고서 표지 (cover page 톤) */
.page-hero {
  margin: 0 0 40px;
  padding: 44px 48px;
  background: var(--paper);
  border: 1px solid var(--border);
  position: relative;
  box-shadow: var(--shadow-sm);
}
.page-hero::before {
  content: ''; position: absolute;
  top: 0; left: 0; right: 0; height: 4px;
  background: var(--rule);
}
.page-hero::after {
  content: ''; position: absolute;
  top: 4px; left: 0; right: 0; height: 1px;
  background: var(--accent-soft);
}
.page-hero .doc-tag {
  display: inline-block;
  color: var(--text-muted);
  padding: 0; margin-bottom: 18px;
  font-size: 11px; font-weight: 600; letter-spacing: 0.18em;
  text-transform: uppercase;
  border-bottom: 1px solid var(--border-strong);
  padding-bottom: 6px;
}
.page-hero h1 {
  font-family: var(--display);
  font-size: 34px; font-weight: 700; line-height: 1.18;
  margin-bottom: 10px; letter-spacing: -0.025em;
  color: var(--text);
}
.page-hero h1 .secondary {
  color: var(--text-muted); font-weight: 400;
}
.page-hero .subtitle {
  color: var(--text-secondary); font-size: 15px;
  font-family: var(--serif); font-style: italic;
  margin-top: 8px;
}
.page-hero .meta {
  display: flex; gap: 32px; flex-wrap: wrap;
  margin-top: 28px; padding-top: 18px;
  border-top: 1px solid var(--border);
  font-size: 13px;
}
.page-hero .meta .item {
  display: inline-flex; flex-direction: column; gap: 2px;
}
.page-hero .meta .item .label {
  color: var(--text-light); font-size: 10px;
  text-transform: uppercase; letter-spacing: 0.1em;
  font-weight: 500;
}
.page-hero .meta .item .value {
  color: var(--text-secondary); font-weight: 500;
}

/* REPORT LAYOUT — 본문 + 사이드 TOC */
.report-layout {
  display: grid;
  grid-template-columns: 1fr var(--sidebar-w);
  gap: 40px;
  align-items: start;
}
.report-toc {
  position: sticky; top: 80px;
  padding: 24px 0;
  font-size: 13px;
  max-height: calc(100vh - 100px);
  overflow-y: auto;
}
.report-toc .toc-title {
  font-family: var(--display);
  font-weight: 600; font-size: 11px;
  letter-spacing: 0.14em; text-transform: uppercase;
  color: var(--text-muted);
  margin-bottom: 14px; padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}
.report-toc ul { list-style: none; padding: 0; margin: 0; }
.report-toc ul ul { padding-left: 14px; margin: 4px 0; border-left: 1px solid var(--border-light); }
.report-toc li { margin: 4px 0; }
.report-toc a {
  color: var(--text-secondary);
  display: block; padding: 4px 8px;
  border-radius: var(--radius-sm);
  font-weight: 500;
  border-left: 2px solid transparent;
  margin-left: -10px;
  transition: all 0.12s;
}
.report-toc a:hover {
  color: var(--accent); background: var(--surface-alt);
  border-left-color: var(--accent-soft);
  text-decoration: none;
}
.report-toc ul ul a { font-weight: 400; font-size: 12px; color: var(--text-muted); padding: 3px 8px; }

@media (max-width: 980px) {
  .report-layout { grid-template-columns: 1fr; }
  .report-toc { display: none; }
}

/* ARTICLE — 본문 (paper-like) */
article.report {
  background: var(--paper);
  border: 1px solid var(--border);
  padding: 56px 64px;
  box-shadow: var(--shadow-sm);
  max-width: var(--content-w);
  position: relative;
}
article.report::before {
  content: ''; position: absolute;
  top: 0; left: 56px; right: 56px; height: 1px;
  background: var(--rule); opacity: 0.6;
}
article.report > h1:first-child,
article.report > h2:first-child { margin-top: 0; }

article.report h1 {
  font-family: var(--display);
  font-size: 26px; font-weight: 700; letter-spacing: -0.02em;
  margin: 40px 0 16px;
  padding-bottom: 14px;
  border-bottom: 2px solid var(--rule);
  color: var(--text);
}
article.report h2 {
  font-family: var(--display);
  font-size: 19px; font-weight: 700; letter-spacing: -0.012em;
  margin: 44px 0 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
  color: var(--text);
  counter-increment: section;
  position: relative;
}
article.report h2::before {
  content: counter(section, decimal-leading-zero);
  font-family: var(--mono); font-weight: 500;
  font-size: 11px; color: var(--text-muted);
  letter-spacing: 0.05em;
  position: absolute; left: -36px; top: 8px;
}
article.report {
  counter-reset: section;
}
article.report h3 {
  font-size: 16px; font-weight: 600;
  margin: 30px 0 10px;
  color: var(--text);
  letter-spacing: -0.005em;
}
article.report h4 {
  font-size: 12px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.1em; color: var(--text-muted);
  margin: 26px 0 10px;
}

article.report p { margin: 14px 0; font-size: 15px; }
article.report p strong { color: var(--text); }
article.report ul, article.report ol { margin: 14px 0 14px 24px; font-size: 15px; }
article.report li { margin: 5px 0; }
article.report li::marker { color: var(--text-muted); }

/* 인용·박스 — 데이터 기준시점 등 */
article.report blockquote {
  border-left: 2px solid var(--rule);
  background: var(--surface-alt);
  padding: 16px 22px;
  margin: 22px 0;
  font-size: 13px;
  color: var(--text-secondary);
  font-family: var(--mono);
  line-height: 1.6;
}
article.report blockquote strong {
  color: var(--text); font-family: var(--display);
  text-transform: uppercase; letter-spacing: 0.06em;
  font-size: 11px; font-weight: 700;
}
article.report blockquote p { margin: 4px 0; }
article.report blockquote ul { margin: 6px 0 0 18px; }
article.report blockquote ul li { font-size: 12px; }

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

/* 표 — 재무 데이터 보고서 스타일 */
article.report table {
  width: 100%; border-collapse: collapse; margin: 22px 0;
  background: var(--surface);
  border-top: 2px solid var(--rule);
  border-bottom: 2px solid var(--rule);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}
article.report table th, article.report table td {
  padding: 8px 12px; text-align: left;
  border-bottom: 1px solid var(--border-light);
}
article.report table th {
  font-weight: 700; color: var(--text);
  border-bottom: 1px solid var(--border-strong);
  font-size: 11px; letter-spacing: 0.05em;
  text-transform: uppercase;
  font-family: var(--display);
}
article.report table td:not(:first-child),
article.report table th:not(:first-child) {
  text-align: right; font-feature-settings: 'tnum';
}
article.report table tr:last-child td { border-bottom: none; }
article.report table tr:hover { background: var(--surface-alt); }
article.report table strong { color: var(--text); }
article.report table tr:has(td strong),
article.report table tr:has(td:first-child strong) {
  background: var(--surface-alt);
  border-top: 1px solid var(--border-strong);
}

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

/* 추적 중 (보고서 미생성) 카드 — placeholder */
.report-card.report-card-empty {
  background: var(--surface-alt);
  border-style: dashed;
  opacity: 0.85;
}
.report-card.report-card-empty:hover {
  transform: none; box-shadow: var(--shadow-sm);
  border-color: var(--border);
}
.badge.badge-empty {
  background: var(--tag-bg); color: var(--text-muted);
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

/* SCROLL-TO-TOP 버튼 */
.scroll-top {
  position: fixed;
  right: 24px; bottom: 24px;
  width: 44px; height: 44px;
  border-radius: 50%;
  background: var(--accent); color: #fff;
  border: none; cursor: pointer;
  font-size: 22px; line-height: 1;
  box-shadow: var(--shadow-md);
  opacity: 0; transform: translateY(8px);
  pointer-events: none;
  transition: opacity 0.2s, transform 0.2s;
  z-index: 90;
}
.scroll-top.visible { opacity: 0.92; transform: translateY(0); pointer-events: auto; }
.scroll-top:hover { opacity: 1; }

/* TOC FAB (모바일·작은 화면에서 떠있는 목차 버튼) */
.toc-fab {
  display: none;
  position: fixed; right: 24px; bottom: 80px;
  width: 44px; height: 44px;
  border-radius: 50%;
  background: var(--surface); color: var(--accent);
  border: 1px solid var(--border-strong);
  cursor: pointer;
  align-items: center; justify-content: center;
  box-shadow: var(--shadow-md);
  z-index: 90;
}
.toc-fab:hover { background: var(--accent-light); }

.toc-drawer {
  display: none;
  position: fixed; inset: 0;
  background: rgba(10,14,26,0.4);
  z-index: 110;
  align-items: stretch; justify-content: flex-end;
}
.toc-drawer.open { display: flex; }
.toc-drawer-inner {
  width: min(320px, 88vw);
  background: var(--surface);
  border-left: 1px solid var(--border);
  padding: 20px 22px 80px;
  overflow-y: auto;
}
.toc-drawer-head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 14px; padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}
.toc-drawer-head .toc-title {
  font-family: var(--display);
  font-size: 12px; font-weight: 700;
  letter-spacing: 0.14em; text-transform: uppercase;
  color: var(--text-muted);
}
.toc-close {
  width: 32px; height: 32px; border: none;
  background: transparent; cursor: pointer;
  font-size: 22px; color: var(--text-muted);
  border-radius: var(--radius-sm);
}
.toc-close:hover { background: var(--surface-alt); color: var(--text); }
.toc-drawer ul { list-style: none; padding: 0; margin: 0; }
.toc-drawer ul ul { padding-left: 14px; margin: 4px 0; border-left: 1px solid var(--border-light); }
.toc-drawer li { margin: 6px 0; }
.toc-drawer a {
  display: block; padding: 8px 10px;
  color: var(--text-secondary); font-size: 14px;
  font-weight: 500; border-radius: var(--radius-sm);
  text-decoration: none;
}
.toc-drawer a:hover { background: var(--surface-alt); color: var(--accent); }
.toc-drawer ul ul a { font-size: 13px; font-weight: 400; color: var(--text-muted); }

/* anchor scroll offset (sticky header 고려) */
article.report h2, article.report h3 { scroll-margin-top: 80px; }

/* 모바일 — 980px 이하 (TOC FAB 등장, sidebar 숨김) */
@media (max-width: 980px) {
  .report-layout { grid-template-columns: 1fr; }
  .report-toc { display: none; }
  .toc-fab { display: inline-flex; }
}

/* 모바일 — 720px 이하 */
@media (max-width: 720px) {
  .container { padding: 24px 16px; }
  .site-header .inner { padding: 14px 16px; }
  .site-header .brand { font-size: 15px; gap: 8px; }
  .site-header .brand .badge { display: none; }
  .site-header .brand .divider { display: none; }
  .site-header nav a { margin-left: 0; }
  article.report { padding: 28px 22px; }
  article.report h1 { font-size: 22px; }
  article.report h2 { font-size: 17px; padding-bottom: 6px; }
  article.report h2::before { display: none; }
  article.report table { font-size: 12px; }
  article.report table th, article.report table td { padding: 7px 10px; }
  .page-hero { padding: 28px 22px; }
  .page-hero h1 { font-size: 24px; }
  .page-hero .meta { gap: 16px; }
  .scroll-top, .toc-fab { right: 14px; }
  .scroll-top { bottom: 14px; }
  .toc-fab { bottom: 70px; }
  .report-card { padding: 16px 18px; }
}

/* 카드 그리드도 모바일 대응 */
@media (max-width: 480px) {
  .report-grid { grid-template-columns: 1fr; gap: 12px; }
}

/* 회사 인덱스 정렬 토글 */
.list-controls {
  display: flex; align-items: center; gap: 16px;
  margin: 24px 0 16px; padding: 12px 0;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}
.list-controls-label {
  color: var(--text-muted);
  font-family: var(--display);
  text-transform: uppercase; letter-spacing: 0.08em;
  font-size: 11px; font-weight: 600;
}
.list-controls-count {
  margin-left: auto;
  color: var(--text-muted);
  font-family: var(--mono); font-size: 12px;
}
.sort-toggle {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--surface);
}
.sort-btn {
  padding: 7px 16px;
  border: none; background: transparent;
  color: var(--text-muted); cursor: pointer;
  font-size: 13px; font-weight: 500;
  font-family: var(--sans);
  transition: background 0.15s, color 0.15s;
}
.sort-btn + .sort-btn { border-left: 1px solid var(--border); }
.sort-btn:hover { background: var(--surface-alt); color: var(--text); }
.sort-btn.active {
  background: var(--accent); color: #fff;
}
.report-card-link {
  text-decoration: none; color: inherit;
  display: block;
}

/* ─────── 마스터 인덱스 — Dashboard 표 레이아웃 ─────── */

/* Hero stats — 4구획 숫자 */
.hero-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0;
  margin-top: 28px; padding-top: 22px;
  border-top: 1px solid var(--border);
}
.hero-stats .stat {
  display: flex; flex-direction: column; gap: 4px;
  padding: 0 16px;
  border-right: 1px solid var(--border-light);
}
.hero-stats .stat:last-child { border-right: none; }
.hero-stats .stat:first-child { padding-left: 0; }
.hero-stats .stat-num {
  font-family: var(--display);
  font-size: 28px; font-weight: 700;
  letter-spacing: -0.02em; color: var(--text);
  font-feature-settings: 'tnum';
}
.hero-stats .stat-lbl {
  font-size: 11px; color: var(--text-muted);
  text-transform: uppercase; letter-spacing: 0.08em;
  font-weight: 500;
}

/* 섹터 필터 pills (sticky 가까이) */
.filter-bar {
  margin: 28px 0 16px;
  padding: 14px 0;
  border-top: 1px solid var(--border-light);
  border-bottom: 1px solid var(--border-light);
}
.filter-pills {
  display: flex; flex-wrap: wrap;
  gap: 6px;
  overflow-x: auto;
  padding: 2px 0;
}
.filter-pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px;
  background: var(--surface); color: var(--text-secondary);
  border: 1px solid var(--border);
  border-radius: 99px;
  font-size: 12.5px; font-weight: 500;
  cursor: pointer; white-space: nowrap;
  font-family: var(--sans);
  transition: background 0.12s, color 0.12s, border-color 0.12s;
}
.filter-pill:hover {
  border-color: var(--border-strong);
  background: var(--surface-alt);
}
.filter-pill.active {
  background: var(--accent); color: #fff;
  border-color: var(--accent);
}
.filter-pill .pill-count {
  font-family: var(--mono); font-size: 11px;
  opacity: 0.75; font-weight: 500;
}
.filter-pill.active .pill-count { opacity: 0.85; }

/* Watchlist 표 */
.watchlist-table {
  background: var(--surface);
  border-top: 2px solid var(--rule);
  border-bottom: 2px solid var(--rule);
  overflow-x: auto;
}
.watchlist-table table {
  width: 100%; border-collapse: collapse;
  font-size: 14px; font-variant-numeric: tabular-nums;
}
.watchlist-table thead th {
  padding: 10px 14px;
  text-align: left;
  font-family: var(--display);
  font-size: 10px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.1em;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border-strong);
  background: var(--surface-alt);
}
.watchlist-table thead th.status { width: 32px; text-align: center; }
.watchlist-table thead th.date,
.watchlist-table thead th.action { text-align: right; }
.watchlist-table thead th.action { width: 100px; }

/* 섹터 헤더 행 */
tr.sector-header td {
  padding: 18px 14px 8px;
  border-bottom: 1px solid var(--border);
  background: var(--bg);
}
tr.sector-header .sector-name {
  font-family: var(--display);
  font-size: 13px; font-weight: 700;
  color: var(--text); letter-spacing: -0.005em;
}
tr.sector-header .sector-stat {
  margin-left: 10px;
  font-family: var(--mono); font-size: 11px;
  color: var(--text-muted); font-weight: 500;
}

/* 종목 행 */
tr.stock-row td {
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-light);
  vertical-align: middle;
}
tr.stock-row.stock-active {
  cursor: pointer;
  transition: background 0.1s;
}
tr.stock-row.stock-active:hover {
  background: var(--accent-light);
}
tr.stock-row.stock-empty {
  opacity: 0.7;
}
tr.stock-row td.status { width: 32px; text-align: center; }
tr.stock-row td.name { font-weight: 500; color: var(--text); }
tr.stock-row td.name .ticker {
  margin-left: 8px;
  font-family: var(--mono); font-size: 11px;
  color: var(--text-muted); font-weight: 400;
}
tr.stock-row td.latest {
  color: var(--text-secondary);
  font-size: 13px;
}
tr.stock-row td.latest .empty-text {
  color: var(--text-light); font-style: italic; font-size: 12.5px;
}
tr.stock-row td.date {
  text-align: right;
  font-family: var(--mono); font-size: 12px;
  color: var(--text-muted); white-space: nowrap;
}
tr.stock-row td.action {
  text-align: right;
  font-size: 12px; color: var(--text-muted);
  font-weight: 500;
  white-space: nowrap;
}
tr.stock-row.stock-active td.action {
  color: var(--accent);
}

/* 상태 dot */
.dot {
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
}
.dot-active { background: var(--accent); }
.dot-empty {
  border: 1.5px solid var(--text-light);
  background: transparent;
  width: 7px; height: 7px;
}

/* 모바일 — 표 padding 축소 + 일부 칼럼 숨김 */
@media (max-width: 720px) {
  .hero-stats { grid-template-columns: repeat(2, 1fr); gap: 18px 0; }
  .hero-stats .stat { padding: 0 12px; }
  .hero-stats .stat-num { font-size: 22px; }
  .filter-pills { gap: 5px; }
  .filter-pill { padding: 5px 10px; font-size: 12px; }
  .watchlist-table table { font-size: 12.5px; }
  .watchlist-table thead th, tr.stock-row td { padding: 8px 10px; }
  tr.stock-row td.date { display: none; }
  tr.sector-header td { padding: 14px 10px 6px; }
}
"""


def _wrap_html(title: str, body: str, breadcrumb: str = "", description: str = "") -> str:
    desc = description or "DART 기반 한국 상장사 종합 진단. 출처 검증 + 추론 명시 + XBRL ground truth."
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
  <meta property="og:type" content="article">
  <meta property="og:site_name" content="K_E_R — Korea Equity Reports">
  <meta property="og:image" content="https://soccz.github.io/assets/og-image.svg">
  <meta name="twitter:card" content="summary_large_image">
  <link rel="canonical" href="">
  <link rel="icon" type="image/svg+xml" href="/assets/favicon.svg">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&family=Inter:wght@400;500;600;700&family=Noto+Sans+KR:wght@400;500;600;700&family=Source+Serif+4:ital,wght@0,400;0,600;1,400&display=swap" rel="stylesheet">
  <style>{_SHARED_CSS}</style>
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
) -> None:
    """마스터 인덱스 — dashboard 표 레이아웃, 섹터 필터 포함.

    24종목 전부 한 페이지에 압축 표시. 카드 그리드보다 훨씬 짧음.
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
    rows_html: list[str] = []
    for sector, sector_entries in sector_groups.items():
        # 섹터 헤더 행
        with_reports = sum(1 for w in sector_entries if w.name in companies)
        rows_html.append(
            f'<tr class="sector-header" data-sector="{escape(sector)}">'
            f'<td colspan="5">'
            f'<span class="sector-name">{escape(sector)}</span>'
            f'<span class="sector-stat">{with_reports}/{len(sector_entries)}</span>'
            f'</td></tr>'
        )
        for w in sector_entries:
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
                    f'<td class="latest">{escape(friendly)}</td>'
                    f'<td class="date">{escape(latest.written_at)}</td>'
                    f'<td class="action">{report_label} →</td>'
                    f'</tr>'
                )
            else:
                rows_html.append(
                    f'<tr class="stock-row stock-empty" data-sector="{escape(sector)}">'
                    f'<td class="status"><span class="dot dot-empty"></span></td>'
                    f'<td class="name">{escape(w.name)}'
                    f'<span class="ticker">{escape(w.ticker) if w.ticker else ""}</span></td>'
                    f'<td class="latest" colspan="2"><em class="empty-text">추적 중 — 첫 정기공시 도착 시 자동</em></td>'
                    f'<td class="action">대기</td>'
                    f'</tr>'
                )

    body = f"""
<div class="page-hero">
  <span class="doc-tag">Equity Research Pipeline</span>
  <h1>K_E_R — Korea Equity Reports</h1>
  <p class="subtitle">DART 기반 한국 상장사 종합 진단. 출처 엄격주의 + 추론 명시 + XBRL ground truth.</p>
  <div class="hero-stats">
    <div class="stat"><span class="stat-num">{n_total}</span><span class="stat-lbl">종목</span></div>
    <div class="stat"><span class="stat-num">{n_with_reports}</span><span class="stat-lbl">진단 완료</span></div>
    <div class="stat"><span class="stat-num">{n_total_reports}</span><span class="stat-lbl">누적 보고서</span></div>
    <div class="stat"><span class="stat-num">{len(sector_groups)}</span><span class="stat-lbl">섹터</span></div>
  </div>
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
      <th class="latest">최신 보고서</th>
      <th class="date">작성일</th>
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
    out_html_path.parent.mkdir(parents=True, exist_ok=True)
    out_html_path.write_text(_wrap_html(title, body), encoding="utf-8")


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
) -> tuple[int, int, int]:
    """전체 변환 — companies → site_root/projects/k-e-r/.

    incremental=True: MD가 HTML보다 새로운 것만 다시 렌더 (대량 보고서 시 빠름).
    워치리스트 path 주면 마스터 인덱스에 24종목 전부 표시 (placeholder 포함).
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

    # 마스터 인덱스는 항상 다시 (워치리스트 placeholder 포함)
    master = site_root / "index.html"
    render_master_index(master, discovered, watchlist=watchlist)
    return len(discovered), total_reports, rendered
