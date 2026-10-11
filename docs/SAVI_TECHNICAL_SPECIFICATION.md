# SAVI Platform Architecture: Comprehensive Technical Specification

## Executive Summary & System Overview

The **SAVI (Sentiment, Accuracy, Validation, Impact)** Intelligence Platform is an end-to-end, autonomous data harvesting, structural verification, and spatio-temporal analytical infrastructure. Designed to monitor, verify, and quantify cross-platform information propagation, the platform coordinates a quad-agent scraping mesh across Web articles, Reddit discussions, Twitter/X interactions, and YouTube media streams.

Traditional intelligence platforms suffer from three architectural failure modes:

1. **Ingestion Fragility:** Static scrapers trigger cascading HTTP 429 (Too Many Requests), IP blacklisting, and cloud-provider blocks during high-volume events.
2. **Computational Contention:** Coupling heavy relational reads with high-volume graph-traversal computations leads to database deadlocks and high query latency.
3. **Analytical Naivety:** Standard natural language processing models treat news items as independent events, ignoring spatial dissemination vectors, temporal evolution, and coordinated bot manipulation.

SAVI solves these limitations by implementing a segregated computational pipeline:

* An **Adaptive Ingestion Layer** governed by a Point-Based Reinforcement Learning (RL) controller.
* A dynamic **Pipeline Management Router** combined with an **Extended Isolation Forest (Isolation Rainforest)** for non-axis-aligned multidimensional anomaly and bot detection.
* A **Graph Staging & Structural Analytics Engine (Neo4j)** hosting Spatio-Temporal Graph Neural Networks (STGNN) and an Open JEV (Joint Evaluation & Verification) formal logic audit.
* A **Command Query Responsibility Segregation (CQRS)** materialized delivery layer powered by **PostgreSQL** with JSONB indices to serve low-latency queries to client endpoints.

---

## Phase 1: Adaptive Quad-Scraper Layer & Point-Based Reinforcement Learning

The ingestion fabric coordinates four concurrent agent tasks:

* **Agent 1 (Web Ingestion):** Recursive DOM parser extracting sanitized HTML bodies, author metadata, publication timestamps, schema microdata, and primary citation links.
* **Agent 2 (Reddit Ingestion):** Traverses subreddits, extracts nested comment trees, flairs, author account ages, and upvote/downvote ratios.
* **Agent 3 (Twitter/X Ingestion):** Parses tweet payloads, reply cascades, quote tweets, retweet chains, follower/following ratios, and verification metadata.
* **Agent 4 (YouTube Multimodal Ingestion):** Ingests video metadata, user comments, timed closed-caption transcripts, and keyframe visual vector embeddings extracted via a localized vision backbone.

### Point-Based Reinforcement Learning Control Model

Scraping execution is governed by an automated agent modeled as a Markov Decision Process (MDP) defined by the tuple $\langle \mathcal{S}, \mathcal{A}, \mathcal{P}, \mathcal{R}, \gamma \rangle$.

#### State Space ($\mathcal{S}$)

The system state $s_t \in \mathcal{S}$ at step $t$ is a continuous multi-dimensional vector:

$$s_t = \Big[ \Delta \tau_{req}, \rho_{proxy}, \kappa_{429}, \mu_{latency}, \sigma_{dom\_drift}, \xi_{quota\_remaining} \Big]$$

Where:

* $\Delta \tau_{req}$: Inter-request time interval (ms).
* $\rho_{proxy}$: Health score of the current active proxy pool (ratio of successful calls over the last 100 requests).
* $\kappa_{429}$: Running exponential moving average of rate-limit responses.
* $\mu_{latency}$: Target platform server response latency (ms).
* $\sigma_{dom\_drift}$: Quantified distance in page layout structure indicating target site anti-bot updates.
* $\xi_{quota\_remaining}$: Fraction of remaining quota across the API key rotation set.

#### Action Space ($\mathcal{A}$)

The action $a_t \in \mathcal{A}$ selected by the control policy determines immediate request execution behavior:

* $a_1$: Step-wise decrease inter-request delay ($\Delta \tau_{req} - \delta t$).
* $a_2$: Step-wise increase inter-request delay ($\Delta \tau_{req} + \delta t$).
* $a_3$: Execute atomic context-preserving key rotation.
* $a_4$: Rotate residential proxy subnet.
* $a_5$: Switch parser strategy (e.g., transition from API REST endpoint to headless browser DOM extraction).
* $a_6$: Soft-backoff (pause queue execution for duration $T_{backoff}$).

