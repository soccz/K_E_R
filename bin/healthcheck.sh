#!/bin/bash
# K_E_R 시스템 헬스체크.
#
# 부팅 후 / 정기 점검 / 디버깅에 사용.
# 모든 컴포넌트가 살아있는지 빠르게 확인.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PASS=0
FAIL=0
WARN=0

ok()   { echo "  [OK]   $1"; PASS=$((PASS+1)); }
fail() { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }
warn() { echo "  [WARN] $1"; WARN=$((WARN+1)); }

echo "K_E_R 헬스체크 — $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "================================================"

echo ""
echo "[1/7] 파일·디렉토리 구조"
[ -f _frame.md ] && ok "_frame.md" || fail "_frame.md 없음"
[ -f _persona.md ] && ok "_persona.md" || fail "_persona.md 없음"
[ -f _watchlist.md ] && ok "_watchlist.md" || fail "_watchlist.md 없음"
[ -d pipeline ] && ok "pipeline/" || fail "pipeline/ 없음"
[ -d companies ] && ok "companies/" || warn "companies/ 없음 (첫 실행 전이면 OK)"
[ -d logs ] && ok "logs/" || warn "logs/ 없음 (자동 생성됨)"

echo ""
echo "[2/7] 비밀 파일"
if [ -f .env ]; then
  perm=$(stat -c %a .env)
  if [ "$perm" = "600" ]; then ok ".env 권한 600"; else warn ".env 권한 $perm (chmod 600 권장)"; fi
  if grep -q "^DART_API_KEY=..*" .env && ! grep -q "PUT_YOUR" .env; then
    ok "DART_API_KEY 설정됨"
  else
    fail ".env에 DART_API_KEY 미설정"
  fi
else
  fail ".env 없음 (cp .env.example .env 후 키 채움)"
fi

echo ""
echo "[3/7] Python 환경"
if [ -x .venv/bin/python ]; then
  PY_VER=$(.venv/bin/python --version 2>&1)
  ok "venv: $PY_VER"
  if .venv/bin/python -c "import anthropic, requests" 2>/dev/null; then
    ok "주요 패키지 임포트 OK"
  else
    fail "패키지 누락 (.venv/bin/pip install -e .)"
  fi
else
  fail ".venv 없음"
fi

echo ""
echo "[4/7] Claude Code CLI"
if command -v claude &> /dev/null; then
  CLI_VER=$(claude --version 2>&1 | head -1)
  ok "claude: $CLI_VER"
else
  fail "claude CLI 없음 (구독 모드 작동 불가)"
fi

if command -v pdftotext &> /dev/null; then
  ok "pdftotext 사용 가능"
else
  warn "pdftotext 없음 (sudo apt install poppler-utils)"
fi

echo ""
echo "[5/7] systemd timer"
if systemctl --user list-unit-files k_e_r-weekday.timer 2>&1 | grep -q "k_e_r-weekday.timer"; then
  if systemctl --user is-active k_e_r-weekday.timer &>/dev/null; then
    ok "k_e_r-weekday.timer 활성"
    NEXT=$(systemctl --user list-timers k_e_r-weekday.timer --no-legend 2>&1 | awk '{print $1, $2}')
    echo "         다음 실행: $NEXT"
  else
    warn "k_e_r-weekday.timer 비활성 (systemctl --user start k_e_r-weekday.timer)"
  fi
else
  fail "systemd timer 미설치 (bin/install_systemd.sh)"
fi

USER="$(whoami)"
if loginctl show-user "$USER" 2>&1 | grep -q "Linger=yes"; then
  ok "user lingering 활성 (로그아웃해도 timer 동작)"
else
  warn "user lingering 비활성 (sudo loginctl enable-linger $USER)"
fi

echo ""
echo "[6/7] 네트워크 — TCP 연결 가능 여부 (인증·HTTP 코드는 무관)"
check_host() {
  local host="$1"
  local port="${2:-443}"
  if timeout 5 bash -c "exec 3<>/dev/tcp/$host/$port" 2>/dev/null; then
    return 0
  fi
  return 1
}

if check_host opendart.fss.or.kr; then ok "opendart.fss.or.kr:443"; else fail "DART 도달 불가"; fi
if check_host api.anthropic.com; then ok "api.anthropic.com:443"; else warn "Anthropic 도달 불가"; fi
if check_host github.com; then ok "github.com:443"; else warn "GitHub 도달 불가"; fi

echo ""
echo "[7/7] git 상태"
if git rev-parse --is-inside-work-tree &>/dev/null; then
  REMOTE=$(git remote get-url origin 2>/dev/null || echo "(no remote)")
  ok "git repo: $REMOTE"
  if [ "$(git status --porcelain | wc -l)" -gt 0 ]; then
    warn "uncommitted changes 있음 ($(git status --porcelain | wc -l) 파일)"
  fi
else
  warn "git repo 아님 (git init 필요)"
fi

echo ""
echo "================================================"
echo "결과: $PASS pass / $WARN warn / $FAIL fail"
[ $FAIL -gt 0 ] && exit 1
exit 0
