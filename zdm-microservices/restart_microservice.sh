#!/bin/bash
set -euo pipefail

HOME_DIR="${HOME_DIR:-/home/zdmuser}"
APP_DIR="${APP_DIR:-$HOME_DIR/zdm-microservices}"
MAIN_PY="${MAIN_PY:-$APP_DIR/main.py}"

ZEUS_LOG="${ZEUS_LOG:-/u01/log}"
LOGFILE="${LOGFILE:-$ZEUS_LOG/microservice.log}"
DEBUGLOG="${DEBUGLOG:-$ZEUS_LOG/debug.log}"
PIDFILE="${PIDFILE:-$ZEUS_LOG/microservice.pid}"

PYTHON_BIN="${PYTHON_BIN:-python3.11}"

mkdir -p "$ZEUS_LOG"

log() {
  echo "$(date +"%Y-%m-%d %H:%M:%S") - $*" | tee -a "$DEBUGLOG"
}

log "restart_microservice.sh started"
log "MAIN_PY=$MAIN_PY"

if [[ ! -f "$MAIN_PY" ]]; then
  log "ERROR: main.py not found: $MAIN_PY"
  exit 1
fi

log "Stopping existing microservice (if any)..."
pids="$(pgrep -f "python3\.11 .*zdm-microservices/main\.py" || true)"
if [[ -n "$pids" ]]; then
  log "Found PIDs: $pids"
  kill $pids || true
  sleep 1
  still="$(pgrep -f "python3\.11 .*zdm-microservices/main\.py" || true)"
  if [[ -n "$still" ]]; then
    log "Still running, force killing: $still"
    kill -9 $still || true
  fi
else
  log "No existing process found."
fi

log "Starting microservice..."
# Fully detach: nohup + </dev/null + &
( cd "$APP_DIR" && nohup "$PYTHON_BIN" "$MAIN_PY" >>"$LOGFILE" 2>&1 < /dev/null & echo $! > "$PIDFILE" )

sleep 2
pid="$(cat "$PIDFILE" 2>/dev/null || true)"
log "Started PID: ${pid:-NONE}"

log "Process check:"
ps -ef | grep -E "python3\.11 .*zdm-microservices/main\.py" | grep -v grep || true

log "Last 80 lines of microservice.log:"
tail -n 80 "$LOGFILE" || true

log "restart_microservice.sh finished"