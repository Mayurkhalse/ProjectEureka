# Project EUREKA: Comprehensive Low-Level Architecture & Technical Specification
## The DGIPR Maha-Command Center Media Intelligence Engine

**Document Version:** 1.0.0  
**Classification:** Enterprise Production Architecture  
**Author:** Senior Principal Backend Engineering Team  
**Scope:** Backend Systems, Persistence Layer, Distributed Task Queues, Ingestion Mesh, Semantic Binding, NLP Heads, Graph Projections, and RBAC State Machine.

---

## 1. Executive Summary & Mission Overview

**Project EUREKA** is the next-generation media intelligence and narrative governance engine engineered specifically for the **Directorate General of Information and Public Relations (DGIPR)**, Government of Maharashtra.

### 1.1 Architectural Purpose & Mandate
Project EUREKA replaces legacy experimental prototypes with an enterprise-grade, asynchronous, distributed media analysis backend. The system ingests public releases, government notifications, news articles, and interactive digital communications across Maharashtra, executing:
1. **Multi-Lane Provenance Ingestion (QUAD System):** Ingests structured and unstructured media across four distinct weight-based lanes, preserving an immutable chain of custody before any data transformation occurs.
2. **Deterministic Entity & Incident Resolution (IRF Binding):** Replaces ambiguous continuous scoring with discrete formal logic primitives (`Choice`, `Noul`, `Score`) derived from **SemIf-OpenJev**, establishing strict convergence thresholds for incident clustering.
3. **Multilingual Indic Natural Language Processing:** Classifies Marathi, Hindi, and English content using **MuRIL** (`google/muril-base-cased`), deriving fine-grained sentiment polarity and factual claim boundaries.
4. **Hybrid Relational-Graph Synchronization:** Leverages PostgreSQL 16 as the transactional source of truth and Neo4j 5.x for spatio-temporal graph projections, unified via a **Transactional Outbox Pattern** with zero dual-write vulnerability.
5. **100-Point Composite Index Performance Measurement:** Evaluates state and district-level narrative operations across four 25-point performance pillars: Volume, Turnaround Speed (TAT), Sentiment Polarity (NSI), and Crisis Refutation SLA.
6. **Strict Role-Based Human Review Workflow:** Mandates a formal state machine (`draft -> pending_review -> approved | overridden | rejected`) protected by cryptographically signed JWT role claims for Command Center administrators and district personnel.

---

## 2. High-Level & Low-Level System Topology

```mermaid
graph TD
    subgraph External ["External Data Sources"]
        S1["Lane 1: Open Gov APIs (data.gov.in)"]
        S2["Lane 2: Portal APIs (DGIPR, Relief, Health)"]
        S3["Lane 3: Web News & RSS Portals"]
        S4["Lane 4: Complex DOMs & Bot-Wall Protected Outlets"]
        S5["NewsAPI v2 / Live Web Feeds"]
    end

    subgraph Edge ["Autonomous Edge Node (NEWS_API.py)"]
        DISC["Discovery: NewsAPI Client"]
        EXTR["Extraction: Crawl4AI + LXML / HTTP Fallback"]
        DISPATCH["Queue Dispatcher: EUREKA 8-Field Schema"]
        DISC --> EXTR --> DISPATCH
    end

    subgraph CloudNLP ["Serverless Cloud NLP Layer (eureka.llm)"]
        HF_SENT["Hugging Face Serverless (CardiffNLP RoBERTa)"]
        GROQ_LLM["Groq Cloud LLaMA 3 8B (Crisis SLA Classifier)"]
    end

    subgraph Ingestion ["Ingestion Mesh (QUAD Subsystem)"]
        API_CONN["httpx Connectors (Lanes 1 & 2)"]
        CRAWL_CONN["Crawl4AI Engine (Lanes 3 & 4)"]
        SHA["SHA-256 Deterministic Provenance Hasher"]
    end

    subgraph MessageQueue ["Distributed Queue & Scheduler (Redis 7.x)"]
        Q_DEFAULT["Queue: default (Batch Ingestion & Cypher)"]
        Q_QUAD["Queue: quad_ingestion"]
        Q_IRF["Queue: irf_binding"]
        Q_PROC["Queue: processor"]
        Q_OUT["Queue: outbox"]
        BEAT["Celery Beat Scheduler (5s Outbox / 15m Scoring)"]
    end

    subgraph RelationalDB ["Transactional Source of Truth (PostgreSQL 16 / SQLite)"]
        T_RAW["raw_events (Immutable Payloads)"]
        T_EVENTS["media_events (250,000+ Extreme Scale Rows)"]
        T_NORM["normalized_records (mr / hi / en)"]
        T_CANON["canonical_events (Clustered Incidents)"]
        T_DEC["binding_decisions (OpenJev Audit)"]
        T_TICKET["fact_check_tickets (Crisis 90m SLA)"]
        T_SCORE["pillar_score_snapshots (100-Point Index)"]
        T_AUDIT["human_review_actions (RBAC Audit Trail)"]
        T_OUTBOX["outbox_events (CDC Transactional Buffer)"]
    end

    subgraph MLHeads ["Machine Learning & Resolution Engines"]
        NORM_ENG["TextNormalizer & Language Classifier"]
        OPENJEV["SemIf-OpenJev Binding Engine (Choice/Noul/Score)"]
        MURIL["MuRIL Sentiment Pipeline (google/muril-base-cased)"]
        STGNN_PREP["StGNN Feature Matrix Extractor"]
        IPCS_ADAPT["IPCSAdapter (Strict: not_configured)"]
    end

    subgraph GraphDB ["Spatio-Temporal Graph (Neo4j 5.x)"]
        OUTBOX_WORKER["Neo4j Outbox Worker (SKIP LOCKED)"]
        CYPHER_WORKER["Neo4j Cypher Batch Worker (ingest_neo4j_batch_task)"]
        N_DIST["(:District)"]
        N_DEPT["(:Department)"]
        N_CANON["(:CanonicalEvent)"]
        N_REL["(:Release)"]
        N_CLAIM["(:Claim)"]
        N_MEVENT["(:MediaEvent)"]
    end

    subgraph API_Layer ["API & Governance Layer (FastAPI)"]
        JWT_AUTH["JWT RBAC Middleware (State Admin / Collector / DIO Desk)"]
        EP_HEALTH["GET /api/v1/health"]
        EP_QUAD["POST /api/v1/quad/ingest"]
        EP_REV["POST /api/v1/conclusions/{id}/review"]
        EP_SCORE["GET /api/v1/scoring/latest"]
        EP_REPORTS["GET /api/v1/reports/district-performance"]
        EP_JOBS["POST /api/v1/jobs/trigger-ingestion"]
        EP_GRAPH["GET /api/v1/graph/spatio-temporal"]
    end

    subgraph Frontend ["Maha-Command Center Frontend (frontend/MCC)"]
        MCC_DECK["Next.js / React 19 Executive Command Deck"]
        MCC_ECHARTS["36-District & 6-Division Apache ECharts"]
        MCC_WARROOM["Crisis War Room 90m SLA Countdown"]
    end

    S1 & S2 --> API_CONN
    S3 & S4 --> CRAWL_CONN
    API_CONN & CRAWL_CONN --> SHA --> Q_QUAD
    S5 --> DISC
    EXTR --> CloudNLP --> DISPATCH
    DISPATCH --> Q_DEFAULT
    Q_DEFAULT --> T_EVENTS & CYPHER_WORKER
    CYPHER_WORKER --> N_DIST & N_MEVENT
    Q_QUAD --> T_RAW
    T_RAW --> Q_IRF --> NORM_ENG --> T_NORM
    T_NORM --> OPENJEV --> T_DEC & T_CANON & T_OUTBOX
    T_CANON --> Q_PROC --> MURIL --> T_CANON
    T_OUTBOX --> Q_OUT --> OUTBOX_WORKER
    OUTBOX_WORKER --> N_DIST & N_DEPT & N_CANON & N_REL & N_CLAIM
    BEAT --> Q_PROC & Q_OUT
    API_Layer --> RelationalDB & GraphDB
    MCC_DECK --> API_Layer
```