#### Formulation of the Point-Based Reward Function

The scraper receives a scalar feedback reward $R_t$ at step $t$, parameterizing data yield against operational risk:

$$R_t = \omega_1 \cdot V_{valid} - \omega_2 \cdot E_{429} - \omega_3 \cdot \left(\frac{L_{ms}}{1000}\right) - \omega_4 \cdot C_{captcha} - \omega_5 \cdot \mathbb{I}_{ban}$$

Where:

* $V_{valid} \in \mathbb{N}$: Number of unique, uncorrupted, schema-compliant payloads successfully retrieved.
* $E_{429} \in \{0, 1\}$: Binary penalty triggered upon receiving an HTTP 429 or HTTP 402 code.
* $L_{ms} \in \mathbb{R}^+$: Round-trip HTTP/gRPC latency measured in milliseconds.
* $C_{captcha} \in \{0, 1\}$: Binary penalty for hitting Cloudflare, reCAPTCHA, or bot-challenge interstitial screens.
* $\mathbb{I}_{ban} \in \{0, 1\}$: Severe terminal penalty if an IP subnet or API credential suffers an active revocation.
* $\omega_1, \omega_2, \omega_3, \omega_4, \omega_5$: Weight regularization hyperparameters adjusted such that $\omega_5 \gg \omega_2 > \omega_4 \gg \omega_1 > \omega_3$.

#### Policy Optimization: Proximal Policy Optimization (PPO)

The policy parameters $\theta$ are updated iteratively using the PPO clipped surrogate objective function:

$$L^{CLIP}(\theta) = \hat{\mathbb{E}}_t \left[ \min\left(r_t(\theta)\hat{A}_t, \, \text{clip}(r_t(\theta), 1-\epsilon, 1+\epsilon)\hat{A}_t\right) \right]$$

Where the probability ratio is defined as:

$$r_t(\theta) = \frac{\pi_\theta(a_t \vert{} s_t)}{\pi_{\theta_{old}}(a_t \vert{} s_t)}$$

and $\hat{A}_t$ is the Generalized Advantage Estimator (GAE) across operational scraping epochs, ensuring stable policy transitions without causing catastrophic service disruption.

---

## Phase 2: Pipeline Orchestration & Isolation Rainforest Filtering

Raw harvested items are transformed into canonical data envelopes over an internal gRPC bus and routed through a dynamic pipeline controller.

### Pipeline Management: Dynamic DAG Router

A high-throughput Directed Acyclic Graph (DAG) evaluates each content payload $x_i$ to dynamically dictate processing concurrency:

1. **Micro-Event Route (Independent/Parallel Pipeline):** Content identified with localized, single-platform engagement and low propagation velocity bypasses multi-agent batching and executes lightweight feature extraction immediately.
2. **Macro-Cascade Route (Grouped/Synchronous Pipeline):** Content exhibiting cross-platform entity matching within a defined temporal window ($\Delta t \le 15\text{ min}$) is routed into a shared temporal buffer for coordinated spatio-temporal graph construction.

```
                  [ Ingestion Envelopes (gRPC) ]
                                |
                                v
               [ Dynamic DAG Pipeline Controller ]
               /                                 \
  (Micro-Event: Single Source)        (Macro-Cascade: Cross-Platform)
             /                                     \
    [ Parallel Pipeline ]                  [ Synchronous Batcher ]
             \                                     /
              -----> [ Isolation Rainforest ] <----
```

### Multidimensional Outlier Isolation: Isolation Rainforest

To protect downstream graph systems from coordinated astroturfing campaigns, synthetic bot storms, and engagement spam, data passes through an **Extended Isolation Forest (Isolation Rainforest)**.

Standard Isolation Forests partition feature space using axis-aligned orthogonal cuts ($x_j \le v$), which creates structural artifacts and fails to isolate correlated, multi-dimensional anomalies (such as an artificial ratio between Twitter impressions and YouTube views). The Extended Isolation Forest introduces random, non-axis-aligned slicing hyperplanes.

#### Hyperplane Splitting Formulation

At each node in an isolation tree, a cut is defined by choosing an arbitrary normal vector $\vec{n} \in \mathbb{R}^d$ drawn from a standard Gaussian distribution, and a intercept point $\vec{p}$ drawn uniformly from the data domain:

$$(\vec{x} - \vec{p}) \cdot \vec{n} \le 0$$

Data points satisfying this inequality traverse to the left child node; otherwise, they proceed to the right.

#### Anomaly Scoring Algorithm

