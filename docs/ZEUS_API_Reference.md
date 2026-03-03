# ZEUS API User Guide

ZEUS is a lightweight web UI and API layer for working with Oracle ZDM. This guide is written as a product manual, not a route dump. It focuses first on the APIs used by the current Streamlit UI and the workflows a user follows in the product.

## How to read this guide

The backend contains more endpoints than the UI uses day to day. To keep this guide clear, the APIs are split into two groups:

1. **UI workflow APIs** - the endpoints used by the current Streamlit product flow.
2. **Additional backend APIs** - backend-supported endpoints for administration, lifecycle control, advanced workflows, and capabilities that are already available on the server side but not yet exposed in every part of the current UI.

If you are using ZEUS through the UI, start with the UI workflow section first. If you are integrating directly with the backend, extending the UI, or operating ZEUS in a more advanced way, the additional backend APIs section will also be useful.

---

## 1. Before you start

### Base URL

Examples in this guide assume the backend is available at:

```text
https://localhost:8001
```

Replace that with your real ZEUS host and port.

### Authentication

ZEUS uses HTTP Basic Auth.

Example credentials in this guide:

- Username: `zdmuser`
- Password: `YourPassword123#_`

Replace them with your real ZEUS credentials.

### HTTPS certificate

ZEUS serves HTTPS. If you are using a self-signed certificate, point curl to the ZEUS certificate:

```bash
export CURL_CA_BUNDLE=${ZEUS_CERT_DIR:-/u01/data/zeus/certs}/zeus.crt
```

Or pass it directly:

```bash
--cacert ${ZEUS_CERT_DIR:-/u01/data/zeus/certs}/zeus.crt
```

### Useful live schema endpoints

If you want live OpenAPI output from the running backend:

- `GET /openapi.json`
- `GET /docs`
- `GET /redoc`

---

# Part A - UI workflow APIs

These are the endpoints a typical user will encounter when following the current Streamlit UI.

## 2. Check the backend is reachable

The UI starts by testing whether the backend is alive.

### `GET /health`

Use this for a simple liveness check.

**Example**

```bash
curl -X GET "https://localhost:${ZEUS_PORT:-8001}/health" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)"
```

**Example response**

```json
{
  "status": "ok"
}
```

### `GET /version`

Use this to confirm you are talking to a ZEUS backend and to see the service version.

**Example response**

```json
{
  "version": "1.0.0",
  "service": "zdm-microservices"
}
```

---

## 3. Save database connections

A saved DB connection gives ZEUS a reusable connection definition for a source or target database. The password is supplied only when you test or discover the connection.

### `POST /dbconnection`

Create or update a saved DB connection.

**Typical fields**

- `name`
- `host`
- `port`
- `service_name`
- `username`
- `db_type`
- `protocol`
- `allow_tls_without_wallet`

**Example**

```bash
curl -X POST "https://localhost:${ZEUS_PORT:-8001}/dbconnection" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "name": "SRC1",
    "host": "dbhost.example.com",
    "port": 1521,
    "service_name": "ORCLPDB1",
    "username": "system",
    "db_type": "Oracle",
    "protocol": "TCP",
    "allow_tls_without_wallet": false
  }'
```

### `GET /dbconnections`

List saved DB connections.

Use this when the UI needs to populate connection dropdowns.

### `DELETE /dbconnection/{name}`

Delete a saved DB connection.

Use this when you no longer want a connection available in ZEUS.

---

## 4. Upload a TLS wallet for a saved connection

If a saved connection uses TCPS and requires a wallet, upload it after the connection is created.

### `POST /dbconnection/{name}/uploadTlsWallet`

Upload a wallet ZIP for a saved connection.

**Request type**

- multipart upload
- file field name: `wallet`

**Example**

```bash
curl -X POST "https://localhost:${ZEUS_PORT:-8001}/dbconnection/SRC1/uploadTlsWallet" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -F "wallet=@/path/to/tls-wallet.zip"
```