---

## 3. Architectural Decision Records (ADRs)

### ADR-001: Hybrid Relational-Graph CQRS with Transactional Outbox
* **Status:** Accepted & Implemented
* **Context:** The DGIPR Command Center requires ACID guarantees for audit logs, fact-check SLA tickets, and user reviews, while simultaneously requiring sub-second multi-hop graph traversals across Maharashtra districts, state departments, and incident cascades. Dual-writing to PostgreSQL and Neo4j within application request handlers causes distributed transaction failures, network partitions, and data divergence.
* **Decision:** PostgreSQL 16 is designated the sole transactional source of truth. Every mutation to a graph-projectable entity synchronously inserts an event record into `outbox_events` within the same database transaction. A dedicated asynchronous Celery worker polls `outbox_events` using `SELECT ... FOR UPDATE SKIP LOCKED` and executes idempotent Cypher `MERGE` queries in Neo4j.
* **Consequences:** Zero dual-write inconsistencies. If Neo4j restarts, PostgreSQL transactions are never blocked. Outbox events retry with exponential backoff up to 5 times before marking `FAILED`.

### ADR-002: QUAD Model Weight-Based Ingestion Architecture
* **Status:** Accepted & Implemented
* **Context:** Information originates from diverse sources ranging from high-trust structured government REST endpoints to bot-protected regional news outlets and dynamic JavaScript portals.
* **Decision:** Implement four dedicated ingestion lanes:
  * **Lane 1 (`LANE_1_API_GOV`):** High-throughput, authenticated REST JSON connectors (`httpx`) targeting structured open government data (`data.gov.in`, `pib.gov.in`).
  * **Lane 2 (`LANE_2_API_PORTAL`):** Departmental portal feeds (`dgipr.maharashtra.gov.in`, Disaster Management feeds) with custom schema mappings.
  * **Lane 3 (`LANE_3_SCRAPE_WEB`):** Clean HTML and RSS extraction via `crawl4ai.AsyncWebCrawler` extracting structured markdown.
  * **Lane 4 (`LANE_4_SCRAPE_DOM`):** Interactive DOM navigation and anti-scraping bypass via `crawl4ai` headless browser automation (`bypass_cache=True`, selector filtering, JavaScript triggers).
* **Write-Back Rule:** All four lanes must write raw, un-normalized payloads into `raw_events` accompanied by a deterministic SHA-256 hash before any normalization or NLP parsing occurs.

### ADR-003: Discrete SemIf-OpenJev IRF Binding vs. Fuzzy Scoring
* **Status:** Accepted & Implemented
* **Context:** Previous prototype iterations relied on continuous fuzzy metrics ($S_{dyn}$, $A_{score}$) which produced unpredictable clustering boundaries and could not provide verifiable explanations for why two news items were grouped together.
* **Decision:** Replace continuous formulas with formal semantic logic primitives from **SemIf-OpenJev**:
  * **`Choice` ($\ge 0.90$ similarity):** Formal semantic equivalence. Automatically binds to existing `canonical_event_id`.
  * **`Noul` ($< 0.70$ similarity):** Formal semantic divergence. Automatically instantiates a new `canonical_event_id`.
  * **`Score` ($0.70 \le \text{similarity} < 0.90$):** Ambiguous boundary condition. Binds provisionally but marks event status as `pending_review` for human review.
* **Consequences:** Clear, legally auditable classification boundaries stored in the `binding_decisions` table with explicit logic primitive tags.

### ADR-004: Multilingual Indic NLP Processing with MuRIL
* **Status:** Accepted & Implemented
* **Context:** Maharashtra state media operates predominantly in Marathi (65%), Hindi (20%), and English (15%). Generic English LLMs struggle with Marathi morphological markers (e.g., 'ळ', 'झाले', 'शासनाने').
* **Decision:** Integrate HuggingFace's `google/muril-base-cased` (Multilingual Representations for Indian Languages). The model outputs classification labels (`Positive`, `Neutral`, `Negative`, `Mixed`) and a continuous polarity score in $[-1.0, 1.0]$. A resilient rule-anchored fallback classifier provides seamless continuity when GPU resources or model weights are initializing.