For an observation vector $\vec{x} \in \mathbb{R}^d$ comprising engagement signals, author age metrics, token perplexities, and velocity gradients, the path length $h(\vec{x})$ is the number of edges traversed until termination.

The anomaly score $s(\vec{x}, n)$ across an ensemble of $T$ trees over a sample size of $n$ instances is formulated as:

$$s(\vec{x}, n) = 2^{-\frac{\mathbb{E}[h(\vec{x})]}{c(n)}}$$

Where the average path length of an unsuccessful search in an equivalent Binary Search Tree (BST) is:

$$c(n) = 2\left(\ln(n - 1) + \gamma_E\right) - \frac{2(n - 1)}{n}$$

*(Where $\gamma_E \approx 0.5772156649$ is the Euler–Mascheroni constant).*

#### Decision Boundary Logic

* If $s(\vec{x}, n) \to 1.0$: The item isolates at extremely shallow tree depths, denoting an unnatural synthetic anomaly or engagement fraud. **Payload is routed to a quarantine queue for agent penalty backpropagation.**
* If $s(\vec{x}, n) < 0.50$: The instance displays organic propagation behavior and is passed down the pipeline.
* If $0.50 \le s(\vec{x}, n) \le 0.65$: The instance is flagged with an anomaly penalty weight and dispatched to Neo4j with an elevated verification threshold.

---

## Phase 3: Graph Structuring & Analytical Compute Engine (Neo4j)

Sanitized payloads pass directly into **Neo4j**, which functions as the platform's high-speed topological staging and structural computational memory.

```
       [ Clean Data Payloads ]
                  |
                  v
       +---------------------------------------------+
       |   Neo4j In-Memory Graph Processing Engine   |
       |                                             |
       |   1. Entity / Triplet Extraction (S, P, O)  |
       |   2. Community Clustering (Louvain)        |
       |   3. Spatio-Temporal GNN (STGNN)            |
       |   4. Open JEV Logical Reasoning Audit       |
       +---------------------------------------------+
```

### Knowledge Graph Construction & Community Detection

Payloads are processed through an Open Information Extraction pipeline that pulls Subject-Predicate-Object triplets:

$$\mathcal{E} = (e_{subject}, r_{predicate}, e_{object})$$

Nodes represent entities, platforms, authors, and claims; edges define citation trails, retweets, shared URL hashes, or structural semantic entailments.

To detect coordinated informational sub-networks, the engine executes the **Louvain Modularity Optimization Algorithm**:

$$Q = \frac{1}{2m} \sum_{i, j} \left[ A_{ij} - \frac{k_i k_j}{2m} \right] \delta(c_i, c_j)$$

Where:

* $A_{ij}$: Edge weight between nodes $i$ and $j$.
* $k_i, k_j$: Sum of the weights of the edges attached to nodes $i$ and $j$.
* $m = \frac{1}{2}\sum_{ij} A_{ij}$: Total weight of all edges within the graph.
* $\delta(c_i, c_j)$: Kronecker delta function, evaluating to 1 if node $i$ and $j$ belong to the same community $c$, and 0 otherwise.

### Spatio-Temporal Graph Neural Network (STGNN) Formulation

The STGNN models spatial network relationships alongside temporal trajectory metrics simultaneously.

#### Spatial Convolution (Graph Convolutional Layer)

Spatial information aggregation across the dynamic cross-platform topology is governed by localized first-order spectral graph convolutions:

$$Z^{(l)} = \tilde{D}^{-\frac{1}{2}} \tilde{A} \tilde{D}^{-\frac{1}{2}} H^{(l)} W_S^{(l)}$$

Where:

* $\tilde{A} = A + I_N$: The graph adjacency matrix augmented with self-connections.
* $\tilde{D}_{ii} = \sum_j \tilde{A}_{ij}$: The diagonal node degree matrix.
* $H^{(l)}$: Node activation matrix at layer $l$, where $H^{(0)} = X$ corresponds to the initial multi-modal node feature embeddings.
* $W_S^{(l)}$: Trainable spatial weight matrix.

#### Temporal Gated Convolution

Temporal feature extraction across sliding publication windows $\Delta t$ is computed via Gated Temporal Convolutions (GLU):

$$\Phi(Y) = (Y * \Theta_1 + b_1) \odot \sigma(Y * \Theta_2 + b_2)$$

Where:

* $Y \in \mathbb{R}^{M \times C_i}$: The sequence of historical node embeddings across time steps.
* $*$ denotes the 1D causal convolution operator.
* $\Theta_1, \Theta_2$ and $b_1, b_2$: Convolutional kernel parameters and biases.
* $\odot$: The Hadamard element-wise product.
* $\sigma(\cdot)$: The sigmoid activation function gating the flow of temporal dynamics.

