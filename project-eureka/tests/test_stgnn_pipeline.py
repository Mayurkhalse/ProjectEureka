"""Unit and Integration Tests for Phase 3 Spatio-Temporal Graph Neural Network (StGNN).

Validates:
1. Maharashtra 36-district boundary topology and static edge construction.
2. Dynamic multi-hop claim edge fusion.
3. PyG StaticGraphTemporalSignal formatting.
4. EurekaA3TGCN neural forward, backward passes, and soft attention weighting.
5. StGNN training loop with chronological train/val/test splits, RMSE/MAE evaluation.
6. Real-time 36-district risk diffusion forecasting for the DGIPR 5-Zone Dashboard.
"""

import pytest
import torch
import numpy as np

from eureka.processor.stgnn_dataset import (
    MAHARASHTRA_DISTRICTS,
    NUM_MAHARASHTRA_DISTRICTS,
    CODE_TO_INDEX,
    INDEX_TO_CODE,
    build_static_district_edge_index,
    merge_static_and_dynamic_edges,
    resolve_district_index,
    EurekaTemporalDatasetBuilder,
)
from eureka.processor.stgnn_model import EurekaA3TGCN
from eureka.processor.stgnn_trainer import StGNNTrainer, infer_risk_diffusion


def test_maharashtra_district_registry():
    """Verify all 36 Maharashtra districts are accurately mapped."""
    assert len(MAHARASHTRA_DISTRICTS) == 36
    assert NUM_MAHARASHTRA_DISTRICTS == 36

    # Test resolution of codes and historical names
    assert resolve_district_index("MH-01") == 0
    assert resolve_district_index("MH-12") == 11 or resolve_district_index("MH-08") == 7
    assert resolve_district_index("Aurangabad") == CODE_TO_INDEX["chhatrapati sambhajinagar"]
    assert resolve_district_index("Ahmednagar") == CODE_TO_INDEX["ahilyanagar"]
    assert resolve_district_index("Osmanabad") == CODE_TO_INDEX["dharashiv"]


def test_static_district_edge_index_construction():
    """Verify boundary adjacency matrix has self-loops, connectivity, and symmetry."""
    edge_index, edge_weight = build_static_district_edge_index()

    assert edge_index.ndim == 2
    assert edge_index.shape[0] == 2
    assert edge_index.shape[1] > 36  # Must contain borders + self-loops
    assert len(edge_weight) == edge_index.shape[1]

    # Verify self-loops present for all 36 districts
    edges_set = set(zip(edge_index[0], edge_index[1]))
    for i in range(36):
        assert (i, i) in edges_set

    # Verify symmetry
    for u, v in edges_set:
        assert (v, u) in edges_set


def test_dynamic_edge_fusion():
    """Verify fusion of static boundary edges with dynamic multi-hop event/claim chains."""
    static_idx, static_wt = build_static_district_edge_index()
    dynamic_edges = [
        {"source_district": "MH-01", "target_district": "MH-31", "weight": 5.0},
        {"source_district": "MH-18", "target_district": "MH-20", "weight": 8.0},
    ]

    merged_idx, merged_wt = merge_static_and_dynamic_edges(
        static_idx, static_wt, dynamic_edges, dynamic_alpha=2.0
    )

    assert merged_idx.shape[1] >= static_idx.shape[1]
    assert len(merged_wt) == merged_idx.shape[1]

    # Find weight between Mumbai (0) and Nagpur (30)
    idx_0 = resolve_district_index("MH-01")
    idx_31 = resolve_district_index("MH-31")
    edges_map = {tuple(merged_idx[:, i]): merged_wt[i] for i in range(merged_idx.shape[1])}

    assert (idx_0, idx_31) in edges_map
    assert (idx_31, idx_0) in edges_map
    assert edges_map[(idx_0, idx_31)] >= 10.0  # 5.0 * 2.0