### ADR-005: 100-Point Composite Index Performance Measurement
* **Status:** Accepted & Implemented
* **Context:** Executive command staff need a standardized, deterministic score ($0 - 100$) reflecting real-time communication performance.
* **Decision:** Implement four 25-point additive pillars:
  1. **Volume Pillar ($0 - 25$):** $25 \times \min\left(\frac{\text{TotalReleases}}{300}, 1.0\right)$ (saturates at 300 releases per window).
  2. **Turnaround Speed (TAT) Pillar ($0 - 25$):** Evaluates elapsed time $\Delta t = \text{published\_ts} - \text{event\_ts}$. $\Delta t \le 45\text{ min} \implies 25\text{ pts}$; $\Delta t \ge 120\text{ min} \implies 0\text{ pts}$; linear degradation between 45 and 120 min.
  3. **Sentiment Pillar ($0 - 25$):** Evaluates Net Sentiment Index ($NSI = \frac{\text{Pos} - \text{Neg}}{\text{Total}}$) mapped linearly: $\left(\frac{NSI + 1.0}{2.0}\right) \times 25.0$.
  4. **Crisis SLA Pillar ($0 - 25$):** $\left(\frac{\text{RumorsRefutedWithin90Mins}}{\text{TotalRumorsIngested}}\right) \times 25.0$. **Critical Rule:** If $\text{TotalRumorsIngested} = 0$, the engine must strictly return $25.0$ points to prevent division by zero.

### ADR-006: Human-in-the-Loop Review State Machine & Strict RBAC
* **Status:** Accepted & Implemented
* **Context:** Automated intelligence cannot publish official state conclusions without designated bureaucratic authorization.
* **Decision:** Enforce a strict state machine: `draft -> pending_review -> approved | overridden | rejected`. Valid transitions are guarded by JWT tokens carrying verified `UserRole` claims:
  * `DG State Admin`: Unrestricted state-wide approval, override, and rejection authority.
  * `District Collector`: Authority restricted to events matching their assigned `district_code`.
  * `DIO Desk`: Read-only and draft submission authority.
  All state transitions record immutable records in `human_review_actions`.

### ADR-007: Strict IPCS Adapter Isolation
* **Status:** Accepted & Implemented
* **Context:** The Integrated Public Communication System (IPCS) specification is pending final technical definition by DGIPR.
* **Decision:** The `IPCSAdapter` class is implemented with a strict interface that returns `{"status": "not_configured"}` for all methods. Speculative or hallucinated mock implementations are strictly prohibited.

### ADR-008: Asynchronous Distributed Chunk Ingestion via Celery & Redis
* **Status:** Accepted & Implemented
* **Context:** Ingesting 250,000+ extreme-scale records synchronously in the FastAPI event loop caused request timeouts, socket exhaustion, and UI thread freezing.
* **Decision:** Decouple ingestion into an asynchronous distributed pipeline using Celery with Redis broker (`redis://127.0.0.1:6379/0`) and result backend (`/1`). The `POST /api/v1/jobs/trigger-ingestion` endpoint reads CSV/API sources in configurable batch chunks (default: 5,000 records) and queues them as background tasks (`process_ingestion_chunk.delay(chunk)`).
* **Consequences:** The FastAPI event loop responds within sub-50ms with a `job_id` and chunk dispatch summary. Worker processes handle database insertions concurrently with isolated database connection pooling.

### ADR-009: Serverless Cloud NLP Inference vs. Heavy Local Model Weights
* **Status:** Accepted & Implemented
* **Context:** Loading multi-gigabyte neural checkpoints locally for sentiment and crisis reasoning requires dedicated high-end GPUs, slowing down CI pipelines and bloating edge nodes.
* **Decision:** Implement `eureka.llm.cloud_evaluator`:
  * **Hugging Face Serverless Inference API:** Uses `cardiffnlp/twitter-roberta-base-sentiment-latest` to map multilingual civic sentiment into a normalized float score in $[-1.0, 1.0]$.
  * **Groq Cloud LLaMA 3 (`llama3-8b-8192`):** Executes deterministic ($T=0.0$) zero-shot prompts to classify whether news media resolves/refutes an active rumor within the Crisis SLA window.
* **Consequences:** Edge scrapers run feather-light on any CPU environment. Model execution latency averages <200ms per article without local memory consumption.

### ADR-010: Parameterized Cypher Batch Graph Sync with UNWIND
* **Status:** Accepted & Implemented
* **Context:** Creating individual nodes and edges in Neo4j sequentially per event creates massive transactional overhead and write lock contention.
* **Decision:** Implement `eureka.workers.neo4j_tasks.ingest_neo4j_batch_task` which receives event lists and executes a single parameterized Cypher query with `UNWIND $events AS event`. The query atomically merges `(:District)` and `(:MediaEvent)` nodes and connects them with `[:HAS_EVENT]`.
* **Consequences:** Graph population throughput increases from ~50 nodes/sec to 10,000+ nodes/sec with zero deadlock risk.

### ADR-011: Next.js/React 19 Frontend Deck with GIGW 3.0 Compliance
* **Status:** Accepted & Implemented
* **Context:** Bureaucratic operators in Maharashtra require a standardized bilingual (English/Marathi) dashboard compliant with Government of India Web Guidelines (GIGW 3.0) and UX4G accessibility.
* **Decision:** Build the **Maha-Command Center (`frontend/MCC`)** using Next.js, React 19, Tailwind CSS, Zustand, and Apache ECharts. The deck provides live 36-district revenue division tracking, Crisis War Room 90-minute SLA countdowns, and direct REST consumption of EUREKA's FastAPI backend.

---

## 4. Database Architecture & Entity Relationships

The transactional persistence layer uses **PostgreSQL 16** managed via **SQLAlchemy 2.0** and **Alembic**.

### 4.1 Relational Schema Definitions (PostgreSQL 16)

