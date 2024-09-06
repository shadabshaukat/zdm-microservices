#!/bin/bash

# Function to log messages with timestamp
log_with_timestamp() {
    echo "$(date +"%Y-%m-%d %H:%M:%S") - $1" >> $ZEUS_LOG/debug.log
}

# Log the start of the script
log_with_timestamp "zeus.sh script started."

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

# Start ZEUS microservice
log_with_timestamp "Starting ZEUS microservice..."
exec python3 $HOME_DIR/zdm-microservices/main.py > $ZEUS_LOG/microservice.log 2>&1 &
touch $ZEUS_LOG/.zeus_finished
log_with_timestamp "zeus.sh script finished."
