#!/bin/bash

set -euo pipefail

if [[ "${ZEUS_INTERNAL_RUN:-}" != "1" ]]; then
  echo "This script is for internal use only."
  exit 1
fi

HOME_DIR="${HOME_DIR:-/home/zdmuser}"
ZEUS_BASE="${ZEUS_BASE:-/u01/data/zeus}"
ZEUS_LOG="${ZEUS_LOG:-$ZEUS_BASE/log}"

mkdir -p "$ZEUS_LOG"

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') - $*" >> "$ZEUS_LOG/stop_zeus.log"
}

stop_pid_file() {
  local name="$1"
  local pid_file="$2"

  if [[ -f "$pid_file" ]]; then
    local pid
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      log "Stopping $name pid=$pid"
      kill "$pid" 2>/dev/null || true

      for _ in {1..10}; do
        if ! kill -0 "$pid" 2>/dev/null; then
          break
        fi
        sleep 1
      done

      if kill -0 "$pid" 2>/dev/null; then
        log "$name still running after grace period, sending SIGKILL pid=$pid"
        kill -9 "$pid" 2>/dev/null || true
      fi
    else
      log "$name pid file exists but process is not running"
    fi
  else
    log "$name pid file not found: $pid_file"
  fi
}

log "ZEUS graceful shutdown started"

stop_pid_file "microservice" "$ZEUS_LOG/microservice.pid"

pkill -f "$HOME_DIR/zdm-microservices/main.py" 2>/dev/null || true

# Clear health sentinel so next start must recreate it
rm -f "$ZEUS_LOG/.zeus_finished" || true

log "ZEUS graceful shutdown finished"
