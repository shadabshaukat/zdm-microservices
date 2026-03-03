#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$ROOT_DIR/.env"
LOCAL_KIT_DIR="$ROOT_DIR/.local_zdm"
LOCAL_KIT_NAME="zdm.zip"
LOCAL_KIT_IN_CONTEXT="$LOCAL_KIT_DIR/$LOCAL_KIT_NAME"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: .env file not found at $ENV_FILE" >&2
  exit 1
fi

cd "$ROOT_DIR"

# Load environment variables from .env file
set -a
source "$ENV_FILE"
set +a

ZDM_KIT_PATH="${ZDM_KIT_PATH:-}"
copied_local_kit="false"

mkdir -p "$LOCAL_KIT_DIR" "$ROOT_DIR/.oci"

cleanup_local_kit() {
  if [[ "$copied_local_kit" == "true" ]]; then
    rm -f "$LOCAL_KIT_IN_CONTEXT"
  fi
}
trap cleanup_local_kit EXIT

if [[ -n "$ZDM_KIT_PATH" ]]; then
  if [[ ! -f "$ZDM_KIT_PATH" ]]; then
    echo "Error: ZDM_KIT_PATH file not found: $ZDM_KIT_PATH" >&2
    exit 1
  fi
  cp "$ZDM_KIT_PATH" "$LOCAL_KIT_IN_CONTEXT"
  copied_local_kit="true"
fi

# Require local kit present
if [[ ! -f "$LOCAL_KIT_IN_CONTEXT" ]]; then
  echo "Error: local kit not found. Set ZDM_KIT_PATH to point to zdm.zip (it will be copied to .local_zdm/zdm.zip)." >&2
  exit 1
fi

podman build \
  --build-arg ZDM_USER="$ZDM_USER" \
  --build-arg ZDM_GROUP="$ZDM_GROUP" \
  --build-arg HOME_DIR="$HOME_DIR" \
  --build-arg HOSTNAME="$HOSTNAME" \
  --build-arg ZDM_HOME="$ZDM_HOME" \
  --build-arg ZDM_BASE="$ZDM_BASE" \
  --build-arg ZDM_INSTALL_LOG="$ZDM_INSTALL_LOG" \
  --build-arg ZEUS_DATA="$ZEUS_DATA" \
  --build-arg ZEUS_BASE="$ZEUS_BASE" \
  --build-arg PATH="$PATH" \
  --format docker \
  -t zeus:latest .

podman volume inspect zdm_volume >/dev/null 2>&1 || podman volume create zdm_volume