---

## 5. Test a saved connection

Use this to verify the saved connection details and password before moving on.

### `POST /dbconnection/test`

Validate connectivity for a saved connection.

**Required fields**

- `name`
- `password`

**Optional field**

- `run_snapshot`

**Example**

```bash
curl -X POST "https://localhost:${ZEUS_PORT:-8001}/dbconnection/test" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "name": "SRC1",
    "password": "YourDbPassword"
  }'
```

---

## 6. Create and manage projects

A project is the main working container in ZEUS. It groups together the source and target selections, the response file name, and the jobs that belong to that migration effort.

### `GET /projects`

List projects.

The UI uses this to populate project selectors across pages.

### `POST /project`

Create or update a project.

**Typical fields**

- `name`
- `source_connection`
- `target_connection`
- `rsp`

**Example**

```bash
curl -X POST "https://localhost:${ZEUS_PORT:-8001}/project" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "name": "demo_proj",
    "source_connection": "SRC1",
    "target_connection": "TGT1"
  }'
```

### `DELETE /project/{name}`

Delete a project.

---

## 7. Build and save a response file

In the current ZEUS product flow, the response file is assembled in the UI and then written by the backend.

That means the UI owns the user input and rendering logic, while the backend is responsible for saving the final `.rsp` content.

### `POST /WriteResponseFile`

Write the final response-file lines for a project.

**Required fields**

- `project`
- `lines` - ordered list of response-file lines

**Example**

```bash
curl -X POST "https://localhost:${ZEUS_PORT:-8001}/WriteResponseFile" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "project": "demo_proj",
    "lines": [
      "MIGRATION_METHOD=ONLINE_PHYSICAL",
      "SOURCE_DB=SRC1",
      "TARGET_DB=TGT1"
    ]
  }'
```

### `GET /responsefile/{project}`

Read back the current response file for a project.

The UI uses this to reload previously saved response-file content.

---

## 8. Save reusable job definitions

A saved job definition is a reusable set of run parameters. It does not execute anything by itself.

### `GET /jobsaved`

List saved job definitions.

### `POST /jobsaved`

Create or update a saved job definition.

**Typical fields**

- `name`
- `project`
- `rsp`
- `run_type`
- node and auth fields
- advisor and flow-control fields
- scheduling and custom arguments

**Example**

```bash
curl -X POST "https://localhost:${ZEUS_PORT:-8001}/jobsaved" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "name": "demo-eval",
    "project": "demo_proj",
    "rsp": "demo_proj.rsp",
    "run_type": "EVAL",
    "advisor_mode": "NONE",
    "flow_control": "NONE"
  }'
```

### `DELETE /jobsaved/{name}`

Delete a saved job definition.

---

## 9. Preview or run a job

This is the main execution endpoint used by the UI.

### `POST /runjob`

Generate a ZDM command and either preview it or run it.

**Typical fields**

- `project`
- `rsp`
- `run_type`
- `dry_run`
- source and target connection arguments
- advisor and flow-control fields
- scheduling fields
- `custom_args`

### Preview mode

Set `dry_run=true` to preview the generated command without submitting it.

**Example**

```bash
curl -X POST "https://localhost:${ZEUS_PORT:-8001}/runjob" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "project": "demo_proj",
    "rsp": "demo_proj.rsp",
    "run_type": "EVAL",
    "dry_run": true
  }'
```

### Submit mode

Omit `dry_run` or set it to `false` to submit the run.

**Example**

```bash
curl -X POST "https://localhost:${ZEUS_PORT:-8001}/runjob" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "project": "demo_proj",
    "rsp": "demo_proj.rsp",
    "run_type": "MIGRATE"
  }'
```

---

## 10. Monitor jobs in the UI

The current UI focuses on job lookup, query, and log reading.

### `GET /jobids`

Return the list of job IDs known to ZEUS.

### `GET /query/{jobid}`

Query a specific job.

If the project is known, it can also be passed explicitly as a query parameter.

