# SLR Multi-Agent MCP Pipeline

A four-agent pipeline for sea level rise flood damage modeling, built on a Model Context Protocol (MCP) architecture. A unified **Streamlit UI** orchestrates the full workflow (Phase 0 → 3) through a split-screen conversational interface backed by four FastAPI microservices. When the LLM is unavailable, the CLI orchestrator runs a direct sequential fallback automatically.

```
Prepper (7004) → DIO (7001) → MEL (7002) → SIMO (7003)
```

```bash
# Unified UI — the recommended way to run the pipeline
streamlit run ui/app.py
```

---

## Architecture

| Agent | Role | Port |
|-------|------|------|
| **Prepper** | Setup wizard — configures and launches all other agents | 7004 |
| **DIO** | Data Ingestion & Operations — PostGIS tools, spatial clipping, NFIP cleaning | 7001 |
| **MEL** | Model Ensemble Learner — GMM + ensemble training, artifact export | 7002 |
| **SIMO** | Scenario & Inference — flood simulation, parcel_damage write, RAG chat, MVT tiles | 7003 |

All agents expose an MCP-compatible tool manifest at `GET /tools` and accept tool calls at `POST /call/<tool_name>`.

---

## Streamlit UI

The primary interface is a **split-screen Streamlit app** (`ui/app.py`):

| Panel | Content |
|-------|---------|
| **Left — Agent Chat** | Conversational NL orchestrator. Phases 0–2: study design via regex parser. Phase 3: routes chat to SIMO RAG/LLM for natural-language queries about simulation results. |
| **Right — Visual Canvas** | Phase-specific interactive views: DIO clip map, MEL EDA + training metrics, SIMO dual-layer inundation map. |

### SIMO Map Tabs

| Tab | Description |
|-----|-------------|
| 🚀 County-wide View | PyDeck dual-layer map — NOAA SLR inundation raster + MVT parcel damage overlay with layer toggles |
| 🔬 Regional Assessment | Folium draw tool for polygon selection → localized damage stats |
| 💬 SIMO Chat | Embedded RAG chat backed by ChromaDB + LM Studio |

---

## Quick Start

### Prerequisites

