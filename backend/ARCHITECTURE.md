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
    end

    subgraph Ingestion ["Ingestion Mesh (QUAD Subsystem)"]
        API_CONN["httpx Connectors (Lanes 1 & 2)"]
        CRAWL_CONN["Crawl4AI Engine (Lanes 3 & 4)"]
        SHA["SHA-256 Deterministic Provenance Hasher"]
    end

    subgraph MessageQueue ["Distributed Queue & Scheduler (Redis 7.x)"]
        Q_QUAD["Queue: quad_ingestion"]
        Q_IRF["Queue: irf_binding"]
        Q_PROC["Queue: processor"]
        Q_OUT["Queue: outbox"]
        BEAT["Celery Beat Scheduler (5s Outbox / 15m Scoring)"]
    end

    subgraph RelationalDB ["Transactional Source of Truth (PostgreSQL 16)"]
        T_RAW["raw_events (Immutable Payloads)"]
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
        N_DIST["(:District)"]
        N_DEPT["(:Department)"]
        N_CANON["(:CanonicalEvent)"]
        N_REL["(:Release)"]
        N_CLAIM["(:Claim)"]
    end

    subgraph API_Layer ["API & Governance Layer (FastAPI)"]
        JWT_AUTH["JWT RBAC Middleware (State Admin / Collector / DIO Desk)"]
        EP_HEALTH["GET /api/v1/health"]
        EP_QUAD["POST /api/v1/quad/ingest"]
        EP_REV["POST /api/v1/conclusions/{id}/review"]
        EP_SCORE["GET /api/v1/scoring/latest"]
        EP_GRAPH["GET /api/v1/graph/spatio-temporal"]
    end

    S1 & S2 --> API_CONN
    S3 & S4 --> CRAWL_CONN
    API_CONN & CRAWL_CONN --> SHA --> Q_QUAD
    Q_QUAD --> T_RAW
    T_RAW --> Q_IRF --> NORM_ENG --> T_NORM
    T_NORM --> OPENJEV --> T_DEC & T_CANON & T_OUTBOX
    T_CANON --> Q_PROC --> MURIL --> T_CANON
    T_OUTBOX --> Q_OUT --> OUTBOX_WORKER
    OUTBOX_WORKER --> N_DIST & N_DEPT & N_CANON & N_REL & N_CLAIM
    BEAT --> Q_PROC & Q_OUT
    API_Layer --> RelationalDB & GraphDB
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

## 7. Phased Implementation Roadmap

```mermaid
gantt
    title Project EUREKA Engineering Delivery Roadmap
    dateFormat  YYYY-MM-DD
    section Phase 1 (Foundation)
    Hybrid DB & SQLAlchemy 2.0 Models       :done, p1_1, 2026-10-01, 2026-10-05
    Alembic Migrations & PostgreSQL 16      :done, p1_2, 2026-10-04, 2026-10-07
    Neo4j Outbox Worker & Transaction Lock  :done, p1_3, 2026-10-06, 2026-10-09
    QUAD Ingestion (httpx & Crawl4AI)       :done, p1_4, 2026-10-08, 2026-10-11
    SemIf-OpenJev IRF Binding Engine        :done, p1_5, 2026-10-10, 2026-10-12
    MuRIL NLP Head & 100-Point Scoring      :done, p1_6, 2026-10-11, 2026-10-13
    FastAPI RBAC & Review State Machine     :done, p1_7, 2026-10-12, 2026-10-13

    section Phase 2 (Production Deployment)
    Docker Compose Daemon Clustering        :active, p2_1, 2026-10-14, 2026-10-18
    DGIPR Live Source Onboarding (36 Dist.) :p2_2, 2026-10-16, 2026-10-24
    Nginx Reverse Proxy & SSL Hardening    :p2_3, 2026-10-20, 2026-10-26

    section Phase 3 (Advanced AI & StGNN)
    Marathi DGIPR Corpus MuRIL Fine-Tuning  :p3_1, 2026-10-27, 2026-11-10
    PyTorch Geometric StGNN Model Training :p3_2, 2026-11-05, 2026-11-20
    Real-Time Rumor Diffusion Forecasting  :p3_3, 2026-11-15, 2026-11-30

    section Phase 4 (Enterprise Integration)
    Official DGIPR IPCS Gateway Integration:p4_1, 2026-12-01, 2026-12-15
    Command Center WebSocket Broadcast HUD  :p4_2, 2026-12-10, 2026-12-25
    Disaster Recovery & Multi-AZ Clustering :p4_3, 2026-12-20, 2027-01-10
```

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

#### Phase 2: Live Ingestion & Production Deployment (Current Phase)
* Initialize Docker Desktop / Linux systemd daemon on target VPS host.
* Register official Maharashtra departmental endpoints (e.g., Disaster Management, Agriculture, Public Health).
* Establish Nginx reverse proxy with SSL termination and API rate limiting.

#### Phase 3: Fine-Tuned Indic ML & StGNN Graph Model Training
* Fine-tune `google/muril-base-cased` on 50,000 verified Marathi government releases.
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
