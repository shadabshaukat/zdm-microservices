#!/bin/bash
set -euo pipefail

APP="/home/zdmuser/zdm-microservices/streamlit_app.py"
LOGDIR="/u01/log"
LOGFILE="$LOGDIR/streamlit.log"
PIDFILE="$LOGDIR/streamlit.pid"
PORT="${STREAMLIT_PORT:-8000}"

mkdir -p "$LOGDIR"

log() { echo "$(date +"%Y-%m-%d %H:%M:%S") - $*" | tee -a "$LOGFILE"; }

log "restart_streamlit.sh started (port=$PORT)"

if [[ ! -f "$APP" ]]; then
  log "ERROR: streamlit_app.py not found: $APP"
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
  fi
fi

log "Starting streamlit..."
nohup python3.11 -m streamlit run "$APP" \
  --server.address 0.0.0.0 \
  --server.port "$PORT" \
  --server.headless true \
  >> "$LOGFILE" 2>&1 < /dev/null &

echo $! > "$PIDFILE"
sleep 2

newpid="$(cat "$PIDFILE")"
log "Started pid=$newpid"

log "Listening check:"
if command -v ss >/dev/null 2>&1; then
  ss -ltnp | grep ":$PORT" || true
fi

log "HTTP check:"
curl -I "http://127.0.0.1:$PORT" || true

log "Tail log:"
tail -n 40 "$LOGFILE" || true

log "restart_streamlit.sh finished"
