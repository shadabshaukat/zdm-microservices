#!/bin/bash
# Purpose: prepare ZEUS runtime and start backend + Streamlit. Do not source.
set -euo pipefail

# Required base variables
: "${HOME_DIR:?HOME_DIR must be set}"
: "${ZEUS_BASE:?ZEUS_BASE must be set}"
: "${ZDM_HOME:?ZDM_HOME must be set}"

APP_DIR="$HOME_DIR/zdm-microservices"
RESTART_MICRO="$HOME_DIR/restart_microservice.sh"
RESTART_UI="$HOME_DIR/restart_streamlit.sh"
RUNTIME_ENV="${ZEUS_RUNTIME_ENV:-$ZEUS_BASE/zeus.env}"
AUTH_FILE="${ZEUS_AUTH_FILE:-$ZEUS_BASE/.zeus.auth.env}"
ZEUS_LOG="${ZEUS_LOG:-$ZEUS_BASE/log}"
ZEUS_CERT_DIR="${ZEUS_CERT_DIR:-$ZEUS_BASE/certs}"
DEFAULT_ENV="$APP_DIR/zeus.env.sample"
AUTH_TEMPLATE="$APP_DIR/.zeus.auth.env.sample"

mkdir -p "$ZEUS_BASE" "$ZEUS_LOG" "$ZEUS_CERT_DIR"
log() { echo "$(date +"%Y-%m-%d %H:%M:%S") - $*" | tee -a "$ZEUS_LOG/debug.log"; }

# Ensure helper scripts exist
for f in "$RESTART_MICRO" "$RESTART_UI"; do
  if [[ ! -x "$f" ]]; then
    log "ERROR: required script missing or not executable: $f"
    exit 1
  fi
done

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

log "Starting ZEUS backend..."
"$RESTART_MICRO" >> "$ZEUS_LOG/microservice.log" 2>&1 &
log "Starting ZEUS Streamlit..."
"$RESTART_UI" >> "$ZEUS_LOG/streamlit.log" 2>&1 &

touch "$ZEUS_LOG/.zeus_finished" || true
log "ZEUS startup complete."

# Keep PID1 alive if this is the entrypoint
if [[ "$$" -eq 1 ]]; then
  exec tail -f "$ZEUS_LOG/microservice.log" "$ZEUS_LOG/streamlit.log" 2>/dev/null
fi
