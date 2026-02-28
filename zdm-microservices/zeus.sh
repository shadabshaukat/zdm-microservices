#!/bin/bash
# Run, do not source: preserves caller shell options.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    echo "Please execute, not source: $0" >&2
    return 1
fi

HOME_DIR="${HOME_DIR:-/home/zdmuser}"
APP_DIR="${HOME_DIR}/zdm-microservices"
ZEUS_BASE="${ZEUS_BASE:-/u01/zeus}"
RUNTIME_ENV="${ZEUS_RUNTIME_ENV:-$ZEUS_BASE/zeus.env}"
DEFAULT_ENV="$APP_DIR/zeus.env.sample"
AUTH_FILE="${ZEUS_AUTH_FILE:-$ZEUS_BASE/.zeus.auth.env}"
AUTH_TEMPLATE="$APP_DIR/.zeus.auth.env.sample"
ZEUS_LOG="${ZEUS_LOG:-/u01/log}"
mkdir -p "$ZEUS_LOG"

# Function to log messages with timestamp
log_with_timestamp() {
    echo "$(date +"%Y-%m-%d %H:%M:%S") - $1" >> "$ZEUS_LOG/debug.log"
}

# Ensure TLS cert/key exist; generate self-signed with SAN if missing.
ensure_certs() {
    local cert_dir="${ZEUS_CERT_DIR:-$ZEUS_BASE/certs}"
    local cert_path="$cert_dir/zeus.crt"
    local key_path="$cert_dir/zeus.key"

    mkdir -p "$cert_dir"

    if [[ -f "$cert_path" && -f "$key_path" ]]; then
        log_with_timestamp "TLS cert/key already present at $cert_path and $key_path"
        return
    fi

    if ! command -v openssl >/dev/null 2>&1; then
        log_with_timestamp "ERROR: openssl not found; cannot generate TLS cert."
        exit 1
    fi

    log_with_timestamp "Generating self-signed TLS cert with SAN for localhost/127.0.0.1"
    openssl req -x509 -newkey rsa:4096 -nodes \
        -keyout "$key_path" \
        -out "$cert_path" \
        -days 365 \
        -subj "/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" \
        > "$ZEUS_LOG/openssl_generate_cert.log" 2>&1

    chmod 600 "$key_path" || true
    chmod 644 "$cert_path" || true
    log_with_timestamp "Generated TLS cert/key at $cert_path and $key_path"
}

# Prepare runtime env file under /u01 (persistent)
mkdir -p "$(dirname "$RUNTIME_ENV")"
[ ! -f "$RUNTIME_ENV" ] && [ -f "$DEFAULT_ENV" ] && cp "$DEFAULT_ENV" "$RUNTIME_ENV"

# Export runtime env (ports/certs/etc.)
set -a
[ -f "$RUNTIME_ENV" ] && { set +u; source "$RUNTIME_ENV"; set -u; }
ZEUS_AUTH_FILE="$AUTH_FILE"
set +a

# Ensure auth file exists in /u01
if [[ ! -f "$AUTH_FILE" ]]; then
    mkdir -p "$(dirname "$AUTH_FILE")"
    if [[ -f "$AUTH_TEMPLATE" ]]; then
        cp "$AUTH_TEMPLATE" "$AUTH_FILE"
    else
        cat > "$AUTH_FILE" <<'EOF'
# ZEUS API auth users (plain text). Change defaults immediately.
ZEUS_API_USER_1=zdmuser
ZEUS_API_USER_1_PASSWORD=ChangeMe123#_
EOF
    fi
    chmod 600 "$AUTH_FILE" || true
    log_with_timestamp "Created default API auth file at $AUTH_FILE; please change credentials."
fi

# Log the start of the script
log_with_timestamp "zeus.sh script started."

# Ensure certs exist before starting services
ensure_certs

# Check if the ZDM installation has already been done
if [ ! -f $ZEUS_LOG/.zdm_installed ]; then
    log_with_timestamp "Starting ZDM installation..."

    # Run the ZDM installation script
    cd $HOME_DIR/unzipped/zdm* && \
    ./zdminstall.sh setup oraclehome=$ZDM_HOME oraclebase=$ZDM_BASE ziploc=$HOME_DIR/unzipped/zdm*/zdm_home.zip -zdm > $ZEUS_LOG/zdm_install_log.txt 2>&1

    # Create a flag file to indicate that the installation has been completed
    touch $ZEUS_LOG/.zdm_installed
    log_with_timestamp "ZDM installation completed and flag file created."

else
    log_with_timestamp "ZDM is already installed, skipping installation."
fi


# Start ZDM service
log_with_timestamp "Starting ZDM service..."
$ZDM_HOME/bin/zdmservice start &
log_with_timestamp "ZDM service started."

# Start ZEUS microservice via restart script
log_with_timestamp "Starting ZEUS microservice (restart script)..."
$APP_DIR/restart_microservice.sh >> $ZEUS_LOG/microservice.log 2>&1 &

# Start Streamlit UI via restart script
log_with_timestamp "Starting Streamlit UI (restart script)..."
$APP_DIR/restart_streamlit.sh >> $ZEUS_LOG/streamlit.log 2>&1 &

touch $ZEUS_LOG/.zeus_finished
log_with_timestamp "zeus.sh script finished."

# Keep PID1 alive if invoked as container entrypoint
if [[ "$$" -eq 1 ]]; then
    exec tail -f "$ZEUS_LOG/streamlit.log" "$ZEUS_LOG/microservice.log" 2>/dev/null
fi
