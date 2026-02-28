# ZEUS Deployment Guide

This guide documents the current deployment path for ZEUS using the repository's container-based scripts. It is written for operators who need to build, run, and maintain a ZEUS instance with persisted runtime state.

ZEUS packages two services:
- a **FastAPI backend** for workflow execution and ZEUS-managed data handling
- a **Streamlit UI** for operator interaction with common ZDM workflows

This guide focuses on:
- building the container image with a local ZDM kit zip
- running the container with the repository scripts
- understanding the persisted runtime layout under `/u01/zeus`
- configuring authentication, TLS, ports, and runtime behavior
- performing basic health checks and operator validation

## What the container runs

A ZEUS deployment is a containerized runtime built and started through the repository `build.sh` and `run.sh` scripts.

At build time, the image includes:
- the ZEUS application code from `zdm-microservices/`
- the local ZDM kit zip staged by `build.sh`
- the Python dependencies needed by the ZEUS services
- the container startup scripts used to initialize and run ZEUS

At runtime, `run.sh` starts the `zeus` container with host networking, a persistent `/u01` volume mount, and any host mappings defined in `.hosts`. The container then runs `zeus.sh`, which performs first-run setup and starts the ZEUS services.

The running container includes these main runtime pieces:

1. **Container startup and runtime scripts**
   - `zeus.sh` performs first-run runtime initialization and starts the ZEUS services
   - `restart_microservice.sh` starts or restarts the FastAPI backend
   - `restart_streamlit.sh` starts or restarts the Streamlit UI

2. **FastAPI backend** (`zdm-microservices/main.py`)
   - default port: `8001`
   - executes backend workflows
   - persists ZEUS-managed runtime data

3. **Streamlit UI** (`zdm-microservices/streamlit_app.py`)
   - default port: `8000`
   - calls backend endpoints over HTTP Basic Auth
   - connects to the backend over HTTPS in the current persisted-runtime model

4. **Persisted runtime state under `/u01`**
   - runtime config, auth, certs, logs, and ZEUS-managed data live outside the image so they survive container recreation

## Deployment model

This repository currently documents a **container deployment** using the scripts at the repository root.

At a high level:
- `build.sh` builds the image using a **local ZDM kit zip**
- `run.sh` starts the container with a persistent `/u01` mount
- `zeus.sh` performs first-run runtime initialization inside the container
- runtime config, auth, certs, and logs are stored outside the image under `/u01`

This separation is important:
- **image build** handles packaged software and default environment values
- **runtime state** under `/u01/zeus` handles persisted config, auth, TLS, and logs

## Prerequisites

Before building and running ZEUS, make sure the host has:
- **Podman** installed and usable
- access to the required source and target network paths for your migrations
- a local **ZDM kit zip** file, for example `zdm.zip`
- a persistence strategy for `/u01` such as the provided `zdm_volume:/u01:Z`

You do **not** need to manually install Python packages on the host for this container path. Those are handled during image build and container runtime.

## Build input: local ZDM kit zip

Before running `build.sh`, set `ZDM_KIT_PATH` to your local ZDM kit zip.

Example:

```bash
export ZDM_KIT_PATH=/path/to/zdm.zip
./build.sh
```

Operator-relevant behavior:
- `build.sh` reads the repository `.env`
- if `ZDM_KIT_PATH` is set, the kit is copied into the build context as `.local_zdm/zdm.zip`
- the build fails fast if the local kit is missing
- the `Dockerfile` expects the copied kit at `/tmp/local_zdm/zdm.zip`

For operators, the main required action is simply: set `ZDM_KIT_PATH` correctly before running `./build.sh`.

## Build and run

### Build the image

```bash
export ZDM_KIT_PATH=/path/to/zdm.zip
./build.sh
```

What `build.sh` does at a high level:
- reads `.env` from the repository root
- passes build arguments into `podman build`
- prepares the image with the required software and environment defaults
- ensures a `zdm_volume` Podman volume exists after build

### Run the container

```bash
./run.sh
```

What `run.sh` does at a high level:
- reads host mappings from `.hosts`
- starts the container using host networking
- mounts persistent storage at `/u01`
- restarts the container automatically
- starts the container under the name `zeus`

Current run characteristics:
- `--network host`
- `--restart=always`
- `-v zdm_volume:/u01:Z`

## Runtime layout and persisted state

In the current deployment model, `/u01/zeus` is the main persisted runtime location.

Recommended persisted layout:
- `/u01/zeus/zeus.env` - runtime config
- `/u01/zeus/.zeus.auth.env` - API Basic Auth users
- `/u01/zeus/certs/zeus.crt` and `/u01/zeus/certs/zeus.key` - TLS certificate and key
- `/u01/log/` - logs

This layout makes `/u01/zeus` the operator-managed runtime source of truth for configuration and credentials, rather than rebuilding the image for every small runtime change.

### First-run behavior

On first run, `zeus.sh` initializes persisted runtime files if they do not already exist:
- copies `zeus.env.sample` to `/u01/zeus/zeus.env` if missing
- generates TLS certificate and key if missing
- creates `/u01/zeus/.zeus.auth.env` from `.zeus.auth.env.sample` if missing