The composite STGNN spatio-temporal block alternates spatial graph convolutions with temporal convolutions to produce a finalized dynamic embedding $H_{ST} \in \mathbb{R}^{N \times d}$ representing the combined propagation state.

### Open JEV (Joint Evaluation & Verification) Logic Engine

To ensure rigorous validation, the derived STGNN representations are evaluated against an Open JEV symbolic logic module to test for entailment and eliminate false positives from sarcasm or rhetoric.

Given a claim triplet $T_c = (s_c, p_c, o_c)$ and supporting evidence triplets $T_e \in \mathcal{K}_{Neo4j}$, Open JEV calculates a multi-class verification probability:

$$P(\text{Class} \vert{} T_c, \mathcal{K}) = \text{Softmax}\left( W_v \cdot \left[ H_{T_c} \mathbin{\Vert} H_{\mathcal{K}} \mathbin{\Vert} \vert{}H_{T_c} - H_{\mathcal{K}}\vert{} \mathbin{\Vert} (H_{T_c} \odot H_{\mathcal{K}}) \right] \right)$$

Classes are partitioned into:

1. **Entailment ($\mathcal{C}_{ent}$):** The observed multi-source assertions logically confirm the claim.
2. **Contradiction ($\mathcal{C}_{con}$):** The assertion directly breaches established real-world facts or authoritative sources.
3. **Neutral / Unsubstantiated ($\mathcal{C}_{neu}$):** Insufficient topological cross-referencing available.

---

## Phase 4: SAVI Analytical Formulation Matrix

The consolidated analytical state for each tracked narrative is encapsulated into the **SAVI Metric Suite**:

| Dimension | Primary Metric Formulation | Functional Description |
| --- | --- | --- |
| **S** - Sentiment Dynamics | $S_{dyn}(t) = \int_{0}^t \left( \nabla \vec{S}_{plat}(\tau) \cdot e^{-\lambda(t-\tau)} \right) d\tau$ | Tracks directional drift and velocity of affective polarity across platforms, penalizing decayed historic states. |
| **A** - Factual Accuracy | $A_{score} = \mu_{topo} \cdot P(\mathcal{C}_{ent}) \cdot \left(1 - \frac{1}{\sum W_{authority}}\right)$ | Measures cross-platform topological convergence scaled by the Open JEV logical entailment probability. |
| **V** - Logical Validation | $V_{index} = 1.0 - \left( \frac{\kappa_{contradictions} + s(\vec{x}, n)}{2} \right)$ | Audits structural coherence against the Isolation Rainforest anomaly score $s(\vec{x},n)$ to penalize bot manipulation. |
| **I** - News Impact Index | $I_{impact} = \sum_{m \in \mathcal{M}} \left( E_n^{(m)} \cdot \mathcal{C}_B(m) \right) \cdot \frac{d\mathcal{V}}{dt}$ | Quantifies global propagation reach via normalized engagement $E_n$, betweenness centrality $\mathcal{C}_B$, and transmission velocity. |

---

## Phase 5: Persistence, CQRS & Low-Latency Materialization (PostgreSQL)

To prevent resource contention between write-heavy graph operations and user-facing analytical reads, SAVI enforces **Command Query Responsibility Segregation (CQRS)**.

```
+--------------------------------------------------------+
|         Neo4j Graph Engine (Command / Compute)         |
+--------------------------------------------------------+
                           |
            [ Async Transaction Sink / CDC ]
                           |
                           v
+--------------------------------------------------------+
|       PostgreSQL Intelligence Master (Query / Serve)   |
|                                                        |
|  - Materialized Relational Views for B-Tree Filtering  |
|  - JSONB Engines for Deep Explainable Audit Logs       |
|  - Gin Indexing for Real-Time Client Dashboards        |
+--------------------------------------------------------+
                           |
              [ API & User Applications ]
```

### CQRS Architecture

1. **Neo4j (Command Store):** Executes all high-throughput write-heavy tasks, topological community calculations, node embedding updates, and triplet traversals. No client dashboard queries hit this cluster directly.
2. **PostgreSQL (Query Store):** Houses materialized analytical views and stores historical states. Write operations are populated through an asynchronous, transactional worker pool processing finalized SAVI states.

### Relational Schema & Materialized JSONB Definition

