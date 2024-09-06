#!/bin/bash

# Load environment variables from .env file
set -a
source .env
set +a

# Build the image with build arguments from the .env file
podman build --build-arg ZDM_USER=$ZDM_USER --build-arg ZDM_GROUP=$ZDM_GROUP --build-arg HOME_DIR=$HOME_DIR --build-arg ARTIFACT_ID=$ARTIFACT_ID --build-arg HOSTNAME=$HOSTNAME --build-arg ZDM_HOME=$ZDM_HOME --build-arg ZDM_BASE=$ZDM_BASE --build-arg ZEUS_LOG=$ZEUS_LOG --build-arg PATH=$PATH --format docker -t zeus:latest .

# Create ZDM Volume to store ZDM binary and data
podman volume create zdm_volume
