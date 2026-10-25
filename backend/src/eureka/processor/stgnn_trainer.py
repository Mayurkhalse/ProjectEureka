from __future__ import annotations

"""Asynchronous Training Loop, Evaluation, and Risk Diffusion Inference for StGNN.

Executes production-grade PyTorch training for EurekaA3TGCN using Adam with
ReduceLROnPlateau, MSE + L2 regularization, chronological train/validation/test splits,
and real-time 36-district risk diffusion forecasting for the DGIPR 5-Zone Dashboard.
"""

import logging
import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

try:
    import torch
    import torch.nn as nn
    from torch.optim.lr_scheduler import ReduceLROnPlateau
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    class _DummyTorch:
        device = Any
        Tensor = Any
    torch = _DummyTorch()
    nn = None
    ReduceLROnPlateau = None

from eureka.core.celery_app import celery_app
from eureka.processor.stgnn_dataset import (
    INDEX_TO_CODE,
    INDEX_TO_DIVISION,
    INDEX_TO_NAME,
    MAHARASHTRA_DISTRICTS,
    NUM_MAHARASHTRA_DISTRICTS,
    EurekaTemporalDatasetBuilder,
    StaticGraphTemporalSignal,
    resolve_district_index,
)
from eureka.processor.stgnn_model import EurekaA3TGCN

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "models", "stgnn_a3tgcn_latest.pt"
)


