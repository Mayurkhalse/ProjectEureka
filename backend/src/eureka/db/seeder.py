"""Local SQLite bulk ingestion seeder for Project EUREKA."""

import os
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine
from eureka.db.models import Base, MediaEvent


def resolve_paths():
    """Resolve database path and seed CSV path dynamically across environments."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Ascend from backend/src/eureka/db to workspace root
    root_dir = os.path.abspath(os.path.join(current_dir, "../../../../"))
    db_path = os.path.join(root_dir, "eureka_db.db")

    csv_candidates = [
        os.path.join(root_dir, "backend/seed_data/english_extreme_scale.csv"),
        os.path.join(root_dir, "seed_data/english_extreme_scale.csv"),
        "backend/seed_data/english_extreme_scale.csv",
        "seed_data/english_extreme_scale.csv",
    ]
    seed_csv = None
    for cand in csv_candidates:
        if os.path.exists(cand):
            seed_csv = os.path.abspath(cand)
            break

    if not seed_csv:
        try:
            from eureka.processor.generate_english_synthetic import generate_english_dataset

            fallback_target = os.path.join(root_dir, "backend/seed_data/english_extreme_scale.csv")
            seed_csv = generate_english_dataset(output_path=fallback_target, total_rows=10000, chunk_size=10000)
        except Exception:
            pass

    return db_path, seed_csv


DB_PATH, SEED_CSV = resolve_paths()
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{Path(DB_PATH).as_posix()}")


def seed_database(limit_rows: int = None, chunk_size: int = 10000):
    """Seed the embedded SQLite database from the extreme-scale dataset.

    Args:
        limit_rows: Optional row ceiling for fast testing.
        chunk_size: Size of pandas chunks to stream into SQLite.
    """
    print(f"Connecting to embedded SQLite database at: {DB_PATH}")
    engine = create_engine(DATABASE_URL)

    print("Initializing tables via SQLAlchemy Base metadata...")
    Base.metadata.create_all(bind=engine)

    if not SEED_CSV or not os.path.exists(SEED_CSV):
        raise FileNotFoundError(f"Seed file not found. Checked: {SEED_CSV}")

    print(f"Starting chunked stream ingestion from {SEED_CSV} (chunk_size={chunk_size})...")

    # Clear table if re-seeding to prevent duplicate primary key violations
    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM media_events")

    total_inserted = 0
    valid_cols = [c.name for c in MediaEvent.__table__.columns]

    for idx, chunk in enumerate(pd.read_csv(SEED_CSV, chunksize=chunk_size)):
        if limit_rows and total_inserted >= limit_rows:
            break

        if limit_rows and (total_inserted + len(chunk)) > limit_rows:
            chunk = chunk.iloc[: limit_rows - total_inserted]

        chunk["event_timestamp"] = pd.to_datetime(chunk["event_timestamp"])
        filtered_cols = [col for col in valid_cols if col in chunk.columns]
        chunk[filtered_cols].to_sql("media_events", engine, if_exists="append", index=False)

        total_inserted += len(chunk)
        print(f"Inserted chunk {idx + 1} | Cumulative Rows: {total_inserted}")

    print(f"Ingestion successful: {total_inserted} records committed to {DB_PATH}.")
    return total_inserted


if __name__ == "__main__":
    seed_database()