After first run, operators should review and update the generated runtime files, especially credentials.

## Runtime configuration

Edit runtime settings in:

```bash
/u01/zeus/zeus.env
```

Key runtime settings include:
- `ZEUS_BASE` (default `/u01/zeus`) - base path for runtime state
- `ZEUS_HOST` (default `127.0.0.1`) - backend bind host
- `ZEUS_PORT` (default `8001`) - backend port
- `STREAMLIT_PORT` (default `8000`) - UI port
- `ZEUS_CERT_DIR` (default `$ZEUS_BASE/certs`) - TLS cert/key location
- `ZEUS_AUTH_FILE` (default `$ZEUS_BASE/.zeus.auth.env`) - auth file path
- `API_BASE_URL` (optional) - if unset, the UI derives it from the backend port and runtime config

## Required backend environment behavior

The backend requires:
- `ZDM_HOME`
- `ZEUS_DATA`

The backend derives:
- `MIGRATION_BASE = ZEUS_DATA/migration`

There is no separate operator requirement to set `MIGRATION_BASE` independently if the current code derives it from `ZEUS_DATA`.

Typical runtime values are along the lines of:

```bash
export ZDM_HOME=/u01/app/zdmhome
export ZEUS_DATA=/u01/data
```

## Authentication

The runtime auth file is typically:

```bash
/u01/zeus/.zeus.auth.env
```

Example format:

```bash
ZEUS_API_USER_1=zdmuser
ZEUS_API_USER_1_PASSWORD=YourPassword123#_
# add ZEUS_API_USER_2 / ZEUS_API_USER_2_PASSWORD as needed
```

Operator notes:
- protect this file with restrictive permissions such as `chmod 600`
- change generated default credentials immediately
- keep this file in persisted runtime storage, not only inside the image

## HTTPS and TLS trust

In the current persisted-runtime model, ZEUS uses HTTPS with a self-signed certificate stored under the runtime cert directory.

Typical certificate location:

```bash
/u01/zeus/certs/zeus.crt
/u01/zeus/certs/zeus.key
```

Current behavior:
- the backend serves HTTPS
- the Streamlit UI connects to the backend with TLS verification enabled
- restart scripts can point `REQUESTS_CA_BUNDLE` to `${ZEUS_CERT_DIR}/zeus.crt`

For command-line testing, you can trust the self-signed cert with:

```bash
export CURL_CA_BUNDLE=/u01/zeus/certs/zeus.crt
```

or pass `--cacert` directly in each `curl` command.

## Ports and health checks

Default ports:
- **Streamlit UI:** `8000`
- **FastAPI backend:** `8001`

Basic runtime checks:

```bash
curl --cacert /u01/zeus/certs/zeus.crt -I https://localhost:${STREAMLIT_PORT:-8000}
curl --cacert /u01/zeus/certs/zeus.crt https://localhost:${ZEUS_PORT:-8001}/health
curl --cacert /u01/zeus/certs/zeus.crt https://localhost:${ZEUS_PORT:-8001}/version
```

Container-level checks:

```bash
podman ps
podman logs zeus --tail 200
```

## Runtime scripts

The main runtime scripts are:
- `zeus.sh` - performs first-run setup for env, auth, and certs; starts both services; keeps PID 1 alive when used as the container entrypoint
- `restart_microservice.sh` - restarts the backend and expects certs and auth to be present
- `restart_streamlit.sh` - restarts the UI and derives or uses the configured backend base URL

## Important runtime behavior notes

### Build-time `.env` versus runtime `zeus.env`

Current script flow includes both build-time and runtime configuration layers.

Build-time behavior:
- `build.sh` reads the repository `.env`
- values are passed into the image build
- the `Dockerfile` sets them as image environment values
- `run.sh` does not currently inject the repo `.env` at runtime using `--env-file`

Operational implication:
- changing repository `.env` values usually requires **rebuild + rerun**
- changing persisted runtime values in `/u01/zeus/zeus.env` is the preferred path for runtime-level settings handled by the runtime model

### Persistence

The provided run path mounts persistent storage at `/u01`.

With the current defaults, ZEUS-managed data is typically stored under:

```bash
/u01/data/migration
```

Use persistent storage for `/u01` so migration data, runtime config, credentials, and certificates survive container recreation.

## Operator validation checklist

After deployment, verify the following:
- the image built successfully with the intended ZDM kit zip
- the container is running as `zeus`
- `/u01/zeus/zeus.env` exists and reflects the intended runtime values
- `/u01/zeus/.zeus.auth.env` exists and credentials have been updated from defaults
- `/u01/zeus/certs/` contains the expected certificate and key
- the UI is reachable on the expected port
- the backend `/health` and `/version` endpoints respond successfully
- persisted data under `/u01` remains available after container restart

## Related documents

- `README.md` - repository overview and quick start
- `docs/ZEUS_API_Reference.md` - API endpoints and examples