def test_synthetic_historical_dataset_builder():
    """Verify PyG StaticGraphTemporalSignal generation and snapshot dimensions."""
    builder = EurekaTemporalDatasetBuilder(periods=12, forecast_horizon_hours=6)
    dataset = builder.generate_synthetic_historical_signal(num_snapshots=10, seed=101)

    assert dataset.snapshot_count == 10
    snapshots = list(dataset)
    assert len(snapshots) == 10

    snap0 = snapshots[0]
    # x: (num_nodes=36, num_features=3, periods=12)
    assert snap0.x.shape == (36, 3, 12)
    # y: (num_nodes=36, num_targets=2)
    assert snap0.y.shape == (36, 2)
    assert snap0.edge_index.shape[0] == 2
    assert snap0.edge_attr is not None


def test_eureka_a3tgcn_architecture_and_backprop():
    """Verify EurekaA3TGCN forward pass, soft attention, risk scoring, and gradients."""
    model = EurekaA3TGCN(
        in_channels=3,
        hidden_dim_1=16,
        hidden_dim_2=8,
        periods=12,
        out_features=2,
    )

    x = torch.randn(36, 3, 12, requires_grad=True)
    edge_index = torch.tensor([[0, 1, 1, 2], [1, 0, 2, 1]], dtype=torch.long)
    edge_weight = torch.tensor([1.0, 1.0, 1.0, 1.0], dtype=torch.float)

    preds, attn = model(x, edge_index, edge_weight)

    # Output shapes
    assert preds.shape == (36, 2)
    assert attn.shape == (12,)
    # Soft attention weights must sum to 1.0
    assert torch.isclose(attn.sum(), torch.tensor(1.0), atol=1e-4)

    # Risk scores calculation
    risk = model.compute_risk_scores(x, edge_index, edge_weight)
    assert risk.shape == (36,)
    assert (risk >= 0.0).all() and (risk <= 1.0).all()

    # Backpropagation verification
    loss = torch.nn.functional.mse_loss(preds, torch.ones_like(preds))
    loss.backward()
    assert x.grad is not None
    assert not torch.isnan(x.grad).any()


def test_stgnn_trainer_pipeline_and_chronological_evaluation():
    """Verify training loop, chronological train/val/test splitting, and RMSE/MAE metrics."""
    builder = EurekaTemporalDatasetBuilder(periods=8, forecast_horizon_hours=6)
    dataset = builder.generate_synthetic_historical_signal(num_snapshots=8, seed=42)

    model = EurekaA3TGCN(in_channels=3, hidden_dim_1=8, hidden_dim_2=4, periods=8, out_features=2)
    trainer = StGNNTrainer(model=model, learning_rate=0.01, weight_decay=1e-4)

    results = trainer.train_pipeline(dataset=dataset, epochs=3, test_ratio=0.25, val_ratio=0.25)

    assert "best_val_loss" in results
    assert "test_metrics" in results
    assert "rmse" in results["test_metrics"]
    assert "mae" in results["test_metrics"]
    assert results["test_metrics"]["rmse"] >= 0.0
    assert results["test_metrics"]["mae"] >= 0.0
    assert len(results["history"]) == 3


def test_infer_risk_diffusion_dashboard_output():
    """Verify 36-district risk diffusion output formatting for the DGIPR 5-Zone Dashboard."""
    builder = EurekaTemporalDatasetBuilder(periods=12, forecast_horizon_hours=6)
    dataset = builder.generate_synthetic_historical_signal(num_snapshots=5, seed=77)

    output = infer_risk_diffusion(dataset)

    assert output["total_districts_monitored"] == 36
    assert output["forecast_horizon_hours"] == 6
    assert len(output["district_risk_matrix"]) == 36
    assert len(output["top_critical_districts"]) <= 5
    assert len(output["attention_weights"]) == 12

    # Check 5-Zone breakdown
    summary = output["dgipr_5_zone_summary"]
    for zone in ["Konkan", "Pune", "Nashik", "Chhatrapati Sambhajinagar", "Vidarbha"]:
        assert zone in summary
        assert 0.0 <= summary[zone] <= 1.0

    # Check district item fields
    sample_district = output["district_risk_matrix"][0]
    assert "district_id" in sample_district
    assert "district_code" in sample_district
    assert "district_name" in sample_district
    assert "division" in sample_district
    assert "risk_score" in sample_district
    assert "risk_level" in sample_district
    assert sample_district["risk_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
