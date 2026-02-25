# ZEUS (ZDM Enqueue URL Services)

ZEUS is a lightweight migration operations console for **Oracle Zero Downtime Migration (ZDM)** teams.

It provides a **Streamlit UI + FastAPI backend** wrapper around common ZDM CLI workflows so engineers can standardize execution, manage reusable metadata, and improve operational visibility during migrations.

## What ZEUS does

- Manage **DB connection profiles**
- Run **DB discovery snapshots**
- Manage **projects**
- Generate and store **response files**
- Build and run **ZDM commands**
- Monitor jobs and read logs
- Manage **wallets / credentials** used by ZEUS workflows

## Project layout

This repository uses a simple operator-first layout:

- **Repository root**: container build/run entrypoints
- **`docs/`**: deployment + API documentation
- **`zdm-microservices/`**: ZEUS runtime code (FastAPI, Streamlit, helpers)

```text
.
├── build.sh
├── Dockerfile
├── README.md
├── run.sh
├── TODO.md
├── docs/
│   ├── ZEUS_API_Reference.md
│   └── ZEUS_Deployment_Guide.md
└── zdm-microservices/
    ├── backend_auth.py
    ├── main.py
    ├── requirements.txt
    ├── restart_microservice.sh
    ├── restart_streamlit.sh
    ├── sql_catalog.json
    ├── streamlit_app.py
    ├── .zeus.auth.env        # local auth file (do not commit real secrets)
    └── zeus.sh
```

## Architecture

- **Frontend:** `zdm-microservices/streamlit_app.py` (Streamlit)
- **Backend:** `zdm-microservices/main.py` (FastAPI)
- **Auth pattern:** Streamlit calls FastAPI over HTTP Basic Auth
- **Execution pattern:** Backend invokes local tools/scripts (for example ZDM CLI and Oracle tooling)

## UI sections (from `streamlit_app.py`)

- Backend Connection
- DB Connections
- DB Discovery
- Projects
- Response Files
- Create Job
- Run Job
- Monitor Jobs
- Wallets & Credentials

## Default ports

- **Streamlit UI:** `8000`
- **FastAPI backend:** `8001`

## Quick start (container)

This repo is documented for a **container deployment path with a local ZDM kit**.

### 0) Download latest ZDM installtion file 
Download the installation binary from official website and store it locally, make note of the path which will be used in next step.

### 1) Set your local ZDM kit zip path

Before running `build.sh`, set `ZDM_KIT_PATH` to your local ZDM kit zip file.

```bash
export ZDM_KIT_PATH=/path/to/zdm.zip
```

### 2) Build the image

```bash
./build.sh
```

### 3) Run the container

```bash
./run.sh
```

### 4) Verify services

```bash
curl -I http://127.0.0.1:8000
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/version
```

## Configuration notes (summary)

- The backend requires `ZDM_HOME` and `ZEUS_DATA`
- `MIGRATION_BASE` is derived automatically as `ZEUS_DATA/migration`
- `.env` values are baked into the image during `build.sh` (changes usually require rebuild + rerun)
- Add entries in backend auth file `.zeus.auth.env` if you don't want to use default dev user/password

For setup details, runtime behavior, and operational notes, use the Deployment Guide.

## Documentation

- **`docs/ZEUS_Deployment_Guide.md`** — step-by-step build/run setup and operational configuration
- **`docs/ZEUS_API_Reference.md`** — backend endpoint reference and example requests

## Disclaimer

ZEUS executes migration-related commands in your environment.

Validate behavior, command generation, and security controls before using it in customer or production-adjacent environments.
