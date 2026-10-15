"""FastAPI router for generating live performance reports and composite index calculations via SQLite."""

import os
from pathlib import Path
from typing import Any, Dict
from fastapi import APIRouter, HTTPException
import pandas as pd
from sqlalchemy import create_engine

router = APIRouter(prefix="/api/v1/reports", tags=["System Reports"])


def resolve_db_path() -> str:
    """Resolve location of eureka_db.db dynamically."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(current_dir, "../../../../"))
    candidates = [
        os.path.join(root_dir, "eureka_db.db"),
        os.path.abspath("eureka_db.db"),
        os.path.join(os.getcwd(), "eureka_db.db"),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
    return os.path.join(root_dir, "eureka_db.db")


@router.get("/district-performance", summary="Generate 100-Point District Leaderboard Report")
def get_district_performance_report() -> Dict[str, Any]:
    database_url = os.getenv("DATABASE_URL")
    datastore_name = "PostgreSQL"

    if not database_url:
        db_path = resolve_db_path()
        if not os.path.exists(db_path):
            raise HTTPException(
                status_code=404,
                detail="SQLite database 'eureka_db.db' not found. Run 'uv run python backend/src/eureka/db/seeder.py' first.",
            )
        database_url = f"sqlite:///{Path(db_path).as_posix()}"
        datastore_name = "SQLite embedded (eureka_db.db)"
    elif "sqlite" in database_url.lower():
        datastore_name = "SQLite embedded (eureka_db.db)"

    try:
        engine = create_engine(database_url)

        # Pull records from the embedded database
        query = "SELECT district, event_type, turnaround_time_mins, sentiment_score, crisis_resolved FROM media_events"
        df = pd.read_sql(query, engine)

        if df.empty:
            raise HTTPException(status_code=404, detail="Table 'media_events' is empty.")

        report_data = []
        for district, group in df.groupby("district"):
            total_releases = len(group[group["event_type"] == "Press Release"])
            avg_tat = float(group["turnaround_time_mins"].mean())
            net_sentiment = float(group["sentiment_score"].mean())

            crisis_tickets = group[group["event_type"] == "Fact-Check Ticket"]
            resolved_ratio = (
                float(crisis_tickets["crisis_resolved"].sum() / len(crisis_tickets))
                if len(crisis_tickets) > 0
                else 1.0
            )

            # 100-Point Composite Metric Calculations:
            # 1. Volume: min(25, (total_releases / 300) * 25)
            volume_score = min(25.0, (total_releases / 300.0) * 25.0)

            # 2. Speed / TAT SLA: 45m = 25 pts, 120m = 0 pts (linear degradation)
            if avg_tat <= 45.0:
                tat_score = 25.0
            elif avg_tat >= 120.0:
                tat_score = 0.0
            else:
                tat_score = 25.0 * (1.0 - ((avg_tat - 45.0) / 75.0))

            # 3. Media Sentiment: ((NSI + 1.0) / 2) * 25
            sentiment_score = ((net_sentiment + 1.0) / 2.0) * 25.0

            # 4. Crisis Containment SLA: (Rumors Refuted / Total Rumors) * 25
            crisis_score = resolved_ratio * 25.0

            total_index = volume_score + tat_score + sentiment_score + crisis_score

            report_data.append({
                "district": district,
                "raw_metrics": {
                    "total_releases": total_releases,
                    "average_tat_minutes": round(avg_tat, 2),
                    "net_sentiment": round(net_sentiment, 3),
                    "crisis_resolution_rate": f"{round(resolved_ratio * 100, 1)}%",
                },
                "pillar_scores": {
                    "volume": round(volume_score, 2),
                    "speed_tat": round(tat_score, 2),
                    "sentiment": round(sentiment_score, 2),
                    "crisis_sla": round(crisis_score, 2),
                },
                "total_index": round(total_index, 2),
            })

        report_data.sort(key=lambda x: x["total_index"], reverse=True)
        return {
            "status": "success",
            "datastore": datastore_name,
            "evaluated_rows": len(df),
            "leaderboard": report_data,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