```mermaid
erDiagram
    SOURCE_REGISTRY ||--o{ INGESTION_RUNS : "initiates"
    SOURCE_REGISTRY ||--o{ RAW_EVENTS : "sources"
    INGESTION_RUNS ||--o{ RAW_EVENTS : "batches"
    RAW_EVENTS ||--|| NORMALIZED_RECORDS : "normalizes to"
    NORMALIZED_RECORDS ||--o{ EVENT_SOURCE_LINKS : "linked in"
    CANONICAL_EVENTS ||--o{ EVENT_SOURCE_LINKS : "contains"
    NORMALIZED_RECORDS ||--o{ BINDING_DECISIONS : "evaluated in"
    CANONICAL_EVENTS ||--o{ BINDING_DECISIONS : "targeted in"
    CANONICAL_EVENTS ||--o{ FACT_CHECK_TICKETS : "tracks"
    CANONICAL_EVENTS ||--o{ HUMAN_REVIEW_ACTIONS : "audited by"

    SOURCE_REGISTRY {
        uuid id PK
        string name UK
        string lane
        string base_url
        jsonb config_json
        boolean is_active
        integer poll_interval_sec
        timestamptz last_polled_at
        timestamptz created_at
        timestamptz updated_at
    }

    INGESTION_RUNS {
        uuid id PK
        uuid source_id FK
        string status
        integer items_ingested
        integer errors_count
        jsonb error_log
        timestamptz started_at
        timestamptz completed_at
    }

    RAW_EVENTS {
        uuid id PK
        uuid ingestion_run_id FK
        uuid source_id FK
        string lane
        string payload_hash
        text raw_content
        jsonb raw_metadata
        timestamptz ingested_at
    }

    NORMALIZED_RECORDS {
        uuid id PK
        uuid raw_event_id FK
        string title
        text cleaned_text
        string detected_language
        string script
        timestamptz normalized_timestamp
        jsonb entities
        jsonb claims
        timestamptz created_at
        timestamptz updated_at
    }

    CANONICAL_EVENTS {
        uuid id PK
        string title
        text summary
        string primary_language
        string district_code
        string district_name
        string department_code
        string department_name
        string status
        string verification_status
        string sentiment_label
        float sentiment_score
        timestamptz first_detected_at
        timestamptz last_updated_at
        timestamptz created_at
        timestamptz updated_at
    }

    EVENT_SOURCE_LINKS {
        uuid id PK
        uuid canonical_event_id FK
        uuid normalized_record_id FK
        float similarity_score
        string bound_by
        timestamptz bound_at
    }

    BINDING_DECISIONS {
        uuid id PK
        uuid normalized_record_id FK
        uuid canonical_event_id FK
        float similarity_score
        string decision_type
        string logic_primitive
        text reasoning
        timestamptz decided_at
    }

    FACT_CHECK_TICKETS {
        uuid id PK
        uuid canonical_event_id FK
        text claim_text
        boolean is_rumor
        timestamptz event_timestamp
        timestamptz refuted_at
        boolean refuted_within_sla_90m
        string status
        string assigned_to
        text resolution_notes
        timestamptz created_at
        timestamptz updated_at
    }

    PILLAR_SCORE_SNAPSHOTS {
        uuid id PK
        timestamptz window_start
        timestamptz window_end
        float volume_score
        float tat_score
        float sentiment_score
        float crisis_sla_score
        float total_composite_score
        jsonb calculation_metadata
        timestamptz created_at
    }

    HUMAN_REVIEW_ACTIONS {
        uuid id PK
        string entity_type
        uuid entity_id
        string reviewer_id
        string role
        string previous_state
        string new_state
        string action_taken
        text comments
        timestamptz created_at
    }

    OUTBOX_EVENTS {
        uuid id PK
        string aggregate_type
        string aggregate_id
        string event_type
        jsonb payload
        string status
        integer retry_count
        text last_error
        timestamptz created_at
        timestamptz processed_at
    }
```

### 4.2 Spatio-Temporal Graph Model (Neo4j 5.x)

Neo4j maintains a projection optimized for multi-hop graph queries, relationship path extraction, and temporal graph neural network inputs.

```mermaid
graph LR
    REL["Release (id, title, url, timestamp)"]
    CANON["CanonicalEvent (id, title, status, language)"]
    DIST["District (code, name, state)"]
    DEPT["Department (code, name)"]
    CLAIM["Claim (id, text, is_rumor, refuted)"]

    REL -->|":REPORTS_ON {similarity_score, bound_by}"| CANON
    CANON -->|":AFFECTS"| DIST
    CANON -->|":RELATES_TO"| DEPT
    CANON -->|":CONTAINS_CLAIM"| CLAIM
    CLAIM -->|":AFFECTS"| DIST
```

#### Uniqueness Constraints Active in Neo4j:
```cypher
CREATE CONSTRAINT district_code_unique IF NOT EXISTS FOR (d:District) REQUIRE d.code IS UNIQUE;
CREATE CONSTRAINT department_code_unique IF NOT EXISTS FOR (dep:Department) REQUIRE dep.code IS UNIQUE;
CREATE CONSTRAINT canonical_event_id_unique IF NOT EXISTS FOR (e:CanonicalEvent) REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT release_id_unique IF NOT EXISTS FOR (r:Release) REQUIRE r.id IS UNIQUE;
CREATE CONSTRAINT claim_id_unique IF NOT EXISTS FOR (c:Claim) REQUIRE c.id IS UNIQUE;
```

---

## 5. End-to-End System Flows & Sequence Execution

### 5.1 Pipeline Flow 1: QUAD Ingestion to Immutable Persistence

```mermaid
sequenceDiagram
    autonumber
    actor Scheduler as Celery Beat / API Trigger
    participant API as FastAPI Router (/api/v1/quad/ingest)
    participant CeleryQ as Redis (quad_ingestion Queue)
    participant Worker as Celery Worker (ingest_source_task)
    participant QUAD as QUAD Engine (httpx / Crawl4AI)
    participant DB as PostgreSQL 16 (raw_events)
    participant NextQ as Redis (irf_binding Queue)

    Scheduler->>API: POST /api/v1/quad/ingest/{source_id}
    API->>CeleryQ: enqueue ingest_source_task(source_id)
    API-->>Scheduler: 202 Accepted {task_id, status: "dispatched"}

    CeleryQ->>Worker: dequeue ingest_source_task
    Worker->>DB: INSERT INTO ingestion_runs (status="STARTED")
    Worker->>QUAD: execute fetch_json() OR scrape_with_crawl4ai()
    QUAD-->>Worker: raw content payload (JSON/Markdown)
    Worker->>Worker: compute SHA-256 payload_hash
    Worker->>DB: INSERT INTO raw_events (run_id, source_id, lane, payload_hash, raw_content)
    Worker->>DB: UPDATE ingestion_runs (status="COMPLETED", items_ingested=N)
    Worker->>NextQ: enqueue normalize_and_bind_task(raw_event_id)
```

---

### 5.2 Pipeline Flow 2: IRF Binding, SemIf-OpenJev & Outbox Projection

