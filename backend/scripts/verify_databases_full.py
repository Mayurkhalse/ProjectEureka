"""Project EUREKA: Comprehensive Multi-Store Verification Harness.

Audits:
1. PostgreSQL 16 live instance: row counts for all tables and views.
2. Neo4j 5.x graph instance: node and relationship counts.
3. SQLite local fallback files: presence, sizes, and record counts.
"""

import os
import sys
from pathlib import Path
from dotenv import find_dotenv, load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(find_dotenv(usecwd=True))

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from eureka.core.config import get_settings
from eureka.core.neo4j_driver import Neo4jGraphService


def audit_postgresql():
    print("=" * 60)
    print("  POSTGRESQL 16 CLUSTER AUDIT")
    print("=" * 60)
    settings = get_settings()
    engine = create_engine(settings.sync_database_url)
    with engine.connect() as conn:
        tables = [
            r[0]
            for r in conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name")
            ).fetchall()
        ]
        print(f"Total Tables in PostgreSQL: {len(tables)}\n")
        total_rows = 0
        for t in tables:
            try:
                cnt = conn.execute(text(f'SELECT count(*) FROM "{t}"')).scalar()
                total_rows += cnt
                print(f"  {t:<32} : {cnt:>8,} rows")
            except Exception as e:
                print(f"  {t:<32} : Error ({e})")
        print(f"\n  TOTAL ROWS IN POSTGRESQL: {total_rows:,}\n")


def audit_neo4j():
    print("=" * 60)
    print("  NEO4J 5.x GRAPH CLUSTER AUDIT")
    print("=" * 60)
    queries = {
        "Districts (:District)": "MATCH (d:District) RETURN count(d) AS count",
        "Departments (:Department)": "MATCH (d:Department) RETURN count(d) AS count",
        "Canonical Events (:CanonicalEvent)": "MATCH (c:CanonicalEvent) RETURN count(c) AS count",
        "Media Events (:MediaEvent)": "MATCH (m:MediaEvent) RETURN count(m) AS count",
        "Borders ([:BORDERS])": "MATCH ()-[r:BORDERS]->() RETURN count(r) AS count",
        "Has Event ([:HAS_EVENT])": "MATCH ()-[r:HAS_EVENT]->() RETURN count(r) AS count",
        "Affects ([:AFFECTS])": "MATCH ()-[r:AFFECTS]->() RETURN count(r) AS count",
    }
    for label, q in queries.items():
        try:
            res = Neo4jGraphService.run_query(q)
            cnt = res[0]["count"] if res else 0
            print(f"  {label:<38} : {cnt:>8,}")
        except Exception as exc:
            print(f"  {label:<38} : Error ({exc})")
    print()


def audit_sqlite_files():
    print("=" * 60)
    print("  SQLITE LOCAL FALLBACK FILES (.db)")
    print("=" * 60)
    files = [
        Path(__file__).resolve().parent.parent / "eureka.db",
        Path(__file__).resolve().parent.parent.parent / "eureka_db.db",
        Path(__file__).resolve().parent.parent.parent / "savi_query_store.db",
    ]
    for f in files:
        if f.exists():
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"  File: {f.name:<24} Path: {f} ({size_mb:.2f} MB)")
            try:
                eng = create_engine(f"sqlite:///{f}")
                with eng.connect() as conn:
                    tables = [r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()]
                    print(f"    Tables ({len(tables)}): {', '.join(tables[:6])}...")
            except Exception as e:
                print(f"    Inspect notice: {e}")
        else:
            print(f"  File: {f.name:<24} NOT FOUND")
    print()


if __name__ == "__main__":
    audit_postgresql()
    audit_neo4j()
    audit_sqlite_files()
