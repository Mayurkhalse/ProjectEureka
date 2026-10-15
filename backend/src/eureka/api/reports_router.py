"""FastAPI router for generating live performance reports and composite index calculations."""

import os
from typing import Any, Dict
from fastapi import APIRouter, HTTPException
import pandas as pd

router = APIRouter(prefix="/api/v1/reports", tags=["System Reports"])


def _resolve_dataset_path() -> str:
    """Resolve location of english_extreme_scale.csv irrespective of working directory."""
    candidates = [
        "backend/seed_data/english_extreme_scale.csv",
        "seed_data/english_extreme_scale.csv",
        os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "../../../seed_data/english_extreme_scale.csv",
            )
        ),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return "backend/seed_data/english_extreme_scale.csv"


@router.get("/district-performance", summary="Generate 100-Point District Leaderboard Report")
def get_district_performance_report() -> Dict[str, Any]:
    file_path = _resolve_dataset_path()

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Synthetic database not found.")

    try:
        # Read a 50,000 row chunk for the live API report
        df = pd.read_csv(file_path, nrows=50000)
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

            # 100-Point Math Logic
            volume_score = min(25.0, (total_releases / 300) * 25)
            tat_score = (
                25.0
                if avg_tat <= 45
                else (0.0 if avg_tat >= 120 else 25.0 * (1 - ((avg_tat - 45) / 75)))
            )
            sentiment_score = ((net_sentiment + 1.0) / 2) * 25
            crisis_score = resolved_ratio * 25

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
                "total_index": round(
                    volume_score + tat_score + sentiment_score + crisis_score, 2
                ),
            })

        report_data.sort(key=lambda x: x["total_index"], reverse=True)

        return {
            "status": "success",
            "evaluated_rows": 50000,
            "leaderboard": report_data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
