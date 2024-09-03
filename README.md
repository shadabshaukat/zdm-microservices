# ZEUS (ZDM Enqueue URL Services)

An API driven Control plane for Oracle Zero Downtime Migration Tool. Built with FastAPI


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

mv zdm-microservices zdm-docker/

cd zdm-docker
```

### 2. Create Configuration Directories

Create two directories, `.oci` and `.ssh`, in the repository directory of zdm_docker:

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

### 4. Build the ZEUS Image

Build the ZEUS Docker image, which downloads the ZDM binary from the OCI Registry:

```bash
podman build --no-cache -t zeus:latest -f Dockerfile.zdm .
```

### 5. Create a Volume for ZDM Data

Create a Podman volume to store ZDM data:

```bash
podman volume create zdm_volume
```

### 6. Run the ZEUS Container

Run the ZEUS container to install the ZDM software and start the ZEUS microservice, mount zdm data volume to the ZEUS container.

```bash
--start the container
[opc@tools2 zdm-docker]$ podman run --userns=keep-id --network host -d --hostname zdm -v zdm_volume:/u01:Z zeus
cc2ac39301e294ffd742c98149b5186de8474064dba1abbab9c874faba26828a

[opc@tools2 zdm-docker]$ podman ps -a
CONTAINER ID  IMAGE                  COMMAND               CREATED        STATUS        PORTS       NAMES
cc2ac39301e2  localhost/zeus:latest  /home/zdmuser/zeu...  4 minutes ago  Up 2 minutes              charming_ritchie

[opc@tools2 zdm-docker]$ podman exec -it cc2ac39301e2 /bin/bash
[zdmuser@zdm ~]$ zdmservice status

---------------------------------------
	Service Status
---------------------------------------

 Running: 	false
 Tranferport:
 Conn String: 	jdbc:mysql://localhost:8899/
 RMI port: 	8897
 HTTP port: 	8898
 Wallet path: 	/u01/app/zdmbase/crsdata/zdm/security

[zdmuser@zdm ~]$ tail -f microservice.log
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)

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

