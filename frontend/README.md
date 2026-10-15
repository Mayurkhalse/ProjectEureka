# Frontend: Deferred for Initial API & Backend Pipeline Validation

Frontend integration is intentionally deferred.
Project EUREKA is operating in pure headless backend mode:
- FastAPI Application
- Celery Asynchronous Workers & Beat
- NVIDIA Triton Inference Server (INT8 PTQ)
- Neo4j Graph Database
- PostgreSQL Relational ACID Store
