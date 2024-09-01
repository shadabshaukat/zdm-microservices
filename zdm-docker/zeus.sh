#!/bin/bash

# Run the ZDM installation script
cd $HOME_DIR/unzipped/zdm* && \
	./zdminstall.sh setup oraclehome=$ZDM_HOME oraclebase=$ZDM_BASE ziploc=$HOME_DIR/unzipped/zdm*/zdm_home.zip -zdm >$HOME_DIR/zdm_install_log.txt 2>&1

# Install Python packages from requirements.txt
sudo pip3 install -r $HOME_DIR/zdm-microservices/requirements.txt
sudo pip3 install --upgrade typing_extensions

# start ZDM service and microservice
$ZDM_HOME/bin/zdmservice start
nohup python3 $HOME_DIR/zdm-microservices/main.py &

# Start bash
exec /bin/bash

