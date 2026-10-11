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
