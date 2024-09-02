#!/bin/bash

# Run the ZDM installation script
cd $HOME_DIR/unzipped/zdm* && \
    ./zdminstall.sh setup oraclehome=$ZDM_HOME oraclebase=$ZDM_BASE ziploc=$HOME_DIR/unzipped/zdm*/zdm_home.zip -zdm > $HOME_DIR/zdm_install_log.txt 2>&1

# Start ZDM service
echo "Starting ZDM service..." >> /home/zdmuser/debug.log
$ZDM_HOME/bin/zdmservice start &

# Start ZEUS microservice
echo "Starting ZEUS microservice..." >> /home/zdmuser/debug.log
exec python3 $HOME_DIR/zdm-microservices/main.py > $HOME_DIR/microservice.log 2>&1
