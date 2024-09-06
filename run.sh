#!/bin/bash

# Create the container with the built image created from build.sh
podman run --userns=keep-id --network host -d --hostname zdm -v zdm_volume:/u01:Z --name zeus zeus