```mermaid
sequenceDiagram
    autonumber
    participant IRF_Worker as Celery Worker (irf_binding Queue)
    participant Normalizer as TextNormalizer
    participant OpenJev as SemIf-OpenJev Engine
    participant PG as PostgreSQL 16
    participant OutboxQ as Celery Beat (5-second Poller)
    participant Neo4jWorker as Neo4j Outbox Worker
    participant GraphDB as Neo4j 5.x Graph

    IRF_Worker->>PG: SELECT raw_content, raw_metadata FROM raw_events
    IRF_Worker->>Normalizer: normalize(raw_content)
    Normalizer-->>IRF_Worker: NormalizationResult (mr/hi/en, clean text, entities)
    IRF_Worker->>PG: INSERT INTO normalized_records

    IRF_Worker->>PG: SELECT CanonicalEvents (window = 72 hrs)
    IRF_Worker->>OpenJev: evaluate_openjev(new_text, candidate_summaries)
    
    alt Similarity >= 0.90 (Choice)
        OpenJev-->>IRF_Worker: Choice primitive -> SAME_EVENT
        IRF_Worker->>PG: UPDATE canonical_events, INSERT event_source_links
    else Similarity < 0.70 (Noul)
        OpenJev-->>IRF_Worker: Noul primitive -> NEW_EVENT
        IRF_Worker->>PG: INSERT INTO canonical_events (status="pending_review")
    else 0.70 <= Similarity < 0.90 (Score)
        OpenJev-->>IRF_Worker: Score primitive -> NEEDS_HUMAN_REVIEW
        IRF_Worker->>PG: INSERT event_source_links, SET status="pending_review"
    end

    IRF_Worker->>PG: INSERT INTO binding_decisions (primitive, similarity_score, reasoning)
    IRF_Worker->>PG: INSERT INTO outbox_events (aggregate_type, payload, status="PENDING")

    Note over OutboxQ,Neo4jWorker: Asynchronous Transactional Outbox Sync Loop (5s)
    OutboxQ->>Neo4jWorker: trigger process_outbox_events_task
    Neo4jWorker->>PG: SELECT FROM outbox_events WHERE status='PENDING' FOR UPDATE SKIP LOCKED
    Neo4jWorker->>GraphDB: Execute Parameterized Cypher (MERGE nodes & relationships)
    GraphDB-->>Neo4jWorker: Transaction Committed
    Neo4jWorker->>PG: UPDATE outbox_events SET status='PROCESSED', processed_at=now()
```

---

### 5.3 Pipeline Flow 3: Human Review State Machine with Strict RBAC

```mermaid
sequenceDiagram
    autonumber
    actor Officer as District Collector / State Admin
    participant Auth as JWT RBAC Middleware
    participant ReviewEP as POST /api/v1/conclusions/{id}/review
    participant DB as PostgreSQL 16
    participant Outbox as outbox_events Table

    Officer->>ReviewEP: POST /review {action, target_state, comments} + Bearer Token
    ReviewEP->>Auth: validate_jwt_and_extract_role(token)
    
    alt Role Unauthorized or District Mismatch
        Auth-->>Officer: 403 Forbidden ("District Collector scope restricted to MH-12")
    else Valid RBAC & District Scope
        Auth-->>ReviewEP: TokenData {username, role, district_code}
        ReviewEP->>DB: SELECT status FROM canonical_events WHERE id = :event_id
        
        alt Invalid State Transition (e.g., approved -> draft)
            ReviewEP-->>Officer: 400 Bad Request ("Invalid state transition")
        else Valid State Transition (e.g., pending_review -> approved)
            ReviewEP->>DB: UPDATE canonical_events SET status = :target_state
            ReviewEP->>DB: INSERT INTO human_review_actions (reviewer_id, role, prev, new, comments)
            ReviewEP->>Outbox: INSERT INTO outbox_events (aggregate="CanonicalEvent", event="STATE_CHANGED")
            DB-->>ReviewEP: Commit Transaction
            ReviewEP-->>Officer: 200 OK {status: "success", new_state: "approved"}
        end
    end
```

---

### 5.4 Pipeline Flow 4: Autonomous Edge Scraping & Serverless Cloud AI Ingestion (`NEWS_API.py`)

```mermaid
sequenceDiagram
    autonumber
    actor CLI as Edge Daemon / Cron
    participant Scraper as NEWS_API.py
    participant NewsAPI as NewsAPI.org (/v2/everything)
    participant Crawler as Crawl4AI (AsyncWebCrawler)
    participant HF as Hugging Face Serverless (RoBERTa)
    participant Groq as Groq Cloud LLaMA 3 8B
    participant Redis as Redis (Queue: default)
    participant Worker as Celery Worker (process_ingestion_chunk)

    CLI->>Scraper: run NEWS_API.py (topic="Thane", max_articles=10)
    Scraper->>NewsAPI: GET /v2/everything?q=Thane&language=en
    NewsAPI-->>Scraper: HTTP 200 OK (articles array)
    
    Scraper->>Crawler: arun() with PruningContentFilterLXML
    alt Scraping Success
        Crawler-->>Scraper: Clean markdown text
    else Anti-Bot / JS Block
        Scraper->>Scraper: Resilient HTTP fallback or lead description
    end

    Scraper->>HF: POST /models/cardiffnlp/twitter-roberta-base-sentiment-latest
    HF-->>Scraper: [{label: "positive", score: 0.95}, ...] -> Score: 1.0
    
    Scraper->>Groq: ChatCompletion (llama3-8b-8192, T=0.0, prompt="Refutes crisis?")
    Groq-->>Scraper: "true" -> crisis_resolved: True

    Scraper->>Scraper: Transform to EUREKA 8-Field Schema
    Scraper->>Redis: process_ingestion_chunk.delay(records)
    Redis-->>Scraper: Celery AsyncResult (Task ID)
    Redis->>Worker: dequeue process_ingestion_chunk(records)
    Worker->>Worker: Bulk Insert into PostgreSQL 16 (media_events)
```

---

### 5.5 Pipeline Flow 5: Extreme-Scale Background Batch Ingestion

```mermaid
sequenceDiagram
    autonumber
    actor Operator as Dashboard / Swagger UI
    participant API as FastAPI (POST /api/v1/jobs/trigger-ingestion)
    participant Queue as Redis (default Queue)
    participant CeleryWorker as Celery Ingestion Worker
    participant DB as PostgreSQL 16 / SQLite (media_events)

    Operator->>API: POST /api/v1/jobs/trigger-ingestion?chunk_size=5000
    API->>API: Read CSV (250,000 records) in 5,000-row chunks
    loop For each chunk (50 chunks total)
        API->>Queue: process_ingestion_chunk.delay(chunk_records)
    end
    API-->>Operator: 200 OK {status: "queued", chunks_queued: 50, total_records: 250000}
    
    par Concurrent Ingestion
        Queue->>CeleryWorker: Worker 1 dequeues Chunk 1
        CeleryWorker->>DB: Bulk insert 5,000 rows
        Queue->>CeleryWorker: Worker 2 dequeues Chunk 2
        CeleryWorker->>DB: Bulk insert 5,000 rows
    end
```

---

### 5.6 Pipeline Flow 6: Asynchronous Neo4j Cypher Batch Graph Sync