- Docker Desktop
- Access to the Azure PostgreSQL database (`sea-level-rise.postgres.database.azure.com`)
- Python 3.10+ with `pip`
- (Optional) Ollama running on Azure VM for LLM orchestration — see [Azure VM / Ollama Setup](#azure-vm--ollama-setup)

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env — fill in PGPASSWORD and (optionally) LM_STUDIO_URL
```

Key `.env` values:

```dotenv
PGHOST=sea-level-rise.postgres.database.azure.com
PGUSER=SLRuser
PGPASSWORD=<your-password>
PGDATABASE=SeaLevelRise
PGSSL=true

# Ollama on Azure VM (or any OpenAI-compatible endpoint)
LM_STUDIO_URL=http://<azure-vm-public-ip>:11434/v1
LM_STUDIO_MODEL=mistral:7b-instruct

# ChromaDB persist directory (SIMO RAG knowledge base)
CHROMA_PERSIST_DIR=/artifacts/chroma

# Service URLs (Streamlit UI reads these)
DIO_URL=http://localhost:7001
MEL_URL=http://localhost:7002
SIMO_URL=http://localhost:7003

# Ports — port 7000 conflicts with macOS AirPlay Receiver
PREPPER_PORT=7004
```

### 2. Initialize the database (once)

```bash
PGPASSWORD=<pw> psql \
  "host=sea-level-rise.postgres.database.azure.com port=5432 user=SLRuser dbname=SeaLevelRise sslmode=require" \
  -f scripts/init_db.sql
```

Creates the `clean_data` schema and `agent_audit_log` table.

### 3. Start agents

```bash
docker compose up --build
```

Or via the Prepper setup UI:

```bash
docker compose up prepper
# Open http://localhost:7004
```

### 4. Launch the Streamlit UI

```bash
cd ui
pip install -r requirements.txt
streamlit run app.py
# Open http://localhost:8501
```

### 5. (Alternative) Run the pipeline from CLI

```bash
pip install -r requirements.txt
python orchestrator.py --levels 1 2 3 4 5
```

The orchestrator first tries LLM-driven tool calling. If the model doesn't support function calling (e.g. `phi3:mini`), it automatically falls back to direct sequential execution.

---

## Data Layout

The pipeline expects the following table layout in the `SeaLevelRise` PostgreSQL database:

| Schema | Table | Description |
|--------|-------|-------------|
| `public` | `collier_claims` | Raw NFIP claims (read by DIO) |
| `public` | `parcels_cliplayer` | Collier County parcels with geometry, `elev_mean`, and `ZCTA5CE20` zip codes (read by SIMO) |
| `public` | `real_property_values` | Collier County assessed property values (`totaljustvalue`) |
| `clean_data` | `collier_claims_cleaned` | Pre-processed claims (optional reference) |
| `clean_data` | `claims_processed` | Output written by `DIO.clean_claims` |
| `public` | `parcel_damage` | Simulation results written by SIMO (auto-created) |

> **Key columns in `parcels_cliplayer`:**
> - `elev_mean` — mean ground elevation in meters (converted to feet during simulation)
> - `ZCTA5CE20` — Census ZCTA zip code used for zip-distance feature encoding
>
> **Training data fallback:** If `/data/*.csv` files are not mounted, MEL automatically loads training data from `clean_data.claims_processed` and derives `zip_mean_dist` from the claims data itself.

---

## Data Flow

```
public.collier_claims
        │
        ▼
DIO.clean_claims ──────────► clean_data.claims_processed
                                         │
                                 MEL.configure_run   ◄── DB fallback when CSV not mounted
                                 MEL.fit_gmm
                                 MEL.apply_transform
                                 MEL.train_ensemble
                                 MEL.export_artifacts ──► /artifacts/{run_id}/
                                                                   │
                                                          SIMO.load_artifact
                                                          SIMO.run_simulation ──► public.parcel_damage
                                                          SIMO.index_simulation_report ──► ChromaDB
                                                          SIMO.invalidate_tile_cache
                                                                   │
                                                          ST_AsMVT tile endpoint
                                                          PyDeck MVTLayer (Streamlit UI)
```

---

## Agent UIs

| Agent | URL | Description |
|-------|-----|-------------|
| **Streamlit** | http://localhost:8501 | **Primary UI** — full split-screen pipeline interface |
| Prepper | http://localhost:7004 | Setup wizard |
| DIO | http://localhost:7001/map | Leaflet spatial clipping tool |
| SIMO | http://localhost:7003 | Standalone scenario map + RAG chatbox |

---

## Performance

| Operation | Latency |
|-----------|---------|
| SIMO simulation (500k parcels) | ~3 s |
| Map tile render (PyDeck MVT) | Instantaneous |
| RAG chat response | ~1–3 s (LM Studio / Ollama) |

Achieved via: vectorized NumPy inference, PostGIS `ST_AsMVT` tile generation, geometry excluded from the ML pipeline (WKB handled entirely in DB), and `COALESCE`-guarded real elevation/zip queries.

---

## Azure VM / Ollama Setup

The pipeline uses Ollama on a budget Azure VM (`Standard_D2s_v3`, Canada Central) as the LLM backend.

### Provision the VM

```bash
bash scripts/azure-vm-create.sh
```

### Install Ollama on the VM

```bash
# Copy and run on the VM
bash scripts/vm-lmstudio-init.sh
```

This installs Ollama, configures it as a systemd service on `0.0.0.0:11434`, and pulls `phi3:mini`.

### VM management

```bash
bash scripts/vm-manage.sh status   # check Ollama health
bash scripts/vm-manage.sh stop     # deallocate VM (stop billing)
bash scripts/vm-manage.sh start    # restart VM
```

> **Model note:** `phi3:mini` does not support the OpenAI function/tool-calling API. For LLM-driven orchestration, pull a tool-capable model:
> ```bash
> ollama pull mistral:7b-instruct
> ```
> Then set `LM_STUDIO_MODEL=mistral:7b-instruct` in `.env`.

---

## Audit Log

Every tool call is logged to `agent_audit_log`:

```sql
SELECT agent, tool, params, status, ts
FROM agent_audit_log
ORDER BY ts DESC
LIMIT 20;
```

---

## Directory Structure

```
slr-pipeline/
├── docker-compose.yml
├── .env.example
├── orchestrator.py           # CLI: LLM → DIO → MEL → SIMO (direct fallback)
├── requirements.txt          # orchestrator deps
├── shared/
│   ├── db.py                 # asyncpg pool + @audit decorator
│   └── schemas.py            # HandoffToken, ArtifactToken (Pydantic)
├── agents/
│   ├── prepper/              # Agent 0: setup wizard UI
│   ├── dio/                  # Agent 1: MCP server + Leaflet clip UI + spatial tools
│   ├── mel/                  # Agent 2: MCP server + GMM + ensemble training
│   └── simo/                 # Agent 3: MCP server + simulator + RAG + MVT tiles
│       └── src/
│           ├── server.py     # FastAPI: tool endpoints + ST_AsMVT tile server
│           ├── simulator.py  # Flood scoring engine (real elev_mean + ZCTA5CE20)
│           └── rag.py        # ChromaDB + LM Studio RAG pipeline
├── ui/
│   ├── app.py                # Streamlit split-screen (Left: chat, Right: canvas)
│   ├── api_client.py         # Async HTTP client for all agent endpoints
│   ├── requirements.txt      # Streamlit UI deps
│   └── views/
│       ├── prepper.py        # Phase 0 — DB connection wizard
│       ├── dio.py            # Phase 1 — clip map + existing dataset selector
│       ├── mel.py            # Phase 2 — EDA-first training + live metrics
│       └── simo.py           # Phase 3 — dual-layer PyDeck map + RAG chat tab
├── scripts/
│   ├── init_db.sql           # DB schema initialization
│   ├── azure-vm-create.sh    # Provision Azure VM
│   ├── vm-lmstudio-init.sh   # Install Ollama on VM
│   └── vm-manage.sh          # Start / stop / status VM
└── daily_log/                # Session progress notes
    ├── 2026-03-12.md
    ├── 2026-03-13.md
    └── 2026-03-15.md
```

---

## Azure Container Registry Deployment

```bash
ACR=<your-registry>.azurecr.io

for agent in dio mel simo; do
  az acr build \
    --registry $ACR \
    --image slr-pipeline/$agent:latest \
    --file agents/$agent/Dockerfile \
    .
done
```

> MEL requires `/artifacts` to be a persistent Azure File Share mount.
> SIMO requires the same share read-only, plus a dedicated ChromaDB volume at `/chroma`.
