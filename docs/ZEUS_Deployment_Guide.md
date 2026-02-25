# ZEUS Deployment Guide

This guide documents the **current implemented deployment path** for ZEUS, based on the repository scripts and code.

Scope of this guide:
- container image build using a **local ZDM kit zip**
- container run using repository `build.sh` / `run.sh`
- runtime checks and operator notes
- backend/runtime environment behavior

---

## 1. What is deployed

ZEUS has two runtime services inside the current deployment:

1. **FastAPI backend** (`zdm-microservices/main.py`)
   - default port: **8001**
   - executes backend workflows and persists ZEUS-managed data

2. **Streamlit UI** (`zdm-microservices/streamlit_app.py`)
   - default port: **8000** (via `restart_streamlit.sh`)
   - calls backend endpoints over HTTP Basic Auth

---

## 2. Container deployment prerequisites

This repository is documented for **container deployment** (Podman scripts at repo root).

Before building/running, ensure the host has:

- **Podman** available (the provided scripts use `podman`)
- access to the required source/target network paths used by your migrations
- a usable local **ZDM kit zip** file (for example `zdm.zip`)
- a persistent volume strategy for `/u01` (the provided `run.sh` uses `zdm_volume:/u01:Z`)
- a valid ZEUS auth file (recommended), e.g. `zdm-microservices/.zeus.auth.env`

> You do **not** need to manually install Python, `requirements.txt`, or `python-multipart` on the host for the container path. Those are handled in the image build/runtime.

---

## 3. Local ZDM kit input (required for image build)

Before running `build.sh`, set `ZDM_KIT_PATH` to your local ZDM kit zip file.

Example:

```bash
export ZDM_KIT_PATH=/path/to/zdm.zip
./build.sh
```

Current script behavior (`build.sh`):
- loads repo `.env`
- if `ZDM_KIT_PATH` is set, copies it into the build context as `.local_zdm/zdm.zip`
- fails fast if the local kit is missing before `podman build`

Current `Dockerfile` behavior:
- expects the copied local kit at `/tmp/local_zdm/zdm.zip`
- fails fast if it is missing

This is an implementation detail; the main operator action is simply to set `ZDM_KIT_PATH` before `./build.sh`.

---

## 4. Container build and run (current scripts)

### 4.1 Build image

```bash
export ZDM_KIT_PATH=/path/to/zdm.zip
./build.sh
```

What `build.sh` currently does (operator-relevant summary):
- reads `.env` from repo root
- passes build args into `podman build`
- ensures a `zdm_volume` Podman volume exists after build

### 4.2 Run container

```bash
./run.sh
```

What `run.sh` currently does:
- reads host mappings from `.hosts`
- starts container with:
  - `--network host`
  - `--restart=always`
  - `-v zdm_volume:/u01:Z`
- container name: `zeus`

---

## 5. Runtime environment behavior

### 5.1 Backend required environment variables (`main.py`)

Current backend code requires:

- `ZDM_HOME` (**required**)
- `ZEUS_DATA` (**required**)

`main.py` derives the backend storage root automatically as:

- `MIGRATION_BASE = ZEUS_DATA/migration`

and creates it at startup.

Example runtime values (already typically baked into the image via `.env` + `build.sh` + `Dockerfile`):

```bash
export ZDM_HOME=/u01/app/zdmhome
export ZEUS_DATA=/u01/data
```

> In current code, there is **no separate `MIGRATION_BASE` env var requirement**.

### 5.2 Auth file behavior (`backend_auth.py` / `streamlit_app.py`)

Backend (`backend_auth.py`):

- Read from `zdm-microservices/.zeus.auth.env` 


Frontend (`streamlit_app.py`):
- supports `API_BASE_URL` (default `http://127.0.0.1:8001`)
- supports `ZDM_API_USER` / `ZDM_API_PASSWORD`
- can also prefill from `backend_auth.first_user_defaults()`
- still has development fallback defaults if nothing is provided

### 5.3 `.env` behavior in current container scripts

Current script flow:
- `build.sh` reads repo `.env`
- values are passed as Docker/Podman build args
- `Dockerfile` sets them as image `ENV`
- `run.sh` does **not** inject `.env` at runtime via `--env-file`

Operational implication:
- changing `.env` usually requires **rebuild + rerun** to take effect

---

## 6. Ports and health checks

Default ports:

- **Streamlit UI:** `8000`
- **FastAPI backend:** `8001`

After the container is running, basic checks:

```bash
curl -I http://127.0.0.1:8000
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/version
```

Container checks:

```bash
podman ps
podman logs zeus --tail 200
```

---

## 7. Persistence and data layout (operator notes)

The provided `run.sh` mounts:

- `zdm_volume:/u01:Z`

With current code and environment defaults, backend-managed ZEUS data is stored under:

- `ZEUS_DATA/migration`
- typically `/u01/data/migration` in the container

Use persistent storage for `/u01` so ZEUS data survives container recreation.

---


## 8. Related docs

- `README.md` — overview and quick start
- `docs/ZEUS_API_Reference.md` — API endpoints and examples
