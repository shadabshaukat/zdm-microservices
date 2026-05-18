#!/bin/bash
# Purpose: prepare ZEUS runtime and start backend. React is served by FastAPI. Do not source.
set -euo pipefail

# Required base variables
: "${HOME_DIR:?HOME_DIR must be set}"
: "${ZEUS_BASE:?ZEUS_BASE must be set}"
: "${ZDM_HOME:?ZDM_HOME must be set}"

APP_DIR="$HOME_DIR/zdm-microservices"
RESTART_MICRO="$HOME_DIR/restart_microservice.sh"
RUNTIME_ENV="${ZEUS_RUNTIME_ENV:-$ZEUS_BASE/zeus.env}"
AUTH_FILE="${ZEUS_AUTH_FILE:-$ZEUS_BASE/.zeus.auth.env}"
ZEUS_LOG="${ZEUS_LOG:-$ZEUS_BASE/log}"
ZEUS_CERT_DIR="${ZEUS_CERT_DIR:-$ZEUS_BASE/certs}"
DEFAULT_ENV="$APP_DIR/zeus.env.sample"
AUTH_TEMPLATE="$APP_DIR/.zeus.auth.env.sample"

mkdir -p "$ZEUS_BASE" "$ZEUS_LOG" "$ZEUS_CERT_DIR"
log() { echo "$(date +"%Y-%m-%d %H:%M:%S") - $*" | tee -a "$ZEUS_LOG/debug.log"; }

if [[ ! -x "$RESTART_MICRO" ]]; then
  log "ERROR: required script missing or not executable: $RESTART_MICRO"
  exit 1
fi

# Prepare env file
mkdir -p "$(dirname "$RUNTIME_ENV")"
if [[ ! -f "$RUNTIME_ENV" && -f "$DEFAULT_ENV" ]]; then
  cp "$DEFAULT_ENV" "$RUNTIME_ENV"
  log "Seeded runtime env from sample -> $RUNTIME_ENV"
fi

# Load env
set -a
[ -f "$RUNTIME_ENV" ] && { set +u; source "$RUNTIME_ENV"; set -u; }
set +a

# Prepare auth file
if [[ ! -f "$AUTH_FILE" ]]; then
  mkdir -p "$(dirname "$AUTH_FILE")"
  if [[ -f "$AUTH_TEMPLATE" ]]; then
    cp "$AUTH_TEMPLATE" "$AUTH_FILE"
  else
    cat > "$AUTH_FILE" <<'EOF_AUTH'
# ZEUS API auth users (plain text). Change defaults immediately.
ZEUS_API_USER_1=zdmuser
ZEUS_API_USER_1_PASSWORD=ChangeMe123#_
EOF_AUTH
  fi
  chmod 600 "$AUTH_FILE" || true
  log "Created auth file at $AUTH_FILE"
fi

# Ensure certs
cert_path="$ZEUS_CERT_DIR/zeus.crt"
key_path="$ZEUS_CERT_DIR/zeus.key"
if [[ ! -f "$cert_path" || ! -f "$key_path" ]]; then
  if ! command -v openssl >/dev/null 2>&1; then
    log "ERROR: openssl not found; cannot generate TLS cert."; exit 1
  fi
  log "Generating self-signed TLS cert with SAN for localhost/127.0.0.1"
  openssl req -x509 -newkey rsa:4096 -nodes \
    -keyout "$key_path" \
    -out "$cert_path" \
    -days 365 \
    -subj "/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" \
    > "$ZEUS_LOG/openssl_generate_cert.log" 2>&1
  chmod 600 "$key_path" || true
  chmod 644 "$cert_path" || true
fi

build_react_frontend() {
  local frontend_dir="$APP_DIR/frontend"
  local frontend_log="$ZEUS_LOG/frontend_build.log"
  local dist_index="$frontend_dir/dist/index.html"

  if [[ ! -d "$frontend_dir" ]]; then
    log "ERROR: React frontend directory missing: $frontend_dir"
    exit 1
  fi
  if [[ ! -f "$frontend_dir/package-lock.json" ]]; then
    log "ERROR: package-lock.json missing in React frontend directory"
    exit 1
  fi
  if ! command -v npm >/dev/null 2>&1; then
    log "ERROR: npm not found; cannot build React frontend"
    exit 1
  fi

  log "Building React frontend..."
  if ! (
    cd "$frontend_dir"
    npm ci
    npm run build
  ) >> "$frontend_log" 2>&1; then
    log "ERROR: React frontend build failed; see $frontend_log"
    exit 1
  fi

  if [[ ! -f "$dist_index" ]]; then
    log "ERROR: React frontend build did not produce $dist_index"
    exit 1
  fi
  log "React frontend build complete."
}

build_react_frontend

log "Starting ZEUS backend..."
if ! "$RESTART_MICRO" >> "$ZEUS_LOG/microservice.log" 2>&1; then
  log "ERROR: backend start script failed"
  exit 1
fi

log "React frontend is served by ZEUS backend."

check_pid_running() {
  local pidfile="$1"
  local name="$2"
  for _ in {1..10}; do
    if [[ -s "$pidfile" ]]; then
      local pid
      pid=$(cat "$pidfile" 2>/dev/null || true)
      if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
        return 0
      fi
    fi
    sleep 1
  done
  log "ERROR: $name did not present a healthy PID after startup (pidfile=$pidfile)"
  return 1
}

check_pid_running "$ZEUS_LOG/microservice.pid" "backend"

echo "healthy $(date '+%Y-%m-%dT%H:%M:%S%z')" > "$ZEUS_LOG/.zeus_finished"
log "ZEUS startup complete."

# Keep PID1 alive if this is the entrypoint
if [[ "$$" -eq 1 ]]; then
  exec tail -f "$ZEUS_LOG/microservice.log" 2>/dev/null
fi