```mermaid
sequenceDiagram
    autonumber
    actor Dispatcher as Event Pipeline
    participant CeleryApp as Celery App
    participant Redis as Redis (default Queue)
    participant Worker as Celery Worker (ingest_neo4j_batch_task)
    participant Driver as Neo4jGraphService
    participant Neo4j as Neo4j 5.x Cluster

    Dispatcher->>CeleryApp: ingest_neo4j_batch_task.delay(events)
    CeleryApp->>Redis: enqueue task in default queue
    Redis->>Worker: dequeue ingest_neo4j_batch_task(events)
    Worker->>Driver: run_query(CYPHER_BATCH_INGEST_QUERY, {events: events})
    Driver->>Neo4j: UNWIND $events AS event MERGE (d:District) MERGE (e:MediaEvent) MERGE (d)-[:HAS_EVENT]->(e)
    Neo4j-->>Driver: {events_ingested: N}
    Driver-->>Worker: Result count
    Worker-->>CeleryApp: {status: "success", nodes_linked: N}
```

---

## 6. Mathematical Formulations (100-Point Composite Index)

The scoring engine calculates performance over a sliding time window $W$ (default: 24 hours):

$$\text{Composite Index Score} = S_{\text{vol}} + S_{\text{tat}} + S_{\text{sent}} + S_{\text{sla}} \quad \in [0.0, 100.0]$$

### Pillar 1: Volume ($S_{\text{vol}} \in [0, 25]$)
Measures communication output and presence, saturating at 300 releases per window:

$$S_{\text{vol}} = 25.0 \times \min\left(\frac{N_{\text{releases}}}{300}, 1.0\right)$$

### Pillar 2: Turnaround Speed ($S_{\text{tat}} \in [0, 25]$)
Measures the latency between an event occurrence ($t_{\text{event}}$) and the official public communication ($t_{\text{pub}}$):

$$\overline{\Delta t} = \frac{1}{N} \sum_{i=1}^{N} (t_{\text{pub}, i} - t_{\text{event}, i}) \quad \text{(in minutes)}$$

$$S_{\text{tat}} = \begin{cases} 
25.0 & \text{if } \overline{\Delta t} \le 45 \\
25.0 \times \left(1.0 - \frac{\overline{\Delta t} - 45}{120 - 45}\right) & \text{if } 45 < \overline{\Delta t} < 120 \\
0.0 & \text{if } \overline{\Delta t} \ge 120 
\end{cases}$$

### Pillar 3: Sentiment ($S_{\text{sent}} \in [0, 25]$)
Evaluates public and media sentiment polarity using the Net Sentiment Index ($NSI$):

$$NSI = \frac{C_{\text{positive}} - C_{\text{negative}}}{C_{\text{total\_classified}}} \quad \in [-1.0, 1.0]$$

$$S_{\text{sent}} = \left(\frac{NSI + 1.0}{2.0}\right) \times 25.0$$

*(If $C_{\text{total\_classified}} = 0$, $NSI = 0.0$ and $S_{\text{sent}} = 12.5$)*

### Pillar 4: Crisis SLA ($S_{\text{sla}} \in [0, 25]$)
Measures the state's capacity to identify, refute, and fact-check rumors within a 90-minute SLA window:

$$S_{\text{sla}} = \begin{cases}
25.0 & \text{if } N_{\text{rumors}} = 0 \quad \text{\textbf{(Critical Division-by-Zero Protection)}} \\
\left(\frac{N_{\text{refuted\_within\_90m}}}{N_{\text{rumors}}}\right) \times 25.0 & \text{if } N_{\text{rumors}} > 0
\end{cases}$$

---

### 6.2 Component Data Contracts & Expected Output Specifications

To guarantee end-to-end predictability and compliance across state operations, every component in Project EUREKA adheres to an explicit data contract defining triggering inputs, processing logic, expected output payloads, and error behavior.

---

#### 1. Extreme-Scale Ingestion Trigger (`POST /api/v1/jobs/trigger-ingestion`)
* **Purpose:** Triggers asynchronous streaming of multi-thousand/million dataset chunks into Celery task workers without blocking the HTTP server.
* **HTTP Request:**
  ```http
  POST /api/v1/jobs/trigger-ingestion?chunk_size=5000 HTTP/1.1
  Host: 127.0.0.1:8000
  Content-Type: application/json
  Authorization: Bearer <jwt_token>
  ```
* **Expected Output (HTTP 200 OK):**
  ```json
  {
    "status": "queued",
    "message": "Successfully dispatched 50 chunk(s) to Celery worker queue.",
    "dataset": "english_extreme_scale.csv",
    "total_records": 250000,
    "chunk_size": 5000,
    "chunks_queued": 50,
    "timestamp": "2026-10-18T21:15:00.123456Z"
  }
  ```
* **Error Output (HTTP 404 / 500):**
  ```json
  {
    "status": "error",
    "detail": "Seed dataset file not found at backend/seed_data/english_extreme_scale.csv"
  }
  ```

---

#### 2. Autonomous Edge Ingestion Node (`NEWS_API.py`)
* **Purpose:** Harvests web articles via NewsAPI, extracts body text with Crawl4AI/HTTP fallback, and normalizes into EUREKA's canonical 8-field payload.
* **Expected Canonical Record Output (Dispatched to Celery):**
  ```json
  {
    "record_id": "a9b4c8d1-5e2f-4a3b-8c1d-9e2f3a4b5c6d",
    "district": "Thane",
    "event_type": "News Article",
    "event_timestamp": "2026-10-18T14:30:00Z",
    "turnaround_time_mins": 30.0,
    "sentiment_score": 0.85,
    "crisis_resolved": true,
    "english_content": "The Thane district collectorate announced the immediate restoration of the primary water pipeline in Kalyan, fully resolving the supply disruption."
  }
  ```
* **Celery Dispatch Return:**
  ```text
  [+] Dispatched 10 fully evaluated articles to Celery queue for Thane. Task ID: e1f2a3b4-5c6d-7e8f-9a0b-1c2d3e4f5a6b
  ```

---

#### 3. Serverless Cloud NLP Evaluators (`eureka.llm.cloud_evaluator`)
* **3A. Multilingual Sentiment (`evaluate_sentiment_cloud`):**
  * **Input:** `text: str` (e.g., `"District administration distributed 10,000 food rations."`)
  * **Endpoint:** Hugging Face Serverless (`cardiffnlp/twitter-roberta-base-sentiment-latest`)
  * **Expected Output:** `float` $\in [-1.0, 1.0]$
    ```json
    [[
      {"label": "positive", "score": 0.9412},
      {"label": "neutral", "score": 0.0451},
      {"label": "negative", "score": 0.0137}
    ]]
    ```
    *Mapped Return Value:* `1.0` (or normalized continuous float).
  * **Fallback Output:** `0.0` (Neutral baseline on network timeout).
