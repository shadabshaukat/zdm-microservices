# API overview

FastAPI backend with Basic Auth (cURL examples use placeholder credentials such as `zdmuser / YourPassword123#_`; replace with your actual ZEUS API credentials).

Backend auth users are loaded via `backend_auth.py` (from the .zeus.auth.env file).
For full schemas, use:
- `GET /openapi.json`
- `GET /docs` (Swagger UI)
- `GET /redoc` (ReDoc)

## Route groups (current backend)

### Core / status
- `GET /health`
- `GET /version`

### Query / job tracking
- `GET /jobids`
- `GET /query/{jobid}`

### Job control (retained / not currently used by Streamlit UI)
- `POST /resume/{jobid}`
- `POST /resume_pauseagain/{jobid}`
- `POST /abort/{jobid}`
- `POST /suspend/{jobid}`

### DB connections
- `POST /dbconnection`
- `GET /dbconnections`
- `DELETE /dbconnection/{name}`
- `POST /dbconnection/{name}/uploadTlsWallet`
- `POST /dbconnection/test`
- `POST /dbconnection/discover`
- `GET /dbconnection/discover/latest/{name}`

### Projects
- `GET /projects`
- `POST /project`
- `DELETE /project/{name}`  (retained / not currently used by Streamlit UI)

### Response file APIs (separate from job APIs)
- `POST /WriteResponseFile`
- `GET /responsefile/{project}`

### Saved job presets / run APIs
- `GET /jobsaved`
- `POST /jobsaved`
- `DELETE /jobsaved/{name}`
- `POST /runjob`

### Logs
- `POST /ReadJobLog`

### Wallets / credentials
- `GET /tlsWallets`  (retained / not currently used by Streamlit UI)
- `GET /credentialWallets`
- `POST /OraPKICreateWallet`
- `POST /MkstoreCreateCredential`

## Request hints (verified against current request models + endpoint logic)

### `POST /dbconnection`
Request model: `DBConnectionParams`
- Required: `name`, `host`, `port`, `service_name`, `username`
- Optional: `db_type`, `protocol` (default `TCP`), `allow_tls_without_wallet` (default `false`), `tls_wallet_uploaded_dir`

### `POST /dbconnection/test`
Request model: `DBConnectionCheckParams`
- Required by model: `name`
- Common in practice: `password`
- Optional: `use_uploaded_tls_wallet`, `run_snapshot`
- Note: TLS wallet requirement is determined by the saved connection config (`protocol`, `allow_tls_without_wallet`) and uploaded wallet availability.

### `POST /dbconnection/discover`
Request model: `DBConnectionDiscoverParams`
- Required by model: `name`
- Common in practice: `password`
- Optional: `use_uploaded_tls_wallet`, `migration_type` (default `logical_offline`), `role`
- Note: This endpoint does **not** require `project`.

### `POST /project`
Request model: `ProjectParams`
- Required: `name`
- Optional: `rsp`, `source_connection`, `target_connection`

### `POST /WriteResponseFile`
Request model: `WriteResponseFileRequest`
- Required: `project`, `lines` (list of strings)

### `POST /jobsaved`
Request model: `SavedJobParams`
- Required: `name`, `project`
- Optional fields include `rsp`, `run_type`, source/target args, advisor/flow-control options, `custom_args`, etc.

### `POST /runjob`
Request model: `RunJobParams`
- Required: `project`
- Optional: `run_type` (`EVAL`/`MIGRATE`, default `EVAL`), `rsp`, `dry_run`, source/target CLI args, advisor/flow-control fields, `ignore`, `schedule`, `listphases`, `custom_args`

### `POST /ReadJobLog`
Request model: `LogFileParams`
- Required: `file_path`

### `POST /OraPKICreateWallet`
Request model: `WalletFileParams`
- Optional: `wallet_name` or `wallet_path` (backend resolves credential wallet path)

### `POST /MkstoreCreateCredential`
Request model: `MkstoreParams`
- Required: `user`, `password`
- Optional: `wallet_name` or `wallet_path`

### `POST /resume/{jobid}` and `POST /resume_pauseagain/{jobid}`
Request body model: `ResumeParams`
- Body is required
- Optional fields: `project`, `pauseafter`, `skip`, `ignore`

### `POST /abort/{jobid}` and `POST /suspend/{jobid}`
- No JSON body required
- Optional query parameter: `project`

---

## Example cURL requests (common UI workflows)

These examples focus on the endpoints currently used by the Streamlit UI.

### Health check
```bash
curl -X GET "http://127.0.0.1:8001/health" 
```

