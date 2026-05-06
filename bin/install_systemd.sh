#!/bin/bash
# K_E_R systemd user timer 설치/활성화.
#
# 효과:
#   - 매주 화 22:00 KST / 일 21:00 KST 자동 실행
#   - 컴퓨터가 슬롯 시간에 꺼져있었으면 부팅 즉시 catch-up (Persistent=true)
#   - 사용자 로그인 안 된 상태에서도 동작 (loginctl enable-linger)
#
# 수동 실행: bin/run_weekly.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"
USER="$(whoami)"

echo "K_E_R systemd timer 설치 중..."
echo "  REPO_ROOT: $REPO_ROOT"
echo "  USER: $USER"
echo ""

# 0. 사전 점검
if [ ! -f "$REPO_ROOT/.env" ]; then
  echo "[warn] .env 없음. 시간 시점에 실행 실패할 수 있음."
  echo "       먼저: cp .env.example .env && chmod 600 .env"
  echo "       그 다음 DART_API_KEY 채움."
fi

if [ ! -x "$REPO_ROOT/.venv/bin/python" ]; then
  echo "[error] .venv 없음. 먼저: python3 -m venv .venv && .venv/bin/pip install -e ."
  exit 1
fi

if ! command -v claude &> /dev/null; then
  echo "[warn] claude CLI 없음. 구독 인증된 Claude Code 설치 필요."
fi

# 1. wrapper 스크립트 실행 권한
chmod +x "$REPO_ROOT/bin/run_weekly.sh" "$REPO_ROOT/bin/run_weekend.sh"

# 2. systemd unit 파일 복사
mkdir -p "$USER_SYSTEMD_DIR"
for f in k_e_r-weekday.service k_e_r-weekday.timer \
         k_e_r-weekend.service k_e_r-weekend.timer \
         k_e_r-daily-refresh.service k_e_r-daily-refresh.timer; do
  cp "$REPO_ROOT/systemd/$f" "$USER_SYSTEMD_DIR/$f"
  echo "  installed: $USER_SYSTEMD_DIR/$f"
done

# 3. systemd user 데몬 reload
systemctl --user daemon-reload
echo "  systemctl --user daemon-reload"

# 4. timer enable + start
systemctl --user enable --now k_e_r-weekday.timer
echo "  enabled: k_e_r-weekday.timer (Tue 22:00 KST — 보고서 생성)"

systemctl --user enable --now k_e_r-daily-refresh.timer
echo "  enabled: k_e_r-daily-refresh.timer (매일 18:00 KST — 매크로 갱신)"

systemctl --user enable --now k_e_r-weekend.timer
echo "  enabled: k_e_r-weekend.timer (Sun 21:00 KST — 종목 보고서 대체. 산업노트 generator 구현 후 진짜 산업노트로 전환)"

# 5. 로그인 안 된 상태에서도 user service 동작 (lingering)
# 이게 핵심 — 이거 없으면 user 로그아웃 시 timer 멈춤
if loginctl show-user "$USER" | grep -q "Linger=no"; then
  echo ""
  echo "[중요] user lingering 활성화 필요. 다음 명령을 *root 권한으로* 실행:"
  echo "  sudo loginctl enable-linger $USER"
  echo ""
  echo "이 명령 없이는 컴퓨터가 켜져있어도 너가 로그아웃하면 timer가 멈춤."
fi

echo ""
echo "설치 완료."
echo ""
echo "=== 다음 실행 시간 확인 ==="
systemctl --user list-timers k_e_r-*.timer