class StGNNTrainer:
    """Manages training, chronological evaluation, and risk diffusion inference."""

    def __init__(
        self,
        model: Optional[EurekaA3TGCN] = None,
        learning_rate: float = 0.005,
        weight_decay: float = 1e-4,
        device: Optional[torch.device] = None,
    ):
        self.device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = model or EurekaA3TGCN(in_channels=3, hidden_dim_1=32, hidden_dim_2=16, periods=12, out_features=2)
        self.model.to(self.device)

        self.learning_rate = learning_rate
        self.weight_decay = weight_decay
        self.criterion = nn.MSELoss()

    def train_epoch(
        self,
        dataset_split: List[Any],
        optimizer: torch.optim.Optimizer,
    ) -> float:
        """Run single forward-backward optimization epoch over temporal snapshots."""
        self.model.train()
        total_loss = 0.0
        count = 0

        for snapshot in dataset_split:
            x = snapshot.x.to(self.device)
            edge_index = snapshot.edge_index.to(self.device)
            edge_weight = snapshot.edge_attr.to(self.device) if snapshot.edge_attr is not None else None
            y = snapshot.y.to(self.device)

            optimizer.zero_grad()
            y_pred, _ = self.model(x, edge_index, edge_weight)

            # Ensure matching shapes
            if y_pred.shape != y.shape:
                if y.dim() == 1 and y_pred.shape[1] == 1:
                    y = y.unsqueeze(1)
                elif y.shape[1] != y_pred.shape[1]:
                    # Align to target channels
                    y_pred = y_pred[:, :y.shape[1]]

            loss = self.criterion(y_pred, y)
            loss.backward()

            # Gradient clipping to prevent exploding gradients in recurrent GCN
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=5.0)

            optimizer.step()
            total_loss += loss.item()
            count += 1

        return total_loss / max(1, count)

    def evaluate(
        self,
        dataset_split: List[Any],
    ) -> Dict[str, float]:
        """Evaluate model on chronologically held-out snapshots returning RMSE and MAE."""
        self.model.eval()
        squared_errors = []
        absolute_errors = []

        with torch.no_grad():
            for snapshot in dataset_split:
                x = snapshot.x.to(self.device)
                edge_index = snapshot.edge_index.to(self.device)
                edge_weight = snapshot.edge_attr.to(self.device) if snapshot.edge_attr is not None else None
                y = snapshot.y.to(self.device)

                y_pred, _ = self.model(x, edge_index, edge_weight)

                if y.dim() == 1 and y_pred.shape[1] == 1:
                    y = y.unsqueeze(1)
                elif y.shape[1] != y_pred.shape[1]:
                    y_pred = y_pred[:, :y.shape[1]]

                diff = (y_pred - y).cpu().numpy()
                squared_errors.extend((diff ** 2).flatten().tolist())
                absolute_errors.extend(np.abs(diff).flatten().tolist())

        mse = float(np.mean(squared_errors)) if squared_errors else 0.0
        rmse = float(math.sqrt(mse))
        mae = float(np.mean(absolute_errors)) if absolute_errors else 0.0

        return {
            "mse": round(mse, 4),
            "rmse": round(rmse, 4),
            "mae": round(mae, 4),
        }

    def train_pipeline(
        self,
        dataset: StaticGraphTemporalSignal,
        epochs: int = 25,
        test_ratio: float = 0.2,
        val_ratio: float = 0.1,
        save_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute full training pipeline with chronological split and LR scheduling."""
        snapshots = list(dataset)
        total_snaps = len(snapshots)

        if total_snaps < 3:
            raise ValueError(f"Dataset has only {total_snaps} snapshots; at least 3 required for chronological split.")

        test_count = max(1, int(total_snaps * test_ratio))
        val_count = max(1, int(total_snaps * val_ratio))
        train_count = total_snaps - test_count - val_count

        if train_count <= 0:
            train_count = 1
            val_count = max(1, (total_snaps - 1) // 2)
            test_count = total_snaps - train_count - val_count

        train_set = snapshots[:train_count]
        val_set = snapshots[train_count:train_count + val_count]
        test_set = snapshots[train_count + val_count:]

        logger.info(
            "Chronological split: %d train, %d val, %d test snapshots (Total: %d)",
            len(train_set), len(val_set), len(test_set), total_snaps,
        )

        optimizer = torch.optim.Adam(
            self.model.parameters(),
            lr=self.learning_rate,
            weight_decay=self.weight_decay,
        )
        scheduler = ReduceLROnPlateau(optimizer, mode="min", factor=0.5, patience=3)

        history: List[Dict[str, float]] = []
        best_val_loss = float("inf")
        best_epoch = 0

        for epoch in range(1, epochs + 1):
            train_loss = self.train_epoch(train_set, optimizer)
            val_metrics = self.evaluate(val_set)
            val_loss = val_metrics["mse"]

            scheduler.step(val_loss)

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_epoch = epoch
                if save_path:
                    self.model.save_weights(save_path)

            history.append({
                "epoch": epoch,
                "train_loss": round(train_loss, 4),
                "val_mse": val_metrics["mse"],
                "val_rmse": val_metrics["rmse"],
                "val_mae": val_metrics["mae"],
            })

            if epoch % 5 == 0 or epoch == epochs:
                logger.info(
                    "Epoch %d/%d - Train Loss: %.4f | Val RMSE: %.4f | Val MAE: %.4f",
                    epoch, epochs, train_loss, val_metrics["rmse"], val_metrics["mae"],
                )

        # Final evaluation on chronologically held-out test set
        test_metrics = self.evaluate(test_set)
        logger.info("Test Set Evaluation - RMSE: %.4f | MAE: %.4f", test_metrics["rmse"], test_metrics["mae"])

        return {
            "best_epoch": best_epoch,
            "best_val_loss": round(best_val_loss, 4),
            "test_metrics": test_metrics,
            "history": history,
            "weights_saved_to": save_path,
        }


def infer_risk_diffusion(
    current_state: Union[StaticGraphTemporalSignal, Dict[str, Any]],
    model: Optional[EurekaA3TGCN] = None,
    weights_path: Optional[str] = None,
    device: Optional[torch.device] = None,
) -> Dict[str, Any]:
    """Execute forward inference to forecast rumor contagion risk for Maharashtra's 36 districts.

    Returns structured output tailored for the DGIPR 5-Zone Dashboard:
        - 36-dimensional district risk scores
        - Risk categorization (LOW, MEDIUM, HIGH, CRITICAL)
        - 5-Zone aggregate risk summary
        - Top critical epicenter alerts
    """
    # Extract x as numpy array or tensor
    is_temporal_signal = (
        (StaticGraphTemporalSignal is not None and isinstance(current_state, StaticGraphTemporalSignal))
        or hasattr(current_state, "snapshot_count")
        or (hasattr(current_state, "features") and hasattr(current_state, "edge_index"))
    )
    if is_temporal_signal:
        snapshot = list(current_state)[-1]
        x_raw = snapshot.x
        x_np = x_raw.cpu().numpy() if hasattr(x_raw, "cpu") else np.array(x_raw, dtype=np.float32)
        edge_index_raw = snapshot.edge_index
        edge_weight_raw = snapshot.edge_attr
    elif isinstance(current_state, dict):
        x_np = np.array(current_state["x"], dtype=np.float32)
        edge_index_raw = current_state.get("edge_index")
        edge_weight_raw = current_state.get("edge_weight")
    else:
        raise TypeError("current_state must be a StaticGraphTemporalSignal or dict with keys 'x' and 'edge_index'.")

    risk_vector = None
    preds = None
    attention = None
    provenance = "model"

    # When no explicit PyTorch model is passed, offload inference to Triton / local INT8 ONNX
    if model is None:
        try:
            from eureka.processor.triton_client import get_triton_client
            triton_client = get_triton_client()
            res = triton_client.infer_stgnn(node_features=x_np)
            preds_raw = res["predictions"]
            preds = preds_raw[0] if preds_raw.ndim == 3 else preds_raw
            attention = res["attention_weights"]

            norm_vol = np.clip(preds[:, 0] / 300.0, 0.0, 1.0)
            norm_rumors = np.clip(preds[:, 1] / 15.0, 0.0, 1.0)
            risk_vector = np.clip(0.4 * norm_vol + 0.6 * norm_rumors, 0.0, 1.0)
        except Exception as exc:
            logger.warning("Triton/INT8 inference failed (%s); attempting PyTorch fallback.", exc)
            if HAS_TORCH and torch is not None:
                model = EurekaA3TGCN(in_channels=3, hidden_dim_1=32, hidden_dim_2=16, periods=12, out_features=2)
                target_path = weights_path or DEFAULT_WEIGHTS_PATH
                if os.path.exists(target_path):
                    try:
                        model.load_weights(target_path)
                    except Exception as w_exc:
                        logger.warning("Could not load weights from %s: %s", target_path, w_exc)

    if model is not None and HAS_TORCH and torch is not None:
        try:
            dev = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
            model.to(dev)
            model.eval()

            x = torch.tensor(x_np, dtype=torch.float32, device=dev)
            edge_index = (
                edge_index_raw.to(dev)
                if hasattr(edge_index_raw, "to")
                else torch.tensor(edge_index_raw, dtype=torch.long, device=dev)
            )
            edge_weight = None
            if edge_weight_raw is not None:
                edge_weight = (
                    edge_weight_raw.to(dev)
                    if hasattr(edge_weight_raw, "to")
                    else torch.tensor(edge_weight_raw, dtype=torch.float32, device=dev)
                )

            with torch.no_grad():
                preds_torch, attention = model(x, edge_index, edge_weight)
                preds = preds_torch.cpu().numpy()
                risk_vector = model.compute_risk_scores(x, edge_index, edge_weight).cpu().numpy()
        except Exception as p_exc:
            logger.warning("PyTorch forward inference failed (%s); falling back to heuristic baseline.", p_exc)

    # Fallback to calibrated heuristic baseline when ML models / PyTorch are absent
    if risk_vector is None or preds is None:
        provenance = "heuristic"
        if x_np is not None and x_np.shape[0] == NUM_MAHARASHTRA_DISTRICTS:
            last_step = x_np[:, :, -1] if x_np.ndim == 3 else x_np
            norm_vol = np.clip(last_step[:, 0] / 300.0, 0.0, 1.0)
            norm_rumors = np.clip(last_step[:, 1] / 15.0 if last_step.shape[1] > 1 else 0.2, 0.0, 1.0)
            risk_vector = np.clip(0.4 * norm_vol + 0.6 * norm_rumors, 0.0, 1.0)
            preds = np.column_stack([norm_vol * 150.0, norm_rumors * 5.0])
        else:
            risk_vector = np.full(NUM_MAHARASHTRA_DISTRICTS, 0.42, dtype=np.float32)
            preds = np.zeros((NUM_MAHARASHTRA_DISTRICTS, 2), dtype=np.float32)
        if attention is None:
            attention = np.full(12, 1.0 / 12.0, dtype=np.float32)

    # Build 36-district response
    district_risks: List[Dict[str, Any]] = []
    zone_accumulators: Dict[str, List[float]] = {
        "Konkan": [],
        "Pune": [],
        "Nashik": [],
        "Chhatrapati Sambhajinagar": [],
        "Vidarbha": [],
    }

    for idx in range(NUM_MAHARASHTRA_DISTRICTS):
        code = INDEX_TO_CODE.get(idx, f"MH-{idx+1:02d}")
        name = INDEX_TO_NAME.get(idx, code)
        div = INDEX_TO_DIVISION.get(idx, "Konkan")
        score = float(risk_vector[idx])

        # Assign DGIPR risk tiers
        if score >= 0.75:
            tier = "CRITICAL"
        elif score >= 0.50:
            tier = "HIGH"
        elif score >= 0.25:
            tier = "MEDIUM"
        else:
            tier = "LOW"

        pred_vol = float(preds[idx, 0]) if preds.shape[1] > 0 else 0.0
        pred_rumors = float(preds[idx, 1]) if preds.shape[1] > 1 else 0.0

        item = {
            "district_id": idx + 1,
            "district_code": code,
            "district_name": name,
            "division": div,
            "risk_score": round(score, 4),
            "risk_level": tier,
            "forecasted_volume_6h": max(0.0, round(pred_vol, 1)),
            "forecasted_rumors_6h": max(0.0, round(pred_rumors, 1)),
        }
        district_risks.append(item)

        # Map division to 5 administrative zones
        zone_key = div
        if div in ("Amravati", "Nagpur"):
            zone_key = "Vidarbha"
        if zone_key in zone_accumulators:
            zone_accumulators[zone_key].append(score)

    # 5-Zone summary
    zone_summary = {
        z: round(float(np.mean(scores)), 4) if scores else 0.0
        for z, scores in zone_accumulators.items()
    }

    # Top critical districts
    top_critical = sorted(district_risks, key=lambda d: d["risk_score"], reverse=True)[:5]

    attn_weights = (
        attention.cpu().tolist()
        if hasattr(attention, "cpu")
        else (attention.tolist() if hasattr(attention, "tolist") else list(attention))
    )

    return {
        "forecast_timestamp": datetime.now(timezone.utc).isoformat(),
        "forecast_horizon_hours": 6,
        "total_districts_monitored": NUM_MAHARASHTRA_DISTRICTS,
        "provenance": provenance,
        "attention_weights": [round(float(w), 4) for w in attn_weights],
        "dgipr_5_zone_summary": zone_summary,
        "top_critical_districts": top_critical,
        "district_risk_matrix": district_risks,
    }


@celery_app.task(name="eureka.processor.stgnn_trainer.train_stgnn_task")
def train_stgnn_task(
    num_snapshots: int = 40,
    epochs: int = 20,
    weights_path: str = DEFAULT_WEIGHTS_PATH,
) -> Dict[str, Any]:
    """Celery background task for asynchronous StGNN model retraining."""
    logger.info("Initiating asynchronous StGNN retraining task...")
    builder = EurekaTemporalDatasetBuilder(periods=12, forecast_horizon_hours=6)
    dataset = builder.generate_synthetic_historical_signal(num_snapshots=num_snapshots, seed=42)

    trainer = StGNNTrainer(learning_rate=0.005, weight_decay=1e-4)
    results = trainer.train_pipeline(dataset=dataset, epochs=epochs, save_path=weights_path)
    logger.info("Completed StGNN retraining. Best Val Loss: %.4f", results["best_val_loss"])
    return results