### Create / update a DB connection
```bash
curl -X POST "http://127.0.0.1:8001/dbconnection" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "name": "SRC1",
    "host": "dbhost.example.com",
    "port": 1521,
    "service_name": "ORCLPDB1",
    "username": "system",
    "protocol": "TCP",
    "allow_tls_without_wallet": false
  }' | jq .
```

### Test DB connection
```bash
curl -X POST "http://127.0.0.1:8001/dbconnection/test" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "name": "SRC1",
    "password": "YourDbPassword"
  }' | jq .
```

### Run discovery snapshot (UI usually passes `migration_type`, but backend does not require `project`)
```bash
curl -X POST "http://127.0.0.1:8001/dbconnection/discover" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "name": "SRC1",
    "password": "YourDbPassword",
    "migration_type": "logical_offline"
  }' | jq .
```

### Create / update a project
```bash
curl -X POST "http://127.0.0.1:8001/project" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "name": "demo_proj",
    "source_connection": "SRC1",
    "target_connection": "TGT1"
  }' | jq .
```

## Example cURL requests (response file APIs only)

### Write response file (`.rsp`) content for a project
```bash
curl -X POST "http://127.0.0.1:8001/WriteResponseFile" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "project": "demo_proj",
    "lines": [
      "MIGRATION_METHOD=LOGICAL",
      "DATA_TRANSFER_MEDIUM=OSS",
      "SOURCE_DB_CONNECTION_STRING=src-host:1521/SVC"
    ]
  }' | jq .
```

### Read response file for a project
```bash
curl -X GET "http://127.0.0.1:8001/responsefile/demo_proj" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" | jq .
```

## Example cURL requests (job APIs only)

### Save a reusable job preset
```bash
curl -X POST "http://127.0.0.1:8001/jobsaved" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "name": "demo-eval",
    "project": "demo_proj",
    "run_type": "EVAL",
    "advisor_mode": "NONE",
    "flow_control": "NONE",
    "listphases": false
  }' | jq .
```

### Dry-run a job command (preview only)
```bash
curl -X POST "http://127.0.0.1:8001/runjob" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "project": "demo_proj",
    "run_type": "EVAL",
    "dry_run": true
  }' | jq .
```

### Submit a runjob (MIGRATE)
```bash
curl -X POST "http://127.0.0.1:8001/runjob" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "project": "demo_proj",
    "run_type": "MIGRATE",
    "advisor_mode": "NONE",
    "flow_control": "NONE"
  }' | jq .
```

### List known job IDs
```bash
curl -X GET "http://127.0.0.1:8001/jobids" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" | jq .
```

### Query a job by ID (optional query parameter `project` is supported but not required if auto-mapped)
```bash
curl -X GET "http://127.0.0.1:8001/query/12345" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" | jq .
```

### Read a job log file
```bash
curl -X POST "http://127.0.0.1:8001/ReadJobLog" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "file_path": "/path/to/zdm_job.log"
  }' | jq .
```

## Example cURL requests (wallet / credential APIs)

### List credential wallets
```bash
curl -X GET "http://127.0.0.1:8001/credentialWallets" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" | jq .
```

### Create a credential wallet (orapki)
```bash
curl -X POST "http://127.0.0.1:8001/OraPKICreateWallet" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "wallet_name": "my_wallet"
  }' | jq .
```

### Add credential into a wallet (mkstore)
```bash
curl -X POST "http://127.0.0.1:8001/MkstoreCreateCredential" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "wallet_name": "my_wallet",
    "user": "store",
    "password": "SecretPassw0rd!"
  }' | jq .
```

## Example cURL requests (retained admin / future UI endpoints)

### Resume a job (body required; `ResumeParams`)
```bash
curl -X POST "http://127.0.0.1:8001/resume/12345" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "project": "demo_proj",
    "skip": "DATAPUMP_IMPORT"
  }' | jq .
```

### Resume and pause again (body required; `ResumeParams`)
```bash
curl -X POST "http://127.0.0.1:8001/resume_pauseagain/12345" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "project": "demo_proj",
    "pauseafter": "ZDM_CONFIGURE_DG_SRC",
    "ignore": "ZDM_VALIDATE_TGT"
  }' | jq .
```

### Abort a job (optional `project` query parameter)
```bash
curl -X POST "http://127.0.0.1:8001/abort/12345?project=demo_proj" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" | jq .
```

### Suspend a job (optional `project` query parameter)
```bash
curl -X POST "http://127.0.0.1:8001/suspend/12345?project=demo_proj" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" | jq .
```

### List TLS wallets
```bash
curl -X GET "http://127.0.0.1:8001/tlsWallets" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" | jq .
```

### Delete a project
```bash
curl -X DELETE "http://127.0.0.1:8001/project/demo_proj" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" | jq .
```
