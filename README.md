# ZEUS (ZDM Enqueue URL Services)

ZEUS is a lightweight migration operations console built on **Oracle Zero Downtime Migration (ZDM)** for teams managing migrations across many Oracle databases. While `zdmcli` works well for individual migrations, ZEUS makes fleet-scale operations easier to standardize, manage, and monitor.

It provides a consistent way to organize common ZDM workflows, manage reusable migration metadata, and improve operational visibility during large migration programs.

## What ZEUS does

ZEUS helps operators work with common ZDM migration workflows in a more structured and repeatable way. It can be used to:

- Manage **DB connection profiles**
- Run **DB discovery snapshots**
- Manage **projects**
- Generate and store **response files**
- Build and run **ZDM commands**
- Monitor jobs and read logs
- Manage **wallets and credentials** used by ZEUS workflows

## Architecture

ZEUS wraps common ZDM CLI workflows with a simple web application architecture:

- **Frontend:** Streamlit UI in `zdm-microservices/streamlit_app.py`
- **Backend:** FastAPI service in `zdm-microservices/main.py`
- **Interaction pattern:** the Streamlit UI calls backend APIs over HTTP Basic Auth
- **Execution pattern:** the backend invokes local tools and scripts, including ZDM CLI workflows and related Oracle tooling

## UI sections

The Streamlit UI currently includes the following sections:

- Backend Connection
- DB Connections
- DB Discovery
- Projects
- Response Files
- Create Job
- Run Job
- Monitor Jobs
- Wallets and Credentials

## Project layout

This repository uses a simple operator-first layout:

- **Repository root**: container build and run entrypoints
- **`docs/`**: deployment and API documentation
- **`zdm-microservices/`**: ZEUS runtime code (FastAPI, Streamlit, helpers)

```text
.
├── build.sh                     # build the ZEUS container image from local repo files and ZDM kit
├── Dockerfile                   # container image definition for ZEUS runtime
├── README.md
├── run.sh                       # run the ZEUS container with persistent /u01 storage
├── restart_microservice.sh      # restart ZEUS FastAPI backend (uses runtime env)
├── restart_streamlit.sh         # restart ZEUS Streamlit UI (uses runtime env)
├── start_zdm.sh                 # install/start ZDM service
├── start_zeus.sh                # start ZEUS backend/UI
├── docs/
│   ├── ZEUS_API_Reference.md
│   └── ZEUS_Deployment_Guide.md
└── zdm-microservices/
    ├── backend_auth.py            # loads ZEUS API Basic Auth users from runtime auth file
    ├── main.py                    # FastAPI backend entrypoint
    ├── requirements.txt
    ├── sql_catalog.json
    ├── streamlit_app.py           # Streamlit UI entrypoint
    ├── zeus.env.sample            # template -> /u01/data/zeus/zeus.env
    ├── .zeus.auth.env.sample      # template -> /u01/data/zeus/.zeus.auth.env
    └── .zeus.auth.env             # (sample copy may be created at runtime)
```

## Quick start (container)

This repository is documented for a **container deployment path with a local ZDM kit**.

### 1) Download the ZDM installation file

Download the ZDM installation archive from the official source and store it locally. Make note of the file path because it is used in the next step.

### 2) Set your local ZDM kit zip path

Before running `build.sh`, set `ZDM_KIT_PATH` to your local ZDM kit zip file.

```bash
export ZDM_KIT_PATH=/path/to/zdm.zip
```

### 3) Build the image

```bash
./build.sh
```

### 4) Run the container

```bash
./run.sh
```

### 5) Verify services

```bash
curl --cacert /u01/data/zeus/certs/zeus.crt -I https://localhost:8000
curl --cacert /u01/data/zeus/certs/zeus.crt https://localhost:8001/health
curl --cacert /u01/data/zeus/certs/zeus.crt https://localhost:8001/version
```

## Runtime configuration and persistence

ZEUS runs both the Streamlit UI and the FastAPI backend over **HTTPS** using a self-signed certificate.

All runtime state is persisted under `/u01/data/zeus`:

- Runtime config: `/u01/data/zeus/zeus.env`
- API auth users: `/u01/data/zeus/.zeus.auth.env` unless overridden with `ZEUS_AUTH_FILE`
- TLS cert and key: `${ZEUS_CERT_DIR:-/u01/data/zeus/certs}/zeus.crt` and `${ZEUS_CERT_DIR:-/u01/data/zeus/certs}/zeus.key`
- Migration working state: `${MIGRATION_BASE}`
- Logs: `/u01/data/zeus/log/`

On first start, ZEUS:

- copies `zdm-microservices/zeus.env.sample` to `/u01/data/zeus/zeus.env` if it does not already exist
- copies `zdm-microservices/.zeus.auth.env.sample` to `/u01/data/zeus/.zeus.auth.env` if it does not already exist
- generates TLS certificates if they are missing

### Default ports

- **Streamlit UI:** `8000`
- **FastAPI backend:** `8001`

Ports can be overridden in `/u01/data/zeus/zeus.env`.

### Configuration notes

- The backend requires `ZDM_HOME` and `ZEUS_DATA`
- `MIGRATION_BASE` is derived automatically as `ZEUS_DATA/migration`
- `.env` at the repository root is used at build time
- Runtime overrides should be placed in `/u01/data/zeus/zeus.env`

For step-by-step setup details and operational guidance, refer to the Deployment Guide.

## Documentation

- **`docs/ZEUS_Deployment_Guide.md`** - step-by-step build and run setup, runtime configuration, and operational details
- **`docs/ZEUS_API_Reference.md`** - backend endpoint reference and example requests

## Disclaimer

ZEUS executes migration-related commands in your environment.

Validate behavior, command generation, and security controls before using it in customer or production-adjacent environments.
