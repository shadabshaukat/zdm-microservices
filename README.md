# ZDM MicroServices

An API driven Control plane for Oracle Zero Downtime Migration Tool. Built with FastAPI

# Deploy

```
git clone https://github.com/shadabshaukat/zdm-microservices.git && cd zdm-microservices
```

Make sure the ZDM_HOME is set for the user which deploys this, preferably ‘zdmuser’.

Change the values in zdm.env as per your environment

```
source zdm.env
```

```
pip3 install -r requirements.txt
```

```
uvicorn main:app —reload
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
           "sourcesyswallet": "/home/zdmuser/migration/sysWallet_11g_v2"
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
           "pauseafter": "ZDM_CONFIGURE_DG_SRC"
         }'
```

## 4. Resume Job 


## 5. Resume Job with Pause Again 

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

## Coming Soon ##

ZDM Run APIs
```
/abort
/addsyswallet
/addosswallet
/build
/suspend
```

