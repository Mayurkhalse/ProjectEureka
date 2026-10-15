"""End-to-End Pipeline Verification Test for Synthetic English Scale Dataset.

Verifies:
1. Generation and ingestion readiness of the synthetic English dataset.
2. Presence and non-emptiness of records.
3. Schema conformance with the 4 Core Pillars (Volume, TAT, Sentiment, Crisis SLA).
4. Strict geographic confinement to the 5 Pilot Districts (Thane, Raigad, Palghar, Sindhudurg, Ratnagiri).
"""

import os
from pathlib import Path
import pytest
import pandas as pd
from eureka.processor.generate_english_synthetic import generate_english_dataset


@pytest.fixture(scope="session")
def setup_test_dataset():
    """Ensures the synthetic dataset exists for the CI runner."""
    output_dir = "backend/seed_data" if os.path.exists("backend/seed_data") else "seed_data"
    test_file_path = os.path.join(output_dir, "english_extreme_scale.csv")

    # Generate a quick chunk if it doesn't exist in the CI environment
    if not os.path.exists(test_file_path):
        test_file_path = generate_english_dataset(output_path=test_file_path, total_rows=5000, chunk_size=5000)

    yield test_file_path


def test_pipeline_data_ingestion(setup_test_dataset):
    """Verifies that the EUREKA ingestion pipeline can successfully load

    and parse the synthetic extreme-scale English dataset.
    """
    df = pd.read_csv(setup_test_dataset)

    # Assert data is present
    assert not df.empty, "Synthetic dataset failed to generate or load."

    # Assert schema matches the 4 Core Pillars
    required_cols = [
        "record_id",
        "district",
        "event_type",
        "event_timestamp",
        "turnaround_time_mins",
        "sentiment_score",
        "crisis_resolved",
    ]
    for col in required_cols:
        assert col in df.columns, f"Schema mismatch: missing {col}"

    # Assert geographic boundaries are strictly enforced (the 5 Pilot Districts)
    valid_districts = {"Thane", "Raigad", "Palghar", "Sindhudurg", "Ratnagiri"}
    found_districts = set(df["district"].unique())
    assert found_districts.issubset(valid_districts), "Data leaked outside pilot districts!"
