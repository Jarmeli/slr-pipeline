# SLR Multi-Agent MCP Pipeline

A four-agent pipeline for sea level rise flood damage modeling, built on a Model Context Protocol (MCP) architecture with LM Studio as the local LLM orchestrator.

```
Prepper (7000) → DIO (7001) → MEL (7002) → SIMO (7003)
```

## Architecture

| Agent | Role | Port |
|-------|------|------|
| **Prepper** | Setup wizard — configures and launches all other agents | 7000 |
| **DIO** | Data Ingestion & Operations — PostGIS tools, spatial clipping, NFIP cleaning | 7001 |
| **MEL** | Model Ensemble Learner — GMM + ensemble training, artifact export | 7002 |
| **SIMO** | Scenario & Inference — flood simulation, parcel_damage write, RAG chat | 7003 |

All agents expose an MCP-compatible tool manifest at `GET /tools` and accept tool calls at `POST /call/<tool_name>`.

---

## Quick Start (Local)

### Prerequisites

- Docker Desktop
- LM Studio running with a model loaded on port `1234`
- Access to the Azure PostgreSQL database

### 1. Clone and configure

```bash
git clone <repo-url> slr-pipeline
cd slr-pipeline
cp .env.example .env
# Edit .env with your DB credentials and LM Studio URL
```

### 2. Initialize the database

Run the SQL script against your Azure PostgreSQL database **once**:

```bash
psql "host=$PGHOST port=$PGPORT user=$PGUSER dbname=$PGDATABASE sslmode=require" \
     -f scripts/init_db.sql
```

This creates the `clean_data` schema and the `agent_audit_log` table.

### 3. Launch via Prepper UI (recommended)

```bash
docker compose up prepper
```

Open **http://localhost:7000** and fill in the setup form. On submit, Prepper renders `.env` + `docker-compose.yml` and starts DIO, MEL, and SIMO automatically, then exits.

### 4. Launch all agents directly

```bash
docker compose up --build
```

### 5. Run the pipeline

**Via orchestrator (LM Studio):**

```bash
pip install -r requirements.txt
python orchestrator.py --levels 1 2 3 4 5
```

**Direct mode (no LLM required):**

```bash
python orchestrator.py --levels 1 2 3 4 5
# Automatically falls back to direct sequential mode if LM Studio is unreachable
```

---

## Agent UIs

| Agent | URL | Description |
|-------|-----|-------------|
| Prepper | http://localhost:7000 | Setup wizard |
| DIO | http://localhost:7001/map | Leaflet spatial clipping tool |
| SIMO | http://localhost:7003 | Scenario map + RAG chatbox |

---

## LM Studio Setup

1. Download [LM Studio](https://lmstudio.ai/) and install a model (recommended: Mistral-7B or Llama-3-8B).
2. Start the local server on port `1234` (default).
3. Set `LM_STUDIO_MODEL` in `.env` to the exact model name shown in LM Studio.
4. From inside Docker containers, LM Studio is reachable at `http://host.docker.internal:1234/v1`.

---

## Azure Container Registry Deployment

### 1. Build and push images

```bash
ACR=<your-registry>.azurecr.io

# Build and push each agent
for agent in dio mel simo; do
  az acr build \
    --registry $ACR \
    --image slr-pipeline/$agent:latest \
    --file agents/$agent/Dockerfile \
    .
done
```

### 2. Update docker-compose.yml for ACR images

Replace `build:` directives with `image:` references:

```yaml
dio:
  image: <your-registry>.azurecr.io/slr-pipeline/dio:latest
```

### 3. Deploy to Azure Container Instances or App Service

```bash
# Example: deploy SIMO to Azure Container Instances
az container create \
  --resource-group <rg> \
  --name simo \
  --image $ACR/slr-pipeline/simo:latest \
  --ports 7003 \
  --environment-variables \
    PGHOST=$PGHOST PGUSER=$PGUSER PGPASSWORD=$PGPASSWORD \
    PGDATABASE=$PGDATABASE PGSSL=true \
    LM_STUDIO_URL=$LM_STUDIO_URL \
  --registry-login-server $ACR \
  --registry-username $(az acr credential show -n <acr-name> --query username -o tsv) \
  --registry-password $(az acr credential show -n <acr-name> --query "passwords[0].value" -o tsv)
```

> **Note:** MEL requires the `/artifacts` volume to be a persistent Azure File Share mount.  
> SIMO requires the same share mounted read-only plus a ChromaDB persist directory.

---

## Data Flow

```
NFIP Claims CSV ──► DIO.clean_claims ──► clean_data.claims_processed
                                              │
parcels_cliplayer ──► DIO.clip_to_bbox ──► clean_data.parcels_clipped
                                              │
                                         MEL.configure_run
                                         MEL.fit_gmm
                                         MEL.apply_transform
                                         MEL.train_ensemble
                                         MEL.export_artifacts ──► /artifacts/{run_id}/
                                                                          │
                                                                   SIMO.load_artifact
                                                                   SIMO.run_simulation ──► parcel_damage table
                                                                   SIMO.invalidate_tile_cache
                                                                          │
                                                                   RookeryBay web app reloads tiles
```

---

## Audit Log

Every tool call is logged to `agent_audit_log` in the PostgreSQL database:

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
├── orchestrator.py          # LM Studio → DIO → MEL → SIMO
├── requirements.txt         # orchestrator deps
├── shared/
│   ├── db.py                # asyncpg pool + audit decorator
│   └── schemas.py           # HandoffToken, ArtifactToken (Pydantic)
├── agents/
│   ├── prepper/             # Agent 1: FastAPI setup wizard
│   ├── dio/                 # Agent 2: MCP server + Leaflet clip UI
│   ├── mel/                 # Agent 3: MCP server + ML training
│   └── simo/                # Agent 4: MCP server + RAG chat UI
└── scripts/
    └── init_db.sql          # DB schema initialization
```
