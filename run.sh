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

for _ in {1..30}; do
  if podman ps --filter "name=^${CONTAINER_NAME}$" --format '{{.Status}}' 2>/dev/null | grep -q '^Up'; then
    if podman exec "$CONTAINER_NAME" /bin/bash -lc 'zdmservice status 2>/dev/null | grep -q "Running:[[:space:]]*true"' 2>/dev/null; then
      break
    fi
  fi
  sleep 1
done

for _ in {1..20}; do
  if podman exec "$CONTAINER_NAME" /bin/bash -lc "ps -ef | grep -E 'python|streamlit' | grep -v grep" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

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
podman exec "$CONTAINER_NAME" /bin/bash -lc "ps -ef | grep -E 'python|streamlit' | grep -v grep" 2>/dev/null || true
