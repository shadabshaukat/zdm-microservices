#!/bin/bash
# Purpose: install and start ZDM. Do not source.
set -euo pipefail

# Required environment
: "${HOME_DIR:?HOME_DIR must be set}"
: "${ZDM_HOME:?ZDM_HOME must be set}"
: "${ZDM_BASE:?ZDM_BASE must be set}"
: "${ZDM_INSTALL_LOG:?ZDM_INSTALL_LOG must be set}"

LOG_DIR="$ZDM_INSTALL_LOG"
mkdir -p "$LOG_DIR"
log() { echo "$(date +"%Y-%m-%d %H:%M:%S") - $*" | tee -a "$LOG_DIR/zdm_install.log"; }
INSTALL_FLAG="$ZDM_BASE/.zdm_installed"

# Install if needed
if [[ ! -f "$INSTALL_FLAG" ]]; then
  log "Starting ZDM installation..."
  cd "$HOME_DIR"/unzipped/zdm* && \
    ./zdminstall.sh setup oraclehome="$ZDM_HOME" oraclebase="$ZDM_BASE" ziploc="$HOME_DIR"/unzipped/zdm*/zdm_home.zip -zdm >> "$LOG_DIR/zdm_install.log" 2>&1
  touch "$INSTALL_FLAG"
  log "ZDM installation completed."
else
  log "ZDM already installed; skipping install."
fi

# Start ZDM service
log "Starting ZDM service..."
"$ZDM_HOME"/bin/zdmservice start >> "$LOG_DIR/zdm_install.log" 2>&1 &
log "ZDM service start triggered."
