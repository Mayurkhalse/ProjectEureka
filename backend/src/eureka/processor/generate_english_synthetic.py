"""Extreme Scale Synthetic English Dataset Generator for Project EUREKA.

Generates 250,000 synthetic records across the 5 pilot districts (Thane, Raigad,
Palghar, Sindhudurg, Ratnagiri) to stress-test backend pipelines across the 4 Core
Pillars:
- Volume (Event distribution across 4 communication types)
- TAT / Speed (Gamma-distributed Turnaround Time in minutes)
- Sentiment (Uniform continuous polarity score in [-1.0, 1.0])
- Crisis SLA (Boolean emergency containment flag with 95% SLA adherence)

Uses iterative chunk-based streaming to disk to prevent Out-Of-Memory (OOM) crashes.
"""

from datetime import datetime, timedelta
import os
from pathlib import Path
import random
import uuid
from typing import Optional

import numpy as np
import pandas as pd


def resolve_default_output_path() -> str:
    """Resolve destination seed_data directory irrespective of invocation working dir."""
    script_dir = Path(__file__).resolve().parent
    # resolve seed_data relative to src directory
    candidate = script_dir.parent.parent.parent / "seed_data"
    if candidate.exists():
        return str(candidate / "english_extreme_scale.csv")
    if Path("backend/seed_data").exists():
        return str(Path("backend/seed_data") / "english_extreme_scale.csv")
    if Path("project-eureka/seed_data").exists():
        return str(Path("project-eureka/seed_data") / "english_extreme_scale.csv")
    os.makedirs("seed_data", exist_ok=True)
    return str(Path("seed_data") / "english_extreme_scale.csv")


def generate_english_dataset(
    output_path: Optional[str] = None,
    total_rows: int = 250000,
    chunk_size: int = 50000,
    seed: int = 42,
) -> str:
    """Generate extreme-scale synthetic English records in memory-safe chunks.

    Args:
        output_path: Target CSV destination path.
        total_rows: Total rows to generate (default: 250,000).
        chunk_size: Rows per batch chunk written to disk (default: 50,000).
        seed: Random seed for reproducible generation.

    Returns:
        Absolute path to the generated CSV file.
    """
    np.random.seed(seed)
    random.seed(seed)

    districts = ["Thane", "Raigad", "Palghar", "Sindhudurg", "Ratnagiri"]
    event_types = ["Press Release", "News Clipping", "Social Media", "Fact-Check Ticket"]

    # Base English templates for realistic text simulation
    templates = [
        "District administration announces new infrastructure project in {}",
        "Local protests reported regarding water shortage in {}",
        "Official clarification issued on highway closures near {}",
        "Viral social media post claims bridge collapse in {}",
        "Collector inaugurates new hospital wing in {}",
        "Emergency advisory issued for unseasonal rainfall across {}",
        "Public grievance cell resolves electricity distribution backlog in {}",
        "Counter-misinformation team debunks false exam leak rumor in {}",
        "Industrial development corporation approves manufacturing zone in {}",
        "Public health department launches vaccination verification drive in {}",
    ]

    dest_path = output_path or resolve_default_output_path()
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)

    print(f"Generating {total_rows:,} synthetic English records in chunks of {chunk_size:,}...")
    print(f"Target Output Path: {dest_path}")

    # Remove existing file if present to guarantee clean stream
    if os.path.exists(dest_path):
        os.remove(dest_path)

    start_time = datetime(2026, 1, 1, 0, 0, 0)
    num_chunks = max(1, total_rows // chunk_size)

    for chunk in range(num_chunks):
        current_chunk_size = chunk_size if chunk < num_chunks - 1 else (total_rows - chunk * chunk_size)

        # 1. Synthesize core metadata aligned with 4 Governance Pillars
        record_ids = [uuid.uuid4().hex for _ in range(current_chunk_size)]
        chosen_districts = np.random.choice(districts, current_chunk_size)
        chosen_event_types = np.random.choice(event_types, current_chunk_size, p=[0.20, 0.40, 0.30, 0.10])

        # Event timestamps spanning a realistic operational calendar
        random_minute_offsets = np.random.randint(0, 120000, size=current_chunk_size)
        timestamps = [start_time + timedelta(minutes=int(m)) for m in random_minute_offsets]

        # Realistic Turnaround Time (TAT) via Gamma distribution (mode around 20-40 min, long tail)
        tat_mins = np.round(np.random.gamma(shape=2.0, scale=20.0, size=current_chunk_size), 1)

        # Continuous sentiment polarity bounded in [-1.0, 1.0]
        sentiments = np.round(np.random.uniform(-1.0, 1.0, size=current_chunk_size), 4)

        # Crisis SLA boolean flag (95% resolved within SLA, 5% active rumor breaches)
        crisis_resolved = np.random.choice([True, False], current_chunk_size, p=[0.95, 0.05])

        # 2. Construct Chunk DataFrame
        chunk_data = {
            "record_id": record_ids,
            "district": chosen_districts,
            "event_type": chosen_event_types,
            "event_timestamp": [ts.isoformat() for ts in timestamps],
            "turnaround_time_mins": tat_mins,
            "sentiment_score": sentiments,
            "crisis_resolved": crisis_resolved,
        }
        df = pd.DataFrame(chunk_data)

        # 3. Vectorized English Content Generation with Anti-Cache Tracing
        df["english_content"] = [
            f"{random.choice(templates).format(d)} [TRACE:{rid[:8]}]"
            for d, rid in zip(df["district"], df["record_id"])
        ]

        # 4. Stream append to CSV (write header on first chunk only)
        df.to_csv(dest_path, mode="a", index=False, header=(chunk == 0))
        print(f"[{chunk + 1:02d}/{num_chunks:02d}] Chunk written successfully: {len(df):,} rows.")

    file_size_mb = os.path.getsize(dest_path) / (1024 * 1024)
    print("\n" + "=" * 60)
    print("SUCCESS: Extreme English dataset generation complete!")
    print(f"Destination: {dest_path}")
    print(f"Total Records: {total_rows:,} rows | Columns: {len(df.columns)}")
    print(f"File Size: {file_size_mb:.2f} MB")
    print("=" * 60)

    return dest_path


if __name__ == "__main__":
    generate_english_dataset()
