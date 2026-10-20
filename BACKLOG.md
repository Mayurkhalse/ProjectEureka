# EUREKA Open UI Copilot v4 - Deferred Backlog

The following non-blocking and exploratory tasks were deferred to keep execution rapid and stable:

1. **Latency Stress & Load Scripts**: Automated multi-user concurrency benchmarking under Apache Bench / Locust.
2. **Context.md Formula Corrections**: Mathematical documentation clarifications for Volume S-curve and A3TGCN.
3. **Qdrant Cluster Upgrade**: Container pinned to `v1.13.2`; cluster distributed mode deferred.
4. **Redis-Shared Sliding-Window Rate Limits**: Currently using in-memory bounded timestamp pruning per instance.
5. **Response Cache Layer**: Caching deterministic view specs for repeated identical queries.
6. **Promoting Thesys C1 to Global Default**: C1 engine available via `COPILOT_UI_ENGINE=c1`; deterministic remains default.
7. **DGIPR 6-to-9 Division Database Migrations**: SQLite and Postgres currently recognize both division codes and names without destructive schema changes.
