"""K_E_R 사이트 CSS — site_renderer.py에서 분리 (Phase G).

CRITICAL_CSS: above-the-fold (header·container·typography·테마 토큰).
페이지마다 인라인 → FOUC 방지.

SHARED_CSS: 전체 (CRITICAL_CSS 포함).
외부 /assets/k-e-r.css로 비차단 로드 (preload + media trick).
"""

# Above-the-fold만 — 페이지마다 인라인 (~5KB).
# FCP 직전에 적용되어 폰트·색·헤더가 깜빡이지 않음.
CRITICAL_CSS = """
*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
:root {
  --bg: #f6f7f9; --surface: #ffffff; --paper: #fcfcfd;
  --border: #dde2ea; --border-strong: #b8c0cc;
  --text: #0a0e1a; --text-secondary: #2c3445; --text-muted: #6b7387;
  --accent: #14213d; --accent-hover: #0a1228;
  --rule: #1a2238;
  --max-w: 1280px;
  --radius-sm: 3px;
  --serif: 'Source Serif 4', 'IBM Plex Serif', Georgia, serif;
  --sans: 'Inter', 'Noto Sans KR', -apple-system, sans-serif;
  --display: 'IBM Plex Sans', 'Inter', sans-serif;
  --mono: 'IBM Plex Mono', 'JetBrains Mono', Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0d1117; --surface: #161b22; --paper: #161b22;
    --border: #2a313c; --border-strong: #3a4250;
    --text: #e6edf3; --text-secondary: #b3c0cf; --text-muted: #8b949e;
    --accent: #58a6ff; --accent-hover: #79b8ff; --rule: #58a6ff;
  }
}
:root[data-theme="dark"] {
  --bg: #0d1117; --surface: #161b22; --paper: #161b22;
  --border: #2a313c; --border-strong: #3a4250;
  --text: #e6edf3; --text-secondary: #b3c0cf; --text-muted: #8b949e;
  --accent: #58a6ff; --accent-hover: #79b8ff; --rule: #58a6ff;
}
html { scroll-behavior: smooth; }
body {
  font-family: var(--sans); background: var(--bg); color: var(--text);
  line-height: 1.7; padding-bottom: 80px;
  -webkit-font-smoothing: antialiased;
  transition: background-color 200ms, color 200ms;
}
::selection { background: var(--accent); color: #fff; }
a { color: var(--accent); text-decoration: none; transition: color 0.15s; }
a:hover { color: var(--accent-hover); text-decoration: underline; text-underline-offset: 2px; }
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
  font-family: var(--display); font-weight: 700; font-size: 17px;
  letter-spacing: -0.02em;
  display: flex; align-items: center; gap: 12px; color: var(--text);
}
.site-header .brand .divider { width: 1px; height: 18px; background: var(--border-strong); }
.site-header .brand .badge {
  background: transparent; color: var(--text-muted);
  font-size: 11px; font-weight: 500; letter-spacing: 0.12em;
  text-transform: uppercase;
}
.site-header nav a {
  color: var(--text-secondary); margin-left: 22px;
  font-size: 13px; font-weight: 500;
}
.theme-toggle {
  background: transparent; border: 1px solid var(--border);
  width: 32px; height: 32px;
  display: inline-flex; align-items: center; justify-content: center;
  cursor: pointer; color: var(--text-secondary);
  font-size: 14px; line-height: 1; border-radius: var(--radius-sm);
}
.container { max-width: var(--max-w); margin: 0 auto; padding: 36px 32px; }
"""

