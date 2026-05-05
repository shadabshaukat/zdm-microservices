#!/bin/bash

set -euo pipefail

: "${HOME_DIR:?HOME_DIR must be set}"
: "${ZDM_HOME:?ZDM_HOME must be set}"
: "${ZDM_BASE:?ZDM_BASE must be set}"
: "${ZDM_INSTALL_LOG:?ZDM_INSTALL_LOG must be set}"
: "${ZDM_KIT_MOUNT:?ZDM_KIT_MOUNT must be set}"

LOG_DIR="$ZDM_INSTALL_LOG"
LOG_FILE="$LOG_DIR/zdm_install.log"
INSTALL_FLAG="$ZDM_BASE/.zdm_installed"

mkdir -p \
  "$LOG_DIR" \
  "$(dirname "$ZDM_HOME")" \
  "$ZDM_HOME" \
  "$ZDM_BASE"

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') - $*" | tee -a "$LOG_FILE"
}

is_zdm_installed() {
  [[ -x "${ZDM_HOME%/}/bin/zdmservice" ]]
}

log "install_zdm.sh started"
log "ZDM_HOME=$ZDM_HOME"
log "ZDM_BASE=$ZDM_BASE"
log "ZDM_KIT_MOUNT=$ZDM_KIT_MOUNT"
log "INSTALL_FLAG=$INSTALL_FLAG"

if [[ -f "$INSTALL_FLAG" ]] && is_zdm_installed; then
  log "ZDM already installed; skipping install."
  exit 0
fi

if [[ ! -f "$ZDM_KIT_MOUNT" ]]; then
  log "ERROR: ZDM kit not found at $ZDM_KIT_MOUNT"
  exit 1
fi

rm -rf "$HOME_DIR/unzipped"

log "Unzipping ZDM kit from $ZDM_KIT_MOUNT"
unzip -o "$ZDM_KIT_MOUNT" -d "$HOME_DIR/unzipped" >> "$LOG_FILE" 2>&1

kit_dir="$(find "$HOME_DIR/unzipped" -mindepth 1 -maxdepth 1 -type d -name 'zdm*' | head -n 1)"
if [[ -z "${kit_dir:-}" ]]; then
  log "ERROR: extracted ZDM kit directory not found under $HOME_DIR/unzipped"
  exit 1
fi

installer="$kit_dir/zdminstall.sh"
zip_loc="$kit_dir/zdm_home.zip"

if [[ ! -x "$installer" ]]; then
  log "ERROR: installer not found or not executable: $installer"
  exit 1
fi

if [[ ! -f "$zip_loc" ]]; then
  log "ERROR: zdm_home.zip not found: $zip_loc"
  exit 1
fi

log "Starting ZDM installation..."
log "KIT_DIR=$kit_dir"
log "INSTALLER=$installer"
log "ZIP_LOC=$zip_loc"

(
  cd "$kit_dir"
  ./zdminstall.sh setup \
    oraclehome="$ZDM_HOME" \
    oraclebase="$ZDM_BASE" \
    ziploc="$zip_loc" \
    -zdm >> "$LOG_FILE" 2>&1
)

if ! is_zdm_installed; then
  log "ERROR: installation completed but expected binary is missing: ${ZDM_HOME%/}/bin/zdmservice"
  exit 1
fi

mkdir -p "$ZDM_BASE"
touch "$INSTALL_FLAG"

log "ZDM installation completed successfully."
