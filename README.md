# SAVI (Sentiment, Accuracy, Validation, Impact) Intelligence Platform

The **SAVI Platform** is an end-to-end, autonomous data harvesting, structural verification, and spatio-temporal analytical infrastructure designed to monitor, verify, and quantify cross-platform information propagation.

## System Architecture Highlights

1. **Adaptive Ingestion Mesh (Phase 1):** Quad-agent scrapers (Web, Reddit, Twitter/X, YouTube) regulated by a Point-Based Reinforcement Learning (PPO) controller managing dynamic request delays, proxy health, and key rotation.
2. **Dynamic DAG Router & Isolation Rainforest (Phase 2):** Segregates micro-events from macro-cascades; filters astroturfing and bot anomalies using an Extended Isolation Forest with oblique slicing hyperplanes.
3. **Graph Analytics & STGNN (Phase 3):** Staged in Neo4j; combines Louvain community detection, Spatio-Temporal Graph Neural Networks (spectral GCN + gated temporal convolutions), and an Open JEV formal logic entailment engine.
4. **SAVI Analytical Suite (Phase 4):** Quantifies Sentiment Dynamics ($S$), Factual Accuracy ($A$), Logical Validation ($V$), and News Impact Index ($I$).
5. **CQRS & Low-Latency Materialization (Phase 5):** Segregates write-heavy graph compute (Neo4j) from read-heavy client serving (PostgreSQL) using JSONB audit logging, GIN indices, and sub-10ms materialized views.

## Documentation & Specification

- **Technical Specification:** See [`docs/SAVI_TECHNICAL_SPECIFICATION.md`](docs/SAVI_TECHNICAL_SPECIFICATION.md) for full mathematical formulations, MDP state/action definitions, and schema details.

---

## Team Testing: PostgreSQL & Docker Setup

If your local Docker daemon struggles or hangs trying to pull NVIDIA's 7GB Triton inference image (`nvcr.io/nvidia/tritonserver:23.10-py3`), Docker Compose profiles are configured to bypass Triton and boot only the essential data infrastructure (PostgreSQL 16, Redis, and Neo4j).

### 1. Boot Core Database Infrastructure (Bypasses Triton 7GB Image)

From the project root:

```bash
# Option A: Boot using the 'core' compose profile (PostgreSQL, Redis, Neo4j)
docker compose -f backend/docker-compose.yml --profile core up -d

# Option B: Boot only PostgreSQL
docker compose -f backend/docker-compose.yml up -d postgres
```

> **Compose Profiles Reference:**
> - `--profile core` or `--profile db`: Starts `postgres`, `neo4j`, and `redis`.
> - `--profile app`: Starts the FastAPI `api` container.
> - `--profile worker`: Starts `celery_worker` and `celery_beat`.
> - `--profile inference`: Starts `tritonserver` (NVIDIA 7GB image).
> - `--profile full`: Boots all services together.

---

### 2. Run Database Bulk Seeder

Once PostgreSQL is healthy on `localhost:5432`:

#### For PostgreSQL Testing:
Set the `DATABASE_URL` environment variable and run the bulk seeder:

```powershell
# Windows PowerShell
$env:PYTHONPATH="backend/src"
$env:DATABASE_URL="postgresql+psycopg2://eureka_user:eureka_secure_2026@localhost:5432/eureka_master"
uv run python backend/src/eureka/db/seeder.py
```

```bash
# Linux / macOS
PYTHONPATH=backend/src DATABASE_URL="postgresql+psycopg2://eureka_user:eureka_secure_2026@localhost:5432/eureka_master" uv run python backend/src/eureka/db/seeder.py
```

#### For Zero-Docker Local Testing (SQLite Fallback):
If Docker is completely frozen or unavailable, omit `DATABASE_URL` to automatically seed into the local embedded SQLite database (`eureka_db.db`):

```powershell
$env:PYTHONPATH="backend/src"
uv run python backend/src/eureka/db/seeder.py
```

---

### 3. Launch FastAPI Command Center & Swagger Portal

Run the FastAPI application locally:

```powershell
# Windows PowerShell
$env:PYTHONPATH="backend/src"
uv run uvicorn eureka.api.main:app --host 127.0.0.1 --port 8000 --reload
```

```bash
# Linux / macOS
PYTHONPATH=backend/src uv run uvicorn eureka.api.main:app --host 127.0.0.1 --port 8000 --reload
```

Access the interactive API docs and test live reports at:
- **Swagger UI:** `http://127.0.0.1:8000/docs`
- **ReDoc:** `http://127.0.0.1:8000/redoc`
- **Live 100-Point Performance Report:** `http://127.0.0.1:8000/api/v1/reports/district-performance`

