#!/bin/bash
# Run, do not source: preserves shell options in caller.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Please execute, not source: $0" >&2
  return 1
fi
set -euo pipefail

HOME_DIR="${HOME_DIR:?HOME_DIR must be set}"
APP_DIR="${APP_DIR:-$HOME_DIR/zdm-microservices}"
MAIN_PY="${MAIN_PY:-$APP_DIR/main.py}"

: "${ZEUS_BASE:?ZEUS_BASE must be set}"
RUNTIME_ENV="${ZEUS_RUNTIME_ENV:-$ZEUS_BASE/zeus.env}"
DEFAULT_ENV="$APP_DIR/zeus.env.sample"
AUTH_TEMPLATE="$APP_DIR/.zeus.auth.env.sample"
mkdir -p "$(dirname "$RUNTIME_ENV")"
[ ! -f "$RUNTIME_ENV" ] && [ -f "$DEFAULT_ENV" ] && cp "$DEFAULT_ENV" "$RUNTIME_ENV"

set -a
[ -f "$RUNTIME_ENV" ] && { set +u; source "$RUNTIME_ENV"; set -u; }
set +a

ZEUS_HOST="${ZEUS_HOST:?ZEUS_HOST must be set}"
ZEUS_PORT="${ZEUS_PORT:?ZEUS_PORT must be set}"
ZEUS_CERT_DIR="${ZEUS_CERT_DIR:-$ZEUS_BASE/certs}"
ZEUS_SSL_CERTFILE="${ZEUS_SSL_CERTFILE:-$ZEUS_CERT_DIR/zeus.crt}"
ZEUS_SSL_KEYFILE="${ZEUS_SSL_KEYFILE:-$ZEUS_CERT_DIR/zeus.key}"
ZEUS_AUTH_FILE="${ZEUS_AUTH_FILE:-$ZEUS_BASE/.zeus.auth.env}"

ZEUS_LOG="${ZEUS_LOG:-$ZEUS_BASE/log}"
LOGFILE="${LOGFILE:-$ZEUS_LOG/microservice.log}"
DEBUGLOG="${DEBUGLOG:-$ZEUS_LOG/debug.log}"
PIDFILE="${PIDFILE:-$ZEUS_LOG/microservice.pid}"

PYTHON_BIN="${PYTHON_BIN:-python3.11}"

export ZEUS_BASE ZEUS_HOST ZEUS_PORT ZEUS_SSL_CERTFILE ZEUS_SSL_KEYFILE ZEUS_AUTH_FILE

mkdir -p "$ZEUS_LOG"
mkdir -p "$(dirname "$ZEUS_SSL_CERTFILE")"

log() {
  echo "$(date +"%Y-%m-%d %H:%M:%S") - $*" | tee -a "$DEBUGLOG"
}

if [[ ! -f "$ZEUS_AUTH_FILE" ]]; then
  mkdir -p "$(dirname "$ZEUS_AUTH_FILE")"
  if [[ -f "$AUTH_TEMPLATE" ]]; then
    cp "$AUTH_TEMPLATE" "$ZEUS_AUTH_FILE"
  else
    cat > "$ZEUS_AUTH_FILE" <<'EOF'
# ZEUS API auth users (plain text). Change immediately.
ZEUS_API_USER_1=zdmuser
ZEUS_API_USER_1_PASSWORD=ChangeMe123#_
EOF
  fi
  chmod 600 "$ZEUS_AUTH_FILE" || true
  log "Created default API auth file at $ZEUS_AUTH_FILE; please change credentials."
fi

# If certs are missing, let main.py fail fast; generation is handled in start_zeus.sh

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
