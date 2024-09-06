# ZEUS (ZDM Enqueue URL Services)

An API driven Control plane for Oracle Zero Downtime Migration Tool. Built with FastAPI

## Project Structure

```
.
├── zdm-microservices/      # Directory containing ZDM microservice code and configs
│   ├── main.py
│   ├── requirements.txt
│   ├── zdm.env
│   └── zeus.sh
├── .oci/                   # OCI configuration files, including API keys
├── .env                    # Environment variables for ZDM setup
├── .hosts                  # hosts entry for ZDM Migration job
├── Dockerfile              # Dockerfile to build the ZDM environment
├── build.sh                # Script to automate the ZDM image build process
└── run.sh                  # Script to automate the creation of the ZDM container

```

# ZEUS Docker Image for ZDM Microservice

This repository provides Dockerfiles and instructions for building and running a Podman container that installs and manages Oracle's Zero Downtime Migration (ZDM) software as a microservice called ZEUS.

## Prerequisites

- **ZDM Host** A server with Podman installed, It's an instance running on OCI.
- **Oracle Cloud Infrastructure (OCI) Registry**  Ensure the latest ZDM software is uploaded as an artifact. Make note of the OCID of the artifact.
- **OCI User** Following the principle of least privilege, create a dedicated OCI user with read-only access to the specified artifact in the OCI Artifact Registry repository.

## Build Process
Follow these steps to build and run the ZEUS Docker image.

1. **Clone the Repository**
   Clone the repository to your local machine:
   ```bash
   mkdir zeus
   cd zeus
   git clone <repo-url> .
   ```

2. **Set Up Environment Variables**
   Ensure that the `.env` file is set up with the required environment variables for the build. Example:

   ```bash
   # .env file
   
   # Environment variables
   ZDM_USER="zdmuser"
   ZDM_GROUP="zdm"
   HOME_DIR="/u01/zdmuser"
   ARTIFACT_ID="ocid1.genericartifact.oc1.ap-hyderabad-1.0.amaaaaaap77apcqaxu2byf5uwr5wccba3l4u4emx3wurknaipanzd5amvajq"
   HOSTNAME="zdm"
   ZDM_HOME="/u01/app/zdmhome"
   ZDM_BASE="/u01/app/zdmbase"
   ZEUS_LOG="/u01/log"
   ```

3. **Create Configuration Directories**
Create directory `.oci` in the repository directory. It contains the OCI configuration file and API key for downloading the ZDM software from the OCI Registry artifact.

```bash
mkdir .oci 

# Example: Copy your OCI config and API key
cp /path/to/oci/config .oci/
cp /path/to/oci_api_key.pem .oci/

```

4. **Build the ZEUS Image and Create Docker Volume**
   Run the build script to create the container image. This will download required ZDM artifacts, set up the environment, and install dependencies. It will also create a Docker Volume after the image is built:

   ```bash
   ./build.sh
   ```

   Alternatively, you can directly run commands seperately as below

   ```bash
   podman build --build-arg ZDM_USER=$ZDM_USER --build-arg ZDM_GROUP=$ZDM_GROUP --build-arg HOME_DIR=$HOME_DIR --build-arg ARTIFACT_ID=$ARTIFACT_ID --build-arg HOSTNAME=$HOSTNAME --build-arg ZDM_HOME=$ZDM_HOME --build-arg ZDM_BASE=$ZDM_BASE --build-arg ZEUS_LOG=$ZEUS_LOG -t zeus:latest .
   ```

   ```bash
   podman volume create zdm_volume
   ```

## Running The Container

1. **DB Hosts Naming Resolution Configuration** (Optional)
   It is required only if  DNS server naming resolution is not available. `hosts` file has to be used for DNS name resolution of source and target DB server name and SCAN name. 

   ```bash
   # .hosts file
   192.168.1.3 abc.domain abc
   192.168.1.4 efg.domain efg
   192.168.1.10 abc-scan.domain abc-scan
   192.168.1.10 efg-scan.domain efg-scan

   ```

2. **Run the Container**
   Once the image is built, use the `run.sh` script to start the container. This script runs the container with the correct configuration, mounts, and environment variables.
   ```bash
   ./run.sh
   ```

   Alternatively, you can directly run:

   ```bash
   podman run --userns=keep-id --network host -d --hostname zdm -v zdm_volume:/u01:Z --name zeus zeus
   ```

   The container will start in the background. 

3. **Stop and Remove the Container:**

   You can stop and remove the container with a single command:

   ```bash
   podman rm -f zeus
   ```

## Enable OCI Port Forwarding (Optional)

If ZDM host is in a private subnet and the host accessing the ZEUS application does not have direct access to the ZDM host, establish an OCI port forwarding bastion session on port 8000 to the ZDM host:

Example:
```bash
ssh -i /path/to/ssh/key -N -L 8000:{ZDM_HOST_IP}:8000 -p 8000 {OCID_of_ZDM_HOST}@host.bastion.{OCI_REGION}.oci.oraclecloud.com
```

