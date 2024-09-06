#!/bin/bash

# Path to the .hosts file
HOSTS_FILE=".hosts"

# Initialize an empty string to hold the add-host options
ADD_HOST_FLAGS=""

# Read the .hosts file line by line
while IFS=' ' read -r ip fqdn hostname; do
  # Append the --add-host flag for each hostname
  ADD_HOST_FLAGS+="--add-host $hostname:$ip "
done < "$HOSTS_FILE"

# Build the final podman run command
CMD="podman run --userns=keep-id --network host -d --hostname zdm -v zdm_volume:/u01:Z $ADD_HOST_FLAGS --name zeus zeus"

# Print the command to be executed
echo "Executing command: $CMD"

# Execute the command
$CMD
