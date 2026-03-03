#!/bin/bash
# Run, do not source: preserves shell options in caller.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Please execute, not source: $0" >&2
  return 1
fi
set -euo pipefail

: "${HOME_DIR:?HOME_DIR must be set}"
: "${ZEUS_BASE:?ZEUS_BASE must be set}"

APP_DIR="${APP_DIR:-$HOME_DIR/zdm-microservices}"
APP="$APP_DIR/streamlit_app.py"

RUNTIME_ENV="${ZEUS_RUNTIME_ENV:-$ZEUS_BASE/zeus.env}"
DEFAULT_ENV="$APP_DIR/zeus.env.sample"
mkdir -p "$(dirname "$RUNTIME_ENV")"
[ ! -f "$RUNTIME_ENV" ] && [ -f "$DEFAULT_ENV" ] && cp "$DEFAULT_ENV" "$RUNTIME_ENV"

set -a
[ -f "$RUNTIME_ENV" ] && { set +u; source "$RUNTIME_ENV"; set -u; }
set +a

: "${ZEUS_BASE:?ZEUS_BASE must be set (after env load)}"
: "${ZEUS_PORT:?ZEUS_PORT must be set}"

LOGDIR="${ZEUS_LOG:-$ZEUS_BASE/log}"
LOGFILE="$LOGDIR/streamlit.log"
PIDFILE="$LOGDIR/streamlit.pid"

PORT="${STREAMLIT_PORT:?STREAMLIT_PORT must be set}"
CERT_DEFAULT="${ZEUS_CERT_DIR:-${ZEUS_BASE}/certs}/zeus.crt"
KEY_DEFAULT="${ZEUS_CERT_DIR:-${ZEUS_BASE}/certs}/zeus.key"
CERT="${STREAMLIT_SSL_CERT:-$CERT_DEFAULT}"
KEY="${STREAMLIT_SSL_KEY:-$KEY_DEFAULT}"
PROTO="https"
API_BASE_URL="${API_BASE_URL:-https://localhost:${ZEUS_PORT}}"

mkdir -p "$LOGDIR"
mkdir -p "$(dirname "$CERT")"

log() { echo "$(date +"%Y-%m-%d %H:%M:%S") - $*" | tee -a "$LOGFILE"; }

log "restart_streamlit.sh started (port=$PORT)"

if [[ ! -f "$APP" ]]; then
  log "ERROR: streamlit_app.py not found: $APP"
  exit 1
fi

# require TLS assets
if [[ ! -f "$CERT" ]]; then
  log "ERROR: TLS cert not found at $CERT (set STREAMLIT_SSL_CERT)"
  exit 1
fi
if [[ ! -f "$KEY" ]]; then
  log "ERROR: TLS key not found at $KEY (set STREAMLIT_SSL_KEY)"
  exit 1
fi

# stop old by pidfile
if [[ -f "$PIDFILE" ]] && ps -p "$(cat "$PIDFILE")" >/dev/null 2>&1; then
  oldpid="$(cat "$PIDFILE")"
  log "Stopping old pid=$oldpid"
  kill "$oldpid" || true
  sleep 1
fi

# fallback kill by pattern
pids="$(pgrep -f "streamlit run .*streamlit_app\.py" || true)"
if [[ -n "$pids" ]]; then
  log "Killing leftover pids: $pids"
  kill $pids || true
  sleep 1
fi

# free port if something else is listening
if command -v ss >/dev/null 2>&1; then
  pids_on_port="$(ss -ltnp | awk -v p=":$PORT" '$4 ~ p {print $NF}' | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | sort -u)"
  if [[ -n "$pids_on_port" ]]; then
    log "Port $PORT occupied by pid(s): $pids_on_port; killing..."
    kill $pids_on_port || true
    sleep 1
    # double-check and force kill if still present
    pids_on_port="$(ss -ltnp | awk -v p=":$PORT" '$4 ~ p {print $NF}' | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | sort -u)"
    if [[ -n "$pids_on_port" ]]; then
      log "Port $PORT still busy after kill; forcing kill -9: $pids_on_port"
      kill -9 $pids_on_port || true
      sleep 1
    fi
  fi
fi

log "Using TLS cert=$CERT key=$KEY"
SSL_ARGS="--server.sslCertFile $CERT --server.sslKeyFile $KEY"

log "Starting streamlit..."
export REQUESTS_CA_BUNDLE="$CERT"
export API_BASE_URL
nohup python3.11 -m streamlit run "$APP" \
  --server.address 0.0.0.0 \
  --server.port "$PORT" \
  --server.headless true \
  $SSL_ARGS \
  >> "$LOGFILE" 2>&1 < /dev/null &

echo $! > "$PIDFILE"
sleep 2

newpid="$(cat "$PIDFILE")"
log "Started pid=$newpid"

# Verify port is owned by new pid; else fail fast
if command -v ss >/dev/null 2>&1; then
  pids_on_port="$(ss -ltnp | awk -v p=":$PORT" '$4 ~ p {print $NF}' | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | sort -u)"
  if ! echo "$pids_on_port" | grep -qw "$newpid"; then
    log "ERROR: Port $PORT is not owned by new pid $newpid (pids on port: $pids_on_port); killing listeners and exiting."
    [[ -n "$pids_on_port" ]] && kill -9 $pids_on_port || true
    exit 1
  fi
fi

log "Listening check:"
if command -v ss >/dev/null 2>&1; then
  ss -ltnp | grep ":$PORT" || true
fi

log "Health check ($PROTO):"
curl --cacert "$CERT" -m 5 -I "$PROTO://127.0.0.1:$PORT" || true

log "Tail log:"
tail -n 40 "$LOGFILE" || true

log "restart_streamlit.sh finished"