```sql
-- Core Table: Platform Intelligence Master
CREATE TABLE intelligence_master (
    content_id UUID PRIMARY KEY,
    canonical_hash VARCHAR(64) UNIQUE NOT NULL,
    primary_headline TEXT NOT NULL,
    origin_platform VARCHAR(16) NOT NULL,
    published_timestamp TIMESTAMPTZ NOT NULL,
    processed_timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    
    -- Structured Metric Columns for Fast B-Tree Indexing
    sentiment_score REAL NOT NULL,
    accuracy_rating REAL NOT NULL,
    validation_index REAL NOT NULL,
    impact_ranking REAL NOT NULL,
    anomaly_metric REAL NOT NULL,

    -- Unstructured & Complex Reasoning Engines stored in JSONB
    open_jev_audit JSONB NOT NULL,
    platform_distribution JSONB NOT NULL,
    multimodal_features JSONB
);

-- Indices for Low-Latency Query Execution
CREATE INDEX idx_intelligence_impact_acc 
ON intelligence_master (impact_ranking DESC, accuracy_rating DESC);

CREATE INDEX idx_intelligence_pub_time 
ON intelligence_master (published_timestamp DESC);

CREATE INDEX idx_open_jev_audit_gin 
ON intelligence_master USING GIN (open_jev_audit);

-- Materialized View for Real-Time Client Dashboards
CREATE MATERIALIZED VIEW mv_top_impact_intelligence AS
SELECT 
    content_id,
    primary_headline,
    origin_platform,
    accuracy_rating,
    impact_ranking,
    open_jev_audit->>'verdict' AS factual_verdict,
    open_jev_audit->'reasoning_chain' AS reasoning_nodes,
    platform_distribution
FROM intelligence_master
WHERE published_timestamp >= NOW() - INTERVAL '24 HOURS'
  AND anomaly_metric < 0.65
ORDER BY impact_ranking DESC
LIMIT 100;

CREATE UNIQUE INDEX idx_mv_content_id ON mv_top_impact_intelligence (content_id);
```

---

## Architectural Comparison Matrix

| Architectural Layer | Prior Architecture (v2) | Redesigned Architecture (Current) | Engineering Impact |
| --- | --- | --- | --- |
| **Ingestion Engine** | Hardcoded key-swapping logic; vulnerable to 429 cascades. | Point-Based Reinforcement Learning (PPO) with dynamic action space. | Mitigates rate-limit bans; adapts dynamically to proxy degradation and DOM changes. |
| **Pipeline Ingestion** | Static parallel queuing. | Dynamic DAG Router (Independent vs. Cascaded Parallelism). | Optimizes compute usage; bypasses heavy multi-source synchronization for localized events. |
| **Anomaly Filtering** | MinHash LSH and Cosine similarity checks. | Extended Isolation Forest (Isolation Rainforest) with oblique hyperplanes. | Detects non-linear, multi-modal engagement anomalies and bot manipulation schemes. |
| **Structural Compute** | Distributed across relational files and Neo4j. | Dedicated Neo4j In-Memory Compute Staging layer. | High-speed topological community detection and graph feature extraction for STGNN models. |
| **Persistence Engine** | Master SQLite (`platform_intelligence.db`). | CQRS-patterned PostgreSQL Master with JSONB and Materialized Views. | Prevents database write-locks; provides sub-10ms API responses for concurrent users. |

---

## End-to-End System Sequence Diagram

```
Scraper Quad     PPO Controller      DAG Router     Isolation Forest      Neo4j (STGNN)       PostgreSQL Master       User Client
     |                 |                 |                  |                   |                     |                |
     |-- Fetch HTML -->|                 |                  |                   |                     |                |
     |<- Adjust Wait --|                 |                  |                   |                     |                |
     |                                   |                  |                   |                     |                |
     |---- Raw Ingestion Payload ------->|                  |                   |                     |                |
     |                                   |-- Assess Route ->|                   |                     |                |
     |                                   |                  |-- Eval Vector --->|                     |                |
     |                                   |                  |<- Anomaly < 0.65 -|                     |                |
     |                                   |                                      |                     |                |
     |                                   |------------- Bulk Graph Ingest ----->|                     |                |
     |                                                                          |-- Run STGNN Convolution             |
     |                                                                          |-- Open JEV Entailment               |
     |                                                                          |                                     |
     |                                                                          |--- Materialize SAVI State --------->|
     |                                                                                                                |<- Poll UI -
     |                                                                                                                |-- Results -
```

This completes the end-to-end technical documentation for the redesigned SAVI architecture, covering each operational stage from reinforcement-controlled ingestion to graph processing and materialized database serving.