### 8. Access the ZEUS Application via a Web Browser

Once the ZEUS container is running, access the ZEUS application via the following URL:

```bash
http://127.0.0.1:8000/docs
```

This URL provides access to the API documentation and the ZEUS application interface.

## Logs and Debugging

Logs are stored in the `/u01/log` directory, which can be accessed within the container.

### Logs Directory

```bash
[zdmuser@zdm log]$ ls -al
total 16
drwxr-xr-x. 2 zdmuser zdm    96 Sep  5 10:59 .
drwxr-xr-x. 4 root    root   28 Sep  5 10:19 ..
-rw-r--r--. 1 zdmuser zdm     0 Sep  5 10:36 .zdm_installed
-rw-r--r--. 1 zdmuser zdm  3295 Sep  5 12:25 debug.log
-rw-r--r--. 1 zdmuser zdm   193 Sep  5 12:25 microservice.log
-rw-r--r--. 1 zdmuser zdm  4398 Sep  5 12:04 zdm_install_log.txt
```

- **debug.log**: Contains logs related to starting services.
- **microservice.log**: Contains logs related to the ZEUS microservice.
- **zdm_install_log.txt**: Logs generated during the installation of ZDM.

### Example Logs:

```bash
# Debug log
2024-09-05 12:16:30 - Starting ZDM service...
2024-09-05 12:16:30 - ZDM service started.
2024-09-05 12:16:30 - Starting ZEUS microservice...
2024-09-05 12:16:30 - zeus.sh script finished.
```

```bash
# Microservice log
INFO:     Started server process [14]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

```bash
# ZDM installation log
ZDM kit home: /home/zdmuser/unzipped/zdm21.4.9
/home/zdmuser/unzipped/zdm21.4.9
---------------------------------------
Validating zip file...
---------------------------------------
       25  08-30-2024 18:38   rhp/zdm.build
---------------------------------------
Unzipping shiphome to home...
---------------------------------------
/u01/app/zdmhome is not empty...
```

## ZEUS Script Overview

The `zeus.sh` script is responsible for:
- Installing ZDM (if not already installed).
- Starting the ZDM service.
- Starting the ZEUS microservice.

### Health Check

A health check has been added to ensure the `zeus.sh` script completes successfully. 

You can check STATUS of the podman container using below command:

```
[opc@tools2 zdm-docker-v3]$ podman ps -a
CONTAINER ID  IMAGE                  COMMAND               CREATED         STATUS                   PORTS       NAMES
7cecddeb2424  localhost/zeus:latest  /bin/bash -c /hom...  15 minutes ago  Up 13 minutes (healthy)              zeus
```

The health check looks for a file `.zeus_finished` in the `$ZEUS_LOG` directory.

```bash
HEALTHCHECK --interval=10s --timeout=5s --start-period=600s --retries=3 CMD test -f $ZEUS_LOG/.zeus_finished || exit 1
```

## Conclusion

This setup provides a complete environment for running ZEUS microservices and ZDM tools inside a containerized environment using Oracle Linux. Logs can be accessed to track the installation and service processes.

For troubleshooting, check the log files inside `/u01/log`.

#######################################################################################

# Manual Deploy with Python36

Minimum Python3.6 required

```
git clone https://github.com/shadabshaukat/zdm-microservices.git && cd zdm-microservices
```

Make sure the ZDM_HOME is set for the user which deploys this, preferably ‘zdmuser’.

Change the values in zdm.env as per your environment

```
source zdm.env

echo $ZDM_HOME
```

```
pip3 install -r requirements.txt
```

```
python3 main.py
```


# API's

Available API routes:

```
[
'/openapi.json',
 '/docs',
 '/docs/oauth2-redirect',
 '/redoc',
 '/eval',
 '/migratedb/physical',
 '/query/{jobid}',
 '/resume/{jobid}',
 '/resume_pauseagain/{jobid}'
 '/ReadJobLog',
 '/createResponseFile',
'/OraPKICreateWallet',
'/MkstoreCreateCredential',
'/abort/{jobid}',
'/suspend/{jobid}'
]
```


## 1. Run Evaluation 
```
curl -X POST "http://127.0.0.1:8000/eval" \
     -H "Content-Type: application/json" \
     -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
     -d '{
           "sourcedb": "MOBUAT",
           "sourcenode": "gdx7db01vm01-mgmt",
           "srcauth": "zdmauth",
           "srcarg1": "user:SVC_OCIMIG",
           "srcarg2": "identity_file:/home/zdmuser/.ssh/id_rsa",
           "srcarg3": "sudo_location:/usr/bin/sudo",
           "targetnode": "aeocidb01vn-4hja81",
           "tgtauth": "zdmauth",
           "tgtarg1": "user:opc",
           "tgtarg2": "identity_file:/home/zdmuser/.ssh/id_rsa",
           "tgtarg3": "sudo_location:/usr/bin/sudo",
           "rsp": "/home/zdmuser/migration/MOBUAT/MOBUAT.rsp",
           "sourcesyswallet": "/home/zdmuser/migration/sysWallet_11g_v2",
           "ignore": "PATCH_CHECK"
         }'