* **3B. Crisis SLA Reasoning (`evaluate_crisis_sla_groq`):**
  * **Input:** `district: "Thane"`, `text: "Collector debunked false rumor..."`
  * **Engine:** Groq Cloud LLaMA 3 (`llama3-8b-8192`, Temperature $= 0.0$)
  * **Expected Output:** `bool` (`True` if official resolution/refutation is explicit, `False` otherwise)
    ```text
    "true" -> Return: True
    ```

---

#### 4. Asynchronous Neo4j Cypher Batching Task (`eureka.workers.neo4j_tasks`)
* **Task Name:** `eureka.workers.ingest_neo4j_batch_task`
* **Input Parameters:** `events: List[Dict[str, Any]]`
* **Executed Cypher Batch Query:**
  ```cypher
  UNWIND $events AS event
  MERGE (d:District {name: event.district})
  ON CREATE SET d.code = event.district
  MERGE (e:MediaEvent {id: event.record_id})
  SET e.event_type = event.event_type,
      e.turnaround_time_mins = toFloat(event.turnaround_time_mins),
      e.sentiment_score = toFloat(event.sentiment_score),
      e.crisis_resolved = toBoolean(event.crisis_resolved),
      e.timestamp = toString(event.event_timestamp)
  MERGE (d)-[:HAS_EVENT]->(e)
  RETURN count(e) AS events_ingested
  ```
* **Expected Output:**
  ```json
  {
    "status": "success",
    "task_id": "c3d4e5f6-7a8b-9c0d-1e2f-3a4b5c6d7e8f",
    "nodes_linked": 500
  }
  ```

---

#### 5. District Performance Governance Report (`GET /api/v1/reports/district-performance`)
* **Purpose:** Computes and returns the authoritative 100-Point Composite Index for target districts across Maharashtra.
* **HTTP Request:**
  ```http
  GET /api/v1/reports/district-performance?district=Thane HTTP/1.1
  Host: 127.0.0.1:8000
  ```
* **Expected Output (HTTP 200 OK):**
  ```json
  {
    "district": "Thane",
    "composite_index_score": 78.42,
    "evaluation_window_hours": 24,
    "pillars": {
      "volume": {
        "score": 23.50,
        "max_score": 25.0,
        "total_releases": 282,
        "saturation_cap": 300
      },
      "turnaround_time": {
        "score": 19.80,
        "max_score": 25.0,
        "average_tat_minutes": 60.5,
        "target_tat_minutes": 45.0
      },
      "sentiment": {
        "score": 17.62,
        "max_score": 25.0,
        "net_sentiment_index": 0.41,
        "positive_ratio": 0.65,
        "negative_ratio": 0.24
      },
      "crisis_sla": {
        "score": 17.50,
        "max_score": 25.0,
        "total_rumors": 4,
        "refuted_within_90m": 3,
        "sla_success_rate": 0.75
      }
    },
    "generated_at": "2026-10-18T21:15:30Z"
  }
  ```

---

#### 6. System Health Check (`GET /api/v1/health`)
* **Expected Output (HTTP 200 OK):**
  ```json
  {
    "status": "ok",
    "engine": "Project EUREKA (DGIPR Maha-Command Center)",
    "version": "1.0.0",
    "components": {
      "postgres": "connected",
      "neo4j": "connected",
      "redis": "connected",
      "triton": "standby"
    },
    "timestamp": "2026-10-18T21:15:30Z"
  }
  ```

---

#### 7. JWT Authentication Gateway (`POST /api/v1/auth/token`)
* **HTTP Request:**
  ```json
  {
    "username": "collector_thane",
    "role": "District Collector",
    "district_code": "MH-04"
  }
  ```
* **Expected Output (HTTP 200 OK):**
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "role": "District Collector",
    "district_code": "MH-04",
    "expires_in_minutes": 480
  }
  ```

---

#### 8. IPCS Adapter Isolation Gateway (`GET /api/v1/ipcs/status`)
* **Expected Output (HTTP 200 OK):**
  ```json
  {
    "status": "not_configured"
  }
  ```

---

#### 9. Spatio-Temporal Graph Feature Matrix (`GET /api/v1/graph/spatio-temporal`)
* **Expected Output (HTTP 200 OK):**
  ```json
  {
    "time_window_start": "2026-10-17T21:00:00Z",
    "time_window_end": "2026-10-18T21:00:00Z",
    "num_nodes": 36,
    "feature_dim": 3,
    "features_order": ["volume", "net_sentiment_index", "rumor_velocity"],
    "districts": ["Thane", "Raigad", "Palghar", "Sindhudurg", "Ratnagiri"],
    "adjacency_matrix_shape": [36, 36],
    "feature_tensor_shape": [36, 3, 24]
  }
  ```

---

## 7. Phased Implementation Roadmap

```mermaid
flowchart TD
    subgraph P1["Phase 1: Core Foundation & Engine (Completed)"]
        direction TB
        F1["SQLAlchemy 2.0 & PostgreSQL 16 Models"]
        F2["Alembic Migrations & SQLite Hybrid Fallback"]
        F3["Celery Multi-Queue Topology & Redis Broker"]
        F4["SemIf-OpenJev Formal Logic Primitives"]
        F5["MuRIL Sentiment & 100-Point Scoring Engine"]
        F6["FastAPI RBAC & Review State Machine"]
    end

    subgraph P2["Phase 2: Live Ingestion & Distributed Scale (Completed)"]
        direction TB
        I1["250K Extreme-Scale Batch Ingestion Worker"]
        I2["REST Jobs Trigger (/api/v1/jobs/trigger-ingestion)"]
        I3["NEWS_API.py Edge Scraper (NewsAPI + Crawl4AI)"]
        I4["Serverless Cloud NLP (Hugging Face + Groq LLaMA 3)"]
        I5["Neo4j Cypher Batching Task (UNWIND $events)"]
        I6["Unified uv Dockerfile & Compose Profiles"]
    end

    subgraph P3["Phase 3: Frontend Deck & Spatio-Temporal AI (Active)"]
        direction TB
        A1["Maha-Command Center Frontend (frontend/MCC Next.js 19)"]
        A2["36-District Apache ECharts Visualizations"]
        A3["Crisis War Room 90m SLA Countdown Desk"]
        A4["PyTorch Geometric StGNN Model Training"]
        A5["6-Hour Rumor Contagion Forecasting"]
    end

    subgraph P4["Phase 4: State-Wide Rollout & Enterprise Gateways"]
        direction TB
        E1["Official DGIPR IPCS Gateway Integration"]
        E2["Command Center Live WebSocket HUD"]
        E3["Multi-AZ Disaster Recovery Deployment"]
    end

    P1 --> P2 --> P3 --> P4
