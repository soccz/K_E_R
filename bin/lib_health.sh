#!/bin/bash
# 공통 health 헬퍼 — run_*.sh 시작/종료 시 사용.
# 디스크 체크 + JSON 상태 기록 + 로그 retention.

# Path 보강 (systemd 환경 대비)
export PATH="$HOME/.local/bin:$HOME/.local/share/claude/versions:$PATH"

# REPO_ROOT는 호출 측에서 미리 export 되어 있어야 함
HEALTH_DIR="${REPO_ROOT:-/home/soccz/22tb/report}/logs/health"
LOGS_DIR="${REPO_ROOT:-/home/soccz/22tb/report}/logs"
mkdir -p "$HEALTH_DIR"

# B. 디스크 사용량 체크 — 5GB 미만이면 warn
check_disk_space() {
  local path="${1:-/home/soccz/22tb}"
  local avail_kb
  avail_kb=$(df --output=avail "$path" | tail -1 2>/dev/null || echo 0)
  local avail_gb=$((avail_kb / 1024 / 1024))
  if [ "$avail_gb" -lt 5 ]; then
    echo "[health] ⚠ 디스크 부족: $path ${avail_gb}GB free (threshold 5GB)"
    return 1
  fi
  echo "[health] disk OK: ${avail_gb}GB free"
  return 0
}

# E. health JSON 기록 — timer/run_name 단위
# usage: write_health <timer_name> <status> [details_json]
write_health() {
  local timer_name="$1"
  local status="${2:-ok}"
  # bash ${3:-{}} 는 첫 } 가 expansion을 종료해 ` "details": {"test": true}}` 같은
  # malformed JSON 발생. 명시적 default 변수로 회피.
  local default_details='{}'
  local details="${3:-$default_details}"
  local now
  now=$(date '+%Y-%m-%dT%H:%M:%S%z')
  local file="$HEALTH_DIR/$timer_name.json"
  cat > "$file" <<EOF
{
  "timer": "$timer_name",
  "last_run": "$now",
  "status": "$status",
  "details": $details
}
EOF
}

# C. 로그 retention — 7일 이상 된 로그 삭제
log_retention_cleanup() {
  if [ -d "$LOGS_DIR" ]; then
    find "$LOGS_DIR" -maxdepth 1 -name "*.log" -mtime +7 -delete 2>/dev/null || true
    # batch_*.log도 7일
    find "$LOGS_DIR" -maxdepth 1 -name "batch_*.log" -mtime +7 -delete 2>/dev/null || true
  fi
}