SHARED_CSS = """
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
  /* 한국식 등락률 색 (KRX/네이버금융 표준): + 빨강 / - 파랑 */
  --kr-up: #c63a2f;
  --kr-up-light: #fdecea;
  --kr-down: #1465c0;
  --kr-down-light: #e7f0fa;
  --kr-flat: #6b7387;
  --max-w: 1280px;
  --content-w: 900px;
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

/* 다크모드 — prefers-color-scheme + manual override (data-theme="dark") */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0d1117;
    --surface: #161b22;
    --surface-alt: #1c222b;
    --surface-hover: #21262e;
    --paper: #161b22;
    --border: #2a313c;
    --border-light: #21262e;
    --border-strong: #3a4250;
    --text: #e6edf3;
    --text-secondary: #b3c0cf;
    --text-muted: #8b949e;
    --text-light: #6e7681;
    --accent: #58a6ff;
    --accent-light: #1f2a3a;
    --accent-hover: #79b8ff;
    --accent-soft: #4f6680;
    --rule: #58a6ff;
    --positive: #56d364;
    --positive-light: #133c1d;
    --negative: #f85149;
    --negative-light: #3a1212;
    --warn: #d29922;
    --warn-light: #3a2c0a;
    --tag-bg: #21262e;
    --tag-text: #b3c0cf;
    --kr-up: #ff6b5e;
    --kr-up-light: #3a1818;
    --kr-down: #4d9eff;
    --kr-down-light: #14233a;
    --kr-flat: #8b949e;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.3);
    --shadow-md: 0 2px 8px rgba(0,0,0,0.4);
    --shadow-lg: 0 12px 28px rgba(0,0,0,0.5);
  }
}
:root[data-theme="dark"] {
  --bg: #0d1117;
  --surface: #161b22;
  --surface-alt: #1c222b;
  --surface-hover: #21262e;
  --paper: #161b22;
  --border: #2a313c;
  --border-light: #21262e;
  --border-strong: #3a4250;
  --text: #e6edf3;
  --text-secondary: #b3c0cf;
  --text-muted: #8b949e;
  --text-light: #6e7681;
  --accent: #58a6ff;
  --accent-light: #1f2a3a;
  --accent-hover: #79b8ff;
  --accent-soft: #4f6680;
  --rule: #58a6ff;
  --positive: #56d364;
  --positive-light: #133c1d;
  --negative: #f85149;
  --negative-light: #3a1212;
  --warn: #d29922;
  --warn-light: #3a2c0a;
  --tag-bg: #21262e;
  --tag-text: #b3c0cf;
  --kr-up: #ff6b5e;
  --kr-up-light: #3a1818;
  --kr-down: #4d9eff;
  --kr-down-light: #14233a;
  --kr-flat: #8b949e;
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.3);
  --shadow-md: 0 2px 8px rgba(0,0,0,0.4);
  --shadow-lg: 0 12px 28px rgba(0,0,0,0.5);
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
  transition: background-color 200ms, color 200ms;
}
:root:not([data-theme="dark"]) body {
  background-image:
    linear-gradient(to bottom, transparent 0, transparent 24px, rgba(20,33,61,0.015) 24px, rgba(20,33,61,0.015) 25px, transparent 25px),
    linear-gradient(to right, transparent 0, transparent 240px, rgba(20,33,61,0.015) 240px, rgba(20,33,61,0.015) 241px, transparent 241px);
  background-size: 100% 25px, 240px 100%;
}
@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) body {
    background-image:
      linear-gradient(to bottom, transparent 0, transparent 24px, rgba(20,33,61,0.015) 24px, rgba(20,33,61,0.015) 25px, transparent 25px),
      linear-gradient(to right, transparent 0, transparent 240px, rgba(20,33,61,0.015) 240px, rgba(20,33,61,0.015) 241px, transparent 241px);
    background-size: 100% 25px, 240px 100%;
  }
}

/* 테마 토글 버튼 */
.theme-toggle {
  background: transparent; border: 1px solid var(--border);
  width: 32px; height: 32px;
  display: inline-flex; align-items: center; justify-content: center;
  cursor: pointer; color: var(--text-secondary);
  font-size: 14px; line-height: 1;
  border-radius: var(--radius-sm);
  transition: all 120ms;
}
.theme-toggle:hover {
  background: var(--surface-hover);
  border-color: var(--border-strong);
  color: var(--accent);
}
.theme-toggle .sun { display: inline; }
.theme-toggle .moon { display: none; }
:root[data-theme="dark"] .theme-toggle .sun,
:root[data-theme="dark"] .theme-toggle .moon { display: inline; }
:root[data-theme="dark"] .theme-toggle .sun { display: none; }
:root[data-theme="dark"] .theme-toggle .moon { display: inline; }
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

/* 보고서 표 셀 — 자동 색칠 (JS 후처리로 .num-up·.num-down·.num-neg 클래스 추가) */
article.report table td.num-up {
  color: var(--kr-up); font-weight: 600;
}
article.report table td.num-down {
  color: var(--kr-down); font-weight: 600;
}
article.report table td.num-neg {
  color: var(--negative);
}
article.report table td.num-pos {
  color: var(--text);
}

/* 변화율 셀 안에 mini bar (양·음 0 기준) */
article.report table td.num-with-bar {
  position: relative;
}
article.report table td.num-with-bar::after {
  content: ""; position: absolute; bottom: 4px;
  left: 50%; right: 50%; height: 2px; background: transparent;
}
article.report table td.num-up.num-with-bar::after {
  right: 12px; background: var(--kr-up); opacity: 0.4;
}
article.report table td.num-down.num-with-bar::after {
  left: 12px; background: var(--kr-down); opacity: 0.4;
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

/* ─────── Macro 지표 바 — 인라인 SVG 스파크라인 ─────── */
.macro-bar {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0;
  margin: 24px 0 4px;
  padding: 20px 0 8px;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border-light);
}
.macro-cell {
  padding: 0 16px;
  border-right: 1px solid var(--border-light);
  display: flex; flex-direction: column; gap: 6px;
  transition: background 120ms;
  border-radius: var(--radius-sm);
}
.macro-cell:hover {
  background: var(--surface-hover);
}
.macro-cell:last-child { border-right: none; }
.macro-cell:first-child { padding-left: 0; }
.macro-head {
  display: flex; align-items: baseline; justify-content: space-between;
}
.macro-label {
  font-family: var(--display);
  font-size: 11px; font-weight: 700;
  letter-spacing: 0.1em; text-transform: uppercase;
  color: var(--text-muted);
}
.macro-symbol {
  font-family: var(--mono); font-size: 10px;
  color: var(--text-light); font-weight: 500;
}
.macro-value {
  font-family: var(--display);
  font-size: 22px; font-weight: 700;
  letter-spacing: -0.015em; color: var(--text);
  font-feature-settings: 'tnum';
  line-height: 1.1;
}
.sparkline {
  width: 100%; height: 32px;
  display: block;
  margin: 2px 0;
}
.spark-line {
  stroke-width: 1.5;
  stroke-linejoin: round; stroke-linecap: round;
  vector-effect: non-scaling-stroke;
}
.sparkline.spark-up .spark-line { stroke: var(--positive); }
.sparkline.spark-up .spark-area { fill: var(--positive); opacity: 0.08; }
.sparkline.spark-down .spark-line { stroke: var(--negative); }
.sparkline.spark-down .spark-area { fill: var(--negative); opacity: 0.08; }
.macro-changes {
  display: flex; justify-content: space-between; align-items: baseline;
  font-size: 11px;
  font-family: var(--mono);
  font-feature-settings: 'tnum';
}
.macro-up { color: var(--positive); font-weight: 600; }
.macro-down { color: var(--negative); font-weight: 600; }
.macro-1y { color: var(--text-light); font-size: 10px; }

@media (max-width: 720px) {
  .macro-bar { grid-template-columns: repeat(2, 1fr); gap: 18px 0; padding: 16px 0; }
  .macro-cell { padding: 0 10px; }
  .macro-value { font-size: 18px; }
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

/* 마스터 표 — 등락률·시총·sparkline (Phase F+) */
.watchlist-table th.change,
.watchlist-table th.mcap,
.watchlist-table th.spark {
  font-family: var(--mono); font-size: 11px;
  font-weight: 600; letter-spacing: 0.04em;
  color: var(--text-muted); text-transform: uppercase;
}
.watchlist-table th.spark { width: 90px; text-align: left; }
.watchlist-table th.change { width: 70px; text-align: right; }
.watchlist-table th.mcap { width: 200px; text-align: right; }
.watchlist-table th.foreign { width: 90px; text-align: right; }
tr.stock-row td.foreign {
  font-family: var(--mono); font-size: 13px;
  text-align: right; font-feature-settings: "tnum";
  padding-right: 16px; white-space: nowrap;
}
tr.stock-row td.foreign-buy { color: var(--kr-up); }
tr.stock-row td.foreign-sell { color: var(--kr-down); }
tr.stock-row td.foreign-flat { color: var(--kr-flat); opacity: 0.6; }

/* 회사 페이지 외인 보유율 30일 차트 (페르소나 §1.7) */
.foreign-holding-chart {
  margin-top: 20px; padding: 16px 20px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  max-width: 320px;
}
.fhc-header {
  display: flex; align-items: baseline; gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.fhc-label {
  font-family: var(--mono); font-size: 11px;
  color: var(--text-muted); text-transform: uppercase;
  letter-spacing: 0.06em;
}
.fhc-value {
  font-family: var(--mono); font-size: 18px;
  font-weight: 600; color: var(--text);
  font-feature-settings: "tnum";
}
.fhc-change {
  font-family: var(--mono); font-size: 12px;
  font-feature-settings: "tnum";
  padding: 2px 6px; border-radius: 2px;
}
.fhc-change.fhc-up { color: var(--kr-up); background: var(--kr-up-light); }
.fhc-change.fhc-down { color: var(--kr-down); background: var(--kr-down-light); }
.fhc-change.fhc-flat { color: var(--kr-flat); background: transparent; }

.fhc-svg {
  width: 100%; height: 80px; display: block;
}
.fhc-svg.fhc-up polyline { stroke: var(--kr-up); }
.fhc-svg.fhc-down polyline { stroke: var(--kr-down); }
.fhc-svg.fhc-flat polyline { stroke: var(--kr-flat); }
.fhc-svg.fhc-up .fhc-dot { fill: var(--kr-up); }
.fhc-svg.fhc-down .fhc-dot { fill: var(--kr-down); }
.fhc-svg.fhc-flat .fhc-dot { fill: var(--kr-flat); }

.fhc-axis {
  display: flex; justify-content: space-between;
  font-family: var(--mono); font-size: 10px;
  color: var(--text-muted); margin-top: 6px;
  letter-spacing: 0.04em;
}

/* 보고서 미발행 회사 페이지 placeholder */
.empty-coverage {
  max-width: 720px; margin: 32px auto 60px;
  padding: 24px 28px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 3px solid var(--rule);
}
.empty-coverage-title {
  font-size: 15px; font-weight: 600; color: var(--text);
  margin: 0 0 8px;
}
.empty-coverage-meta {
  font-size: 13.5px; line-height: 1.65;
  color: var(--text-secondary); margin: 0 0 16px;
}
.empty-coverage-back {
  font-family: var(--mono); font-size: 12px;
  color: var(--text-muted); text-decoration: none;
  border-bottom: 1px solid var(--rule);
}
.empty-coverage-back:hover { color: var(--accent); }
.watchlist-table th.sortable {
  cursor: pointer; user-select: none;
  transition: color 120ms;
}
.watchlist-table th.sortable:hover { color: var(--accent); }
.watchlist-table th .sort-arrow {
  font-size: 10px; color: var(--accent);
  display: inline-block; min-width: 12px;
}

tr.stock-row td.spark { padding: 0 12px; vertical-align: middle; }
tr.stock-row td.spark svg {
  display: block;
  fill: none;
}
tr.stock-row td.spark svg.spark-up polyline { stroke: var(--kr-up); }
tr.stock-row td.spark svg.spark-down polyline { stroke: var(--kr-down); }
tr.stock-row td.spark svg.spark-flat polyline { stroke: var(--kr-flat); opacity: 0.6; }
tr.stock-row.stock-empty td.spark svg polyline { opacity: 0.5; }

tr.stock-row td.change {
  font-family: var(--mono); font-size: 13px;
  text-align: right; font-feature-settings: "tnum";
  font-weight: 600;
  white-space: nowrap;
}
tr.stock-row td.change.change-up { color: var(--kr-up); }
tr.stock-row td.change.change-down { color: var(--kr-down); }
tr.stock-row td.change.change-flat { color: var(--kr-flat); }

tr.stock-row td.mcap {
  font-family: var(--mono); font-size: 12px;
  font-feature-settings: "tnum";
  text-align: right;
  white-space: nowrap;
  position: relative;
}
.mcap-val {
  display: inline-block; min-width: 50px;
  text-align: right; margin-right: 8px;
  color: var(--text-secondary); font-weight: 500;
}
.mcap-bar {
  display: inline-block;
  width: 120px; height: 6px;
  background: var(--surface-hover);
  border-radius: 1px;
  overflow: hidden;
  vertical-align: middle;
}
.mcap-fill {
  display: block; height: 100%;
  background: var(--accent-soft);
  transition: background 120ms;
}
tr.stock-row.stock-active:hover .mcap-fill { background: var(--accent); }

@media (max-width: 1000px) {
  .watchlist-table th.spark,
  tr.stock-row td.spark { display: none; }
}
@media (max-width: 900px) {
  .watchlist-table th.change,
  tr.stock-row td.change { display: none; }
  .watchlist-table th.mcap,
  tr.stock-row td.mcap { width: auto; }
  .mcap-bar { display: none; }
}
@media (max-width: 720px) {
  .watchlist-table th.mcap,
  tr.stock-row td.mcap { display: none; }
}

/* Daily 메모 (Phase D) */
.daily-link-banner {
  margin-top: 24px;
}
.daily-link-banner a {
  display: flex; align-items: center; gap: 14px;
  padding: 14px 18px;
  background: var(--surface); border: 1px solid var(--rule);
  text-decoration: none; color: var(--text);
  transition: border-color 120ms;
}
.daily-link-banner a:hover { border-color: var(--accent); }
.daily-banner-label {
  font-family: var(--mono); font-size: 11px;
  letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--text-muted);
}
.daily-banner-count {
  font-family: var(--mono); font-size: 13px; font-weight: 700;
  padding: 3px 10px;
  border-radius: 3px;
  letter-spacing: 0.02em;
  /* 라이트 모드: 흰 배경 + 강조 색 글자 + 강조 색 테두리 (outline 스타일)
     다크 모드: 강조 색 배경 + 어두운 글자 (filled 스타일)
     0편이어도 명료히 보임 */
  background: var(--surface);
  color: var(--accent);
  border: 1.5px solid var(--accent);
}
.daily-banner-count.has-notes {
  background: var(--accent);
  color: var(--surface);
}
:root[data-theme="dark"] .daily-banner-count {
  background: var(--surface);
  color: var(--accent);
  border-color: var(--accent);
}
:root[data-theme="dark"] .daily-banner-count.has-notes {
  background: var(--accent);
  color: var(--bg);
}
.daily-banner-meta {
  flex: 1; font-size: 13px; color: var(--text-muted);
}
.daily-banner-arrow {
  font-family: var(--mono); color: var(--text-muted);
  font-size: 16px;
}

/* Daily 인덱스 페이지 — observation log 톤 (단일 열, lab notebook 느낌) */
.dn-page {
  max-width: 760px; margin: 24px auto 60px;
  padding: 0 32px;
}

.dn-header {
  border-bottom: 2px solid var(--rule);
  padding-bottom: 20px; margin-bottom: 28px;
}
.dn-header-meta {
  display: flex; justify-content: space-between; align-items: center;
  font-family: var(--mono); font-size: 11px;
  color: var(--text-dim); letter-spacing: 0.04em;
  margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
}
.dn-tag { text-transform: uppercase; }
.dn-stat { font-feature-settings: "tnum"; }
.dn-title {
  font-size: 26px; font-weight: 600; margin: 4px 0 10px;
  letter-spacing: -0.01em;
}
.dn-sub {
  color: var(--text-dim); font-size: 14px; line-height: 1.65;
  max-width: 640px;
}

/* Method footnote — 페이지 하단, 작은 reference 톤 */
.dn-method {
  margin-top: 48px; padding-top: 20px;
  border-top: 1px solid var(--rule);
  font-size: 12px; color: var(--text-dim);
  font-family: var(--mono); line-height: 1.85;
}
.dn-method h2 {
  font-size: 11px; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--text-dim);
  margin: 0 0 8px; font-weight: 500;
}
.dn-method ul {
  list-style: none; padding: 0; margin: 0 0 10px;
}
.dn-method ul li { padding: 1px 0; }
.dn-method ul li strong {
  display: inline-block; min-width: 50px;
  font-size: 11px; color: var(--text-dim);
  font-weight: 500; text-transform: uppercase;
  letter-spacing: 0.04em; margin-right: 8px;
}
.dn-method-meta {
  margin: 8px 0 0; font-size: 11px;
}
.dn-method-meta a {
  color: var(--text-dim); text-decoration: none;
  border-bottom: 1px solid var(--rule);
}
.dn-method-meta a:hover { color: var(--accent); border-color: var(--accent); }

.dn-archive { min-width: 0; }

.dn-list { list-style: none; padding: 0; margin: 0; }
.dn-item {
  border-bottom: 1px solid var(--rule);
}
.dn-row {
  display: flex; gap: 20px; align-items: flex-start;
  padding: 16px 0;
  text-decoration: none; color: inherit;
}
.dn-row:hover .dn-headline { color: var(--accent); }
.dn-date {
  font-family: var(--mono); font-size: 12px;
  color: var(--text-dim); flex-shrink: 0;
  padding-top: 1px; min-width: 92px;
  font-feature-settings: "tnum";
}
.dn-body { flex: 1; min-width: 0; }
.dn-headline {
  display: block; font-size: 14.5px; line-height: 1.5;
  font-weight: 500; transition: color 120ms;
}
.dn-meta {
  display: block; margin-top: 4px;
  font-family: var(--mono); font-size: 11.5px;
  color: var(--text-dim);
}

.dn-empty-state {
  border: 1px dashed var(--rule);
  padding: 26px 22px; text-align: center;
}
.dn-empty-headline {
  font-size: 14px; color: var(--text-dim);
  margin: 0 0 6px;
}
.dn-empty-meta {
  font-family: var(--mono); font-size: 12px;
  color: var(--text-dim); margin: 0;
}
.dn-empty-meta code {
  background: var(--surface); padding: 1px 6px;
  border: 1px solid var(--rule); border-radius: 2px;
  font-size: 11.5px;
}

/* 일간 메모 SVG 스파크라인 (hover·축·툴팁) */
svg.dn-spark {
  cursor: default;
  display: inline-block;
  vertical-align: middle;
}
svg.dn-spark polyline {
  transition: stroke-width 120ms;
}
svg.dn-spark.spark-up polyline { stroke: var(--kr-up); }
svg.dn-spark.spark-down polyline { stroke: var(--kr-down); }
svg.dn-spark.spark-flat polyline { stroke: var(--kr-flat); opacity: 0.7; }
svg.dn-spark:hover polyline { stroke-width: 2; }
svg.dn-spark .dn-spark-label {
  font-family: var(--mono); font-size: 8.5px;
  fill: var(--text-muted);
  font-feature-settings: "tnum";
}

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