```
## 2. Get Job Status 
```
curl -X GET "http://127.0.0.1:8000/query/25" \
     -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" | jq .
```
OR
```
echo -n 'zdmuser:YourPassword123#_' | base64

curl -X GET "http://127.0.0.1:8000/query/25" \
     -H "Authorization: Basic emRtdXNlcjpZb3VyUGFzc3dvcmQxMjMjXw==" | jq .
```

## 3. DB Migration 
```
curl -X POST "http://127.0.0.1:8000/migratedb/physical" \
     -H "Content-Type: application/json" \
     -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
     -d '{
      "sourcedb": "GISTSTDB",
      "sourcenode": "19c_vmcluster_node1_src",
      "srcauth": "zdmauth",
      "srcarg1": "user:SVC_OCIMIG",
      "srcarg2": "identity_file:/home/zdmuser/.ssh/id_rsa",
      "srcarg3": "sudo_location:/usr/bin/sudo",
      "targetnode": "aeocidb01vn-4hja81",
      "tgtauth": "zdmauth",
      "tgtarg1": "user:opc",
      "tgtarg2": "identity_file:/home/zdmuser/.ssh/id_rsa",
      "tgtarg3": "sudo_location:/usr/bin/sudo",
      "rsp": "/tmp/GISTSTDB.rsp",
      "sourcesyswallet": "/home/zdmuser/migration/19cwallet_nonprod",
      "ignore": ["PATCH_CHECK"],
      "pauseafter": "ZDM_CONFIGURE_DG_SRC"
         }'
```

## 4. Resume Job 

```
curl -X POST "http://localhost:8000/resume/<jobid>" -u zdmuser:YourPassword123#_
```

## 5. Resume Job with Pause Again 

```
curl -X POST "http://localhost:8000/resume_pauseagain/<jobid>" -u zdmuser:YourPassword123#_ -H "Content-Type: application/json" -d '{
    "skip": "SWITCHOVER"
}'
```

```
curl -X POST "http://localhost:8000/resume_pauseagain/<jobid>" -u zdmuser:YourPassword123#_ -H "Content-Type: application/json" -d '{
    "pauseafter": "ZDM_CONFIGURE_DG_SRC"
}'
```

## 6. Create Response File 

```
curl -X POST "http://your-fastapi-server-address/createResponseFile" \
    -u zdmuser:YourPassword123#_ \
    -H "Content-Type: application/json" \
    -d '{
          "filename": "MOBUAT",
          "TGT_DB_UNIQUE_NAME": "MOBUAT_733_syd",
          "MIGRATION_METHOD": "ONLINE_PHYSICAL",
          "DATA_TRANSFER_MEDIUM": "DIRECT",
          "PLATFORM_TYPE": "EXACS",
          "NONCDBTOPDB_CONVERSION": "FALSE",
          "NONCDBTOPDB_SWITCHOVER": "TRUE",
          "TGT_SKIP_DATAPATCH": "TRUE",
          "SRC_RMAN_CHANNELS": 4,
          "TGT_RMAN_CHANNELS": 10,
          "ZDM_RMAN_DIRECT_METHOD": "ACTIVE_DUPLICATE",
          "ZDM_USE_DG_BROKER": "FALSE",
          "ZDM_TGT_UPGRADE_TIMEZONE": "FALSE",
          "ZDM_SKIP_TDE_WALLET_MIGRATION": "FALSE"
    }'

```

## 7. Read Job Log 

```
curl -X POST "http://<your_server_ip>:8000/ReadJobLog" \
-H "Content-Type: application/json" \
-u zdmuser:YourPassword123#_ \
-d '{
    "file_path": "/u01/app/zdmbase/chkbase/scheduled/job-38-2024-07-01-12:59:26.log"
}'

```

## 8. Create Oracle Wallet - ORAPKI

```
curl -X POST "http://your_server_address/OraPKICreateWallet" \
-u zdmuser:YourPassword123#_ \
-H "Content-Type: application/json" \
-d '{
  "wallet_path": "/home/zdmuser/migration/19cwallet_nonprod"
}'
```

## 9. Create Credential - MKSTORE

```
curl -X POST "http://your_server_address/MkstoreCreateCredential" \
-u zdmuser:YourPassword123#_ \
-H "Content-Type: application/json" \
-d '{
  "wallet_path": "/home/zdmuser/migration/19cwallet_nonprod",
  "user": "sysuser",
  "password": "yourpassword1234#"
}'
```

## 10. Abort Job

```
curl -X POST "http://localhost:8000/abort/<jobid>" -u zdmuser:YourPassword123#_
```

## 11. Suspend Job

```
curl -X POST "http://localhost:8000/suspend/<jobid>" -u zdmuser:YourPassword123#_
```


# Coming Soon #

- ZDM Microservices Hardening
- Release of v1

