
# ZEUS Docker Image for ZDM Microservice

This repository provides Dockerfiles and instructions for building and running a Podman container that installs and manages Oracle's Zero Downtime Migration (ZDM) software as a microservice called ZEUS.

## Prerequisites

- **Oracle Cloud Infrastructure (OCI) Registry**: Ensure the latest ZDM software is uploaded as an artifact.
- **ZDM Host**: A server with Podman installed, It's an instance running on OCI.

## Getting Started

Follow these steps to build and run the ZEUS Docker image.

### 1. Clone the Repository

* Clone the ZDM microservice repository to your ZDM host:

```
git@github.com:shadabshaukat/zdm-microservices.git
```

* Clone this Docker Image repository to your ZDM host:

```bash
git@github.com:shadabshaukat/zdm-docker.git
cd zdm-docker
```

### 2. Create Configuration Directories

Create two directories, `.oci` and `.ssh`, in the repository directory:

- **.oci**: Contains the OCI configuration file and API key for downloading the ZDM software from the OCI Registry artifact.
- **.ssh**: Contains SSH keys to access the source and target database hosts for ZDM migration.

```bash
mkdir .oci .ssh

# Example: Copy your OCI config and API key
cp /path/to/oci/config .oci/
cp /path/to/oci_api_key.pem .oci/

# Example: Copy your SSH keys
cp /path/to/id_rsa .ssh/
cp /path/to/id_rsa.pub .ssh/
```

### 3. Build the Oracle Linux Base Image

Build the Oracle Linux base image using the provided `Dockerfile.base`:

```bash
podman build --no-cache -t zdm-linux:latest -f Dockerfile.base .
```

Verify the image creation:

```bash
podman images
```

### 4. Create a Volume for ZDM Data

Create a Podman volume to store ZDM data:

```bash
podman volume create zdm_volume
```

### 5. Build the ZEUS Image

Build the ZEUS Docker image, which downloads the ZDM binary from the OCI Registry:

```bash
podman build --no-cache -t zeus:latest -f Dockerfile.zdm .
```

### 6. Run the ZEUS Container

Run the ZEUS container to install the ZDM software and start the ZEUS microservice, mount the local directory `zdm-microservices` to the ZEUS container.

```bash
podman run --userns=keep-id --network host -it --hostname zdm   -v /home/opc/zdm-microservices:/home/zdmuser/zdm-microservices:Z   -v zdm_volume:/u01:Z zeus
```

### 7. Set Up OCI Port Forwarding (If Required)

If ZDM host is in a private subnet and the host accessing the ZEUS application does not have direct access to the ZDM host, set up an OCI port forwarding session on port 8000 to the ZDM host:

```bash
ssh -i /path/to/ssh/key -N -L 8000:{ZDM_HOST_IP}:8000 -p 8000 {OCID_of_ZDM_HOST}@host.bastion.{OCI_REGION}.oci.oraclecloud.com
```

### 8. Access the ZEUS Application via a Web Browser

Once the ZEUS container is running, access the ZEUS application via the following URL:

```bash
http://127.0.0.1:8000/docs
```

This URL provides access to the API documentation and the ZEUS application interface.

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue.
