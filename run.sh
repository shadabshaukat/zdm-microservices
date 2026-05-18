#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="zeus.service"
ENV_FILE="$ROOT_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: .env file not found at $ENV_FILE" >&2
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

CONTAINER_NAME="${CONTAINER_NAME:-zeus}"
CONTAINER_HOSTNAME="${CONTAINER_HOSTNAME:-zdm}"
IMAGE_NAME="${IMAGE_NAME:-zeus:latest}"
VOLUME_NAME="${VOLUME_NAME:-zdm_volume}"

HOME_DIR="${HOME_DIR:?HOME_DIR must be set in .env}"
ZDM_HOME="${ZDM_HOME:?ZDM_HOME must be set in .env}"
ZDM_BASE="${ZDM_BASE:?ZDM_BASE must be set in .env}"
ZDM_INSTALL_LOG="${ZDM_INSTALL_LOG:?ZDM_INSTALL_LOG must be set in .env}"

ZDM_KIT_PATH="${ZDM_KIT_PATH:-}"
ZDM_KIT_MOUNT="${ZDM_KIT_MOUNT:-/mnt/zdm/zdm.zip}"

ZDM_SERVICE_BIN="${ZDM_HOME%/}/bin/zdmservice"

if ! loginctl show-user "$USER" -p Linger 2>/dev/null | grep -q 'Linger=yes'; then
  echo "Linger is not enabled for user $USER."
  echo "Please run the following command once, then rerun this script:"
  echo
  echo "  sudo loginctl enable-linger $USER"
  echo
  exit 1
fi

podman volume inspect "$VOLUME_NAME" >/dev/null 2>&1 || podman volume create "$VOLUME_NAME" >/dev/null

COMMON_RUN_ARGS=(
  --userns=keep-id
  --hostname "$CONTAINER_HOSTNAME"
  -v "${VOLUME_NAME}:/u01:Z"
)

has_existing_zdm() {
  podman run --rm \
    "${COMMON_RUN_ARGS[@]}" \
    "$IMAGE_NAME" \
    bash -lc "test -x '$ZDM_SERVICE_BIN'"
}

if has_existing_zdm; then
  echo "Existing ZDM installation found in volume '$VOLUME_NAME' at $ZDM_SERVICE_BIN"
else
  if [[ -z "$ZDM_KIT_PATH" ]]; then
    echo "Error: no existing ZDM installation found in volume '$VOLUME_NAME' at $ZDM_SERVICE_BIN"
    echo "Please set ZDM_KIT_PATH in .env or export it before running ./run.sh"
    exit 1
  fi

  if [[ ! -f "$ZDM_KIT_PATH" ]]; then
    echo "Error: ZDM kit file not found: $ZDM_KIT_PATH"
    exit 1
  fi

  echo "No existing ZDM installation found. Running one-time installer..."

  podman run --rm \
    "${COMMON_RUN_ARGS[@]}" \
    -v "${ZDM_KIT_PATH}:${ZDM_KIT_MOUNT}:ro,Z" \
    -e "HOME_DIR=$HOME_DIR" \
    -e "ZDM_HOME=$ZDM_HOME" \
    -e "ZDM_BASE=$ZDM_BASE" \
    -e "ZDM_INSTALL_LOG=$ZDM_INSTALL_LOG" \
    -e "ZDM_KIT_MOUNT=$ZDM_KIT_MOUNT" \
    "$IMAGE_NAME" \
    /bin/bash /home/zdmuser/install_zdm.sh

  if ! has_existing_zdm; then
    echo "Error: ZDM installation step completed but expected binary is still missing or not executable at $ZDM_SERVICE_BIN"
    exit 1
  fi

  echo "ZDM installation verified successfully."
fi

"$ROOT_DIR/install-service.sh"

systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME" >/dev/null

if systemctl --user is-active --quiet "$SERVICE_NAME" &&
   podman ps --filter "name=^${CONTAINER_NAME}$" --format '{{.Status}}' | grep -q '^Up'; then
  echo "ZEUS service and container are already running."
