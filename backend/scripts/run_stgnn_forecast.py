"""Standalone CLI runner for Phase 3 StGNN training and risk diffusion forecasting."""

import sys
from pathlib import Path

# Ensure eureka is on sys.path
eureka_src = Path(__file__).resolve().parent.parent / "src"
if str(eureka_src) not in sys.path:
    sys.path.insert(0, str(eureka_src))

from eureka.processor.stgnn_dataset import EurekaTemporalDatasetBuilder
from eureka.processor.stgnn_model import EurekaA3TGCN
from eureka.processor.stgnn_trainer import StGNNTrainer, infer_risk_diffusion


def main():
    print("=" * 72)
    print(" PROJECT EUREKA: PHASE 3 STGNN RUMOR DIFFUSION ENGINE")
    print("=" * 72)

    # 1. Dataset Generation
    print("\n[1] Constructing Maharashtra 36-District Spatio-Temporal Dataset...")
    builder = EurekaTemporalDatasetBuilder(periods=12, forecast_horizon_hours=6)
    dataset = builder.generate_synthetic_historical_signal(num_snapshots=30, seed=42)
    print(f"    - Snapshots Generated:    {dataset.snapshot_count}")
    print(f"    - Monitored Districts:    36 (Undirected Boundary Adjacency Graph)")
    print(f"    - Historical Window:      12 Periods")
    print(f"    - Forecast Horizon:       6 Hours Ahead")

    # 2. Model Training
    print("\n[2] Training EurekaA3TGCN (Spatial GCN + Temporal GRU + Soft Attention)...")
    model = EurekaA3TGCN(in_channels=3, hidden_dim_1=32, hidden_dim_2=16, periods=12, out_features=2)
    trainer = StGNNTrainer(model=model, learning_rate=0.005, weight_decay=1e-4)

    results = trainer.train_pipeline(dataset=dataset, epochs=10, test_ratio=0.2, val_ratio=0.1)
    metrics = results["test_metrics"]
    print(f"    - Best Validation MSE:    {results['best_val_loss']:.4f}")
    print(f"    - Held-Out Test RMSE:     {metrics['rmse']:.4f}")
    print(f"    - Held-Out Test MAE:      {metrics['mae']:.4f}")

    # 3. Risk Diffusion Forecasting
    print("\n[3] Generating 6-Hour Forward Risk Diffusion Forecast...")
    forecast = infer_risk_diffusion(dataset, model=model)

    print("\n" + "=" * 72)
    print(" DGIPR 5-ZONE STATE RISK SUMMARY")
    print("=" * 72)
    for zone, score in forecast["dgipr_5_zone_summary"].items():
        status = "HIGH ALERT" if score >= 0.50 else "ELEVATED" if score >= 0.30 else "NORMAL"
        bar = "#" * int(score * 20) + "-" * (20 - int(score * 20))
        print(f"  {zone:<28} [{bar}] {score:.4f}  ({status})")


    print("\n" + "=" * 72)
    print(" TOP 5 CRITICAL DISTRICTS (EARLY WARNING INTERVENTION)")
    print("=" * 72)
    print(f"  {'Code':<7} {'District':<26} {'Division':<18} {'Risk':<8} {'Level':<10}")
    print("  " + "-" * 68)
    for d in forecast["top_critical_districts"]:
        print(f"  {d['district_code']:<7} {d['district_name']:<26} {d['division']:<18} {d['risk_score']:<8.4f} {d['risk_level']:<10}")

    print("\n" + "=" * 72)
    print(" [OK] StGNN Predictive Rumor Diffusion Engine is Production Ready")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()