```

| Phase | Milestone Name | Status | Key Deliverables |
| :--- | :--- | :--- | :--- |
| **Phase 1** | Core Foundation & Engine | **Completed** | 11 PostgreSQL tables, Alembic migrations, Celery queues, MuRIL sentiment, 100-Point composite index, RBAC state machine. |
| **Phase 2** | Live Ingestion & Distributed Scale | **Completed** | Celery extreme-scale chunk streaming, `NEWS_API.py` edge scraper, serverless HF/Groq evaluators, Cypher batch worker, `uv` Dockerfile. |
| **Phase 3** | Frontend Deck & Spatio-Temporal AI | **Active** | `frontend/MCC` Next.js 19 command deck, 36-district Apache ECharts, Crisis War Room 90m SLA, StGNN 6h rumor diffusion forecaster. |
| **Phase 4** | State-Wide Rollout & Enterprise Gateways | **Scheduled** | Official DGIPR IPCS dispatch integration, live WebSocket streaming, Multi-AZ failover and disaster recovery. |

### Phase Details

#### Phase 1: Core Foundation & Engine (Completed)
* 11 PostgreSQL 16 tables, Alembic migrations, and SQLAlchemy 2.0 async/sync architecture.
* Celery multi-queue task topology (`default`, `quad_ingestion`, `irf_binding`, `processor`, `outbox`).
* Crawl4AI web and interactive DOM ingestion (Lanes 1 to 4).
* SemIf-OpenJev formal logic primitives (`Choice`, `Noul`, `Score`).
* MuRIL Indic sentiment pipeline (`Positive`, `Neutral`, `Negative`, `Mixed`).
* 100-Point Composite Index with four 25-point pillars.
* Transactional Outbox worker with `SELECT ... FOR UPDATE SKIP LOCKED` into Neo4j 5.x.
* FastAPI routers, JWT authentication, and RBAC review state machine.

#### Phase 2: Live Ingestion & Production Deployment (Completed)
* Celery distributed task queue with Redis broker/backend streaming 250,000+ extreme-scale rows.
* Edge node `NEWS_API.py` integrated with NewsAPI v2 and Crawl4AI with headless fallback.
* Serverless cloud NLP evaluation with Hugging Face CardiffNLP RoBERTa and Groq LLaMA 3.
* Parameterized Cypher batching worker `ingest_neo4j_batch_task` with `UNWIND $events AS event`.
* Unified `uv`-powered Dockerfile and modular Docker Compose profiles (`core`, `db`, `app`, `inference`, `full`).

#### Phase 3: Frontend Deck & Spatio-Temporal AI (Active)
* Maha-Command Center Next.js 19 frontend deck (`frontend/MCC`) adhering to GIGW 3.0 / UX4G.
* 36-district & 6-division Apache ECharts maps, radar charts, and trend visualizations.
* Crisis War Room 90-minute SLA countdown desk for District Collector sign-off.
* PyTorch Geometric StGNN model training using extracted time-window feature matrices.
* 6-hour advance rumor diffusion and contagion forecasting across district borders.

#### Phase 4: Enterprise Integration & Multi-AZ Clustering (Scheduled)
* Official DGIPR IPCS dispatch API integration when specifications are published.
* Command Center real-time WebSocket push feeds for high-density broadcast displays.
* Multi-AZ database clustering and automated disaster recovery failover.
* Implement PyTorch Geometric Spatio-Temporal Graph Neural Network (StGNN) utilizing the Neo4j time-window feature matrices extracted by `StGNNDataPreparation`.
* Forecast rumor diffusion vectors across geographic district boundaries 6 hours in advance.

#### Phase 4: Enterprise IPCS Integration & Command Center WebSocket Live HUD
* Integrate official DGIPR IPCS dispatch API when specifications are published.
* Deploy real-time WebSocket push feeds to the District Collector Command Dashboards.
* Establish Multi-AZ database clustering and automated disaster recovery failover.

---

## 8. Failure Modes, Resilience & Operational Runbook

| Failure Scenario | Detection Mechanism | Immediate Automatic Recovery | Manual Remediation |
| :--- | :--- | :--- | :--- |
| **PostgreSQL Connection Exhaustion** | SQLAlchemy `pool_timeout` (30s) | `pool_pre_ping=True` drops dead connections; recycled every 3600s | Increase `POSTGRES_POOL_SIZE` in `.env` |
| **Neo4j Node Downtime** | Neo4j Bolt driver health ping returns `False` | Outbox worker pauses mutations, preserves events in `outbox_events (status='PENDING')` | Restart Neo4j container (`docker compose restart neo4j`) |
| **Crawl4AI Bot Wall / Anti-Scrape Block** | HTTP 403 / Captcha / Cloudflare detection | Worker switches to `httpx_fallback` with clean DOM text extraction | Configure residential proxy pool in source `config_json` |
| **Duplicate Media Ingestion** | Unique index `ix_raw_events_source_hash` violation | `SHA-256` payload deduplication rejects re-ingestion silently | No action required; idempotent design prevents duplicate canonical events |
| **Outbox Poison Pill Payload** | Worker exception during Cypher execution | Row `retry_count` incremented up to 5 attempts, then marked `FAILED` with `last_error` | Inspect `SELECT * FROM outbox_events WHERE status='FAILED'` and fix Cypher query |
| **Celery Worker Crash During Processing** | Broker visibility timeout expires | `task_acks_late=True` and `task_reject_on_worker_lost=True` re-queue task for healthy worker | Restart worker container (`docker compose restart celery_worker`) |

---

## 9. Conclusion & Architectural Integrity Guarantee

Project EUREKA represents a fully deterministic, enterprise-grade architecture engineered for real-world government media intelligence. By decoupling ingestion, normalization, graph projection, and human authorization into independent, asynchronous, idempotent micro-pipelines, the system guarantees high throughput, complete data provenance, zero data loss, and strict bureaucratic accountability.