else
  echo "Starting or restarting ZEUS service..."
  systemctl --user stop "$SERVICE_NAME" >/dev/null 2>&1 || true
  podman rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  systemctl --user reset-failed "$SERVICE_NAME" >/dev/null 2>&1 || true
  systemctl --user start "$SERVICE_NAME"
fi

echo
echo "Waiting for ZEUS startup..."

zdm_ready=false
for _ in {1..30}; do
  if podman ps --filter "name=^${CONTAINER_NAME}$" --format '{{.Status}}' 2>/dev/null | grep -q '^Up'; then
    if podman exec "$CONTAINER_NAME" /bin/bash -lc 'zdmservice status 2>/dev/null | grep -q "Running:[[:space:]]*true"' 2>/dev/null; then
      zdm_ready=true
      break
    fi
  fi
  sleep 1
done

if [[ "$zdm_ready" != true ]]; then
  echo "Error: ZDM service did not become ready in container '$CONTAINER_NAME'." >&2
  podman logs --tail 120 "$CONTAINER_NAME" 2>/dev/null || true
  exit 1
fi

zeus_ready=false
for _ in {1..120}; do
  if podman exec "$CONTAINER_NAME" /bin/bash -lc '
    set -e
    ZEUS_BASE="${ZEUS_BASE:-/u01/data/zeus}"
    RUNTIME_ENV="${ZEUS_RUNTIME_ENV:-$ZEUS_BASE/zeus.env}"
    if [[ -f "$RUNTIME_ENV" ]]; then
      set -a
      source "$RUNTIME_ENV"
      set +a
    fi
    ZEUS_PORT="${ZEUS_PORT:-8001}"
    ZEUS_CERT_DIR="${ZEUS_CERT_DIR:-$ZEUS_BASE/certs}"
    curl --cacert "$ZEUS_CERT_DIR/zeus.crt" -skf "https://127.0.0.1:${ZEUS_PORT}/health" >/dev/null
  ' >/dev/null 2>&1; then
    zeus_ready=true
    break
  fi
  sleep 1
done

if [[ "$zeus_ready" != true ]]; then
  echo "Error: ZEUS health endpoint did not become ready in container '$CONTAINER_NAME'." >&2
  podman logs --tail 120 "$CONTAINER_NAME" 2>/dev/null || true
  exit 1
fi

echo
echo "=== systemd unit ==="
systemctl --user status --no-pager --lines=10 "$SERVICE_NAME" || true

echo
echo "=== container status ==="
podman ps -a --filter "name=^${CONTAINER_NAME}$" || true

echo
echo "=== recent container logs ==="
podman logs --tail 80 "$CONTAINER_NAME" 2>/dev/null || true

echo
echo "=== quick checks ==="
podman exec "$CONTAINER_NAME" /bin/bash -lc 'zdmservice status' 2>/dev/null || true
podman exec "$CONTAINER_NAME" /bin/bash -lc "ps -ef | grep -E 'zdm-microservices/main.py' | grep -v grep" 2>/dev/null || true
podman exec "$CONTAINER_NAME" /bin/bash -lc '
  ZEUS_BASE="${ZEUS_BASE:-/u01/data/zeus}"
  RUNTIME_ENV="${ZEUS_RUNTIME_ENV:-$ZEUS_BASE/zeus.env}"
  if [[ -f "$RUNTIME_ENV" ]]; then
    set -a
    source "$RUNTIME_ENV"
    set +a
  fi
  ZEUS_PORT="${ZEUS_PORT:-8001}"
  ZEUS_CERT_DIR="${ZEUS_CERT_DIR:-$ZEUS_BASE/certs}"
  curl --cacert "$ZEUS_CERT_DIR/zeus.crt" -skf "https://127.0.0.1:${ZEUS_PORT}/health"
' 2>/dev/null || true