**Example**

```bash
curl -X GET "https://localhost:${ZEUS_PORT:-8001}/query/12345" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)"
```

### `POST /ReadJobLog`

Read a log file when you already know the file path.

**Example**

```bash
curl -X POST "https://localhost:${ZEUS_PORT:-8001}/ReadJobLog" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "file_path": "/path/to/zdm_job.log"
  }'
```

---

## 11. Manage credential wallets from the UI

The current Streamlit UI includes a wallet page for creating credential wallets and adding stored credentials.

### `GET /credentialWallets`

List available credential wallets.

### `POST /OraPKICreateWallet`

Create a credential wallet.

**Example**

```bash
curl -X POST "https://localhost:${ZEUS_PORT:-8001}/OraPKICreateWallet" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "wallet_name": "my_wallet"
  }'
```

### `POST /MkstoreCreateCredential`

Create a stored credential inside a credential wallet.

**Example**

```bash
curl -X POST "https://localhost:${ZEUS_PORT:-8001}/MkstoreCreateCredential" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "wallet_name": "my_wallet",
    "user": "store",
    "password": "SecretPassw0rd!"
  }'
```

---

## 12. Run discovery from the UI

The current Streamlit app also includes a discovery page. Discovery is useful, but it is not part of the smallest happy path for every user, so it is documented after the core project-run flow.

### `POST /dbconnection/discover`

Run discovery for a saved connection.

**Typical fields**

- `name`
- `password`
- `migration_type`
- `role`

**Example**

```bash
curl -X POST "https://localhost:${ZEUS_PORT:-8001}/dbconnection/discover" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
  -d '{
    "name": "SRC1",
    "password": "YourDbPassword",
    "migration_type": "logical_offline"
  }'
```

### `GET /dbconnection/discover/latest/{name}`

Return the latest saved discovery result for a connection.

---

# Part B - Additional backend APIs

These endpoints are supported by the backend and may be useful for operations, advanced workflows, direct backend integrations, or future UI expansion. Some are not yet exposed in the current Streamlit UI, and others support actions that are better treated as operational controls than as part of the main setup flow.

## 13. Job control endpoints

These are job lifecycle endpoints for jobs that already exist. They are useful for operational control and are also available for future UI expansion.

### `POST /resume/{jobid}`

Resume a paused job.

### `POST /resume_pauseagain/{jobid}`

Resume a job and set a new pause point.

### `POST /abort/{jobid}`

Abort a job.

### `POST /suspend/{jobid}`

Suspend a running job.

These endpoints are typically used after a job has already been created and entered an active lifecycle state.

---

## 14. Additional wallet inventory endpoint

### `GET /tlsWallets`

List TLS wallets available on the backend.

This endpoint can be useful for backend operations, troubleshooting, direct integrations, or future UI expansion.

---

## 15. Compact endpoint map

### UI workflow APIs

- `GET /health`
- `GET /version`
- `POST /dbconnection`
- `GET /dbconnections`
- `DELETE /dbconnection/{name}`
- `POST /dbconnection/{name}/uploadTlsWallet`
- `POST /dbconnection/test`
- `GET /projects`
- `POST /project`
- `DELETE /project/{name}`
- `POST /WriteResponseFile`
- `GET /responsefile/{project}`
- `GET /jobsaved`
- `POST /jobsaved`
- `DELETE /jobsaved/{name}`
- `POST /runjob`
- `GET /jobids`
- `GET /query/{jobid}`
- `POST /ReadJobLog`
- `GET /credentialWallets`
- `POST /OraPKICreateWallet`
- `POST /MkstoreCreateCredential`
- `POST /dbconnection/discover`
- `GET /dbconnection/discover/latest/{name}`

### Additional backend APIs

- `POST /resume/{jobid}`
- `POST /resume_pauseagain/{jobid}`
- `POST /abort/{jobid}`
- `POST /suspend/{jobid}`
- `GET /tlsWallets`
