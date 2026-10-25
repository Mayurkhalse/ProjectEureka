"""Model Export and INT8 Post-Training Quantization (PTQ) Pipeline for Project EUREKA.

Freezes initialized PyTorch models (EurekaA3TGCN / FastA3TGCN, FANGJointObjective, MuRILEncoder),
exports them to ONNX with dynamic batching axes, and applies Dynamic INT8 Post-Training
Quantization (PTQ) via onnxruntime.quantization for deployment to Triton Inference Server.
"""

import io
import logging
import os
import sys
import types
from pathlib import Path
from typing import Dict, Optional, Tuple

# Ensure eureka src is on sys.path
_src_root = Path(__file__).resolve().parent.parent.parent
if str(_src_root) not in sys.path:
    sys.path.insert(0, str(_src_root))

# Ensure UTF-8 output encoding on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# PyG 2.x and PyTorch 2.x compatibility shims for torch-sparse and torch-scatter
if "torch_sparse" not in sys.modules:
    _ts = types.ModuleType("torch_sparse")
    class _DummySparseTensor:
        pass
    _ts.SparseTensor = _DummySparseTensor
    sys.modules["torch_sparse"] = _ts

if "torch_scatter" not in sys.modules:
    sys.modules["torch_scatter"] = types.ModuleType("torch_scatter")

import numpy as np

try:
    import onnx
    import onnxruntime as ort
    from onnxruntime.quantization import QuantType, quantize_dynamic
    HAS_ONNX = True
except ImportError:
    onnx = None
    ort = None
    QuantType = None
    quantize_dynamic = None
    HAS_ONNX = False

import torch
import torch.nn as nn
import torch.nn.functional as F

from eureka.processor.stgnn_dataset import build_static_district_edge_index

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent / "model_repository"


# ============================================================================
# Optimized Neural Architectures for ONNX / Triton Inference
# ============================================================================

class StGNNCell(nn.Module):
    """Spatio-temporal graph recurrent cell using normalized adjacency matrix multiplication."""

    def __init__(self, in_channels: int, out_channels: int):
        super().__init__()
        self.in_channels = in_channels
        self.out_channels = out_channels

        self.w_z = nn.Linear(in_channels, out_channels, bias=False)
        self.u_z = nn.Linear(out_channels, out_channels, bias=True)

        self.w_r = nn.Linear(in_channels, out_channels, bias=False)
        self.u_r = nn.Linear(out_channels, out_channels, bias=True)

        self.w_h = nn.Linear(in_channels, out_channels, bias=False)
        self.u_h = nn.Linear(out_channels, out_channels, bias=True)

    def forward(
        self,
        x: torch.Tensor,
        adj_norm: torch.Tensor,
        h: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        # x: (B, 36, in_channels), adj_norm: (36, 36)
        ax = torch.matmul(adj_norm, x)

        if h is None:
            h = torch.zeros(x.shape[0], x.shape[1], self.out_channels, device=x.device)

        z = torch.sigmoid(self.w_z(ax) + self.u_z(h))
        r = torch.sigmoid(self.w_r(ax) + self.u_r(h))
        h_tilde = torch.tanh(self.w_h(ax) + self.u_h(r * h))
        h_next = (1 - z) * h + z * h_tilde
        return h_next


class FastA3TGCN(nn.Module):
    """High-performance A3TGCN with dynamic batching and soft attention over temporal periods."""

    def __init__(
        self,
        in_channels: int = 3,
        hidden_dim_1: int = 32,
        hidden_dim_2: int = 16,
        periods: int = 12,
        out_features: int = 2,
    ):
        super().__init__()
        self.periods = periods
        self.hidden_dim_1 = hidden_dim_1
        self.hidden_dim_2 = hidden_dim_2

        self.cell1 = StGNNCell(in_channels, hidden_dim_1)
        self.cell2 = StGNNCell(hidden_dim_1, hidden_dim_2)

        self.attention = nn.Parameter(torch.empty(periods))
        nn.init.uniform_(self.attention, 0.01, 1.0)
        self.output_head = nn.Linear(hidden_dim_2, out_features)

    def forward(
        self,
        node_features: torch.Tensor,
        adj_norm: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        # node_features: (batch_size, 36, in_channels, periods)
        # adj_norm: (36, 36)
        b_size, num_nodes = node_features.shape[0], node_features.shape[1]

        # Stage 1: Spatial-Temporal recurrence
        h1 = None
        seq_h1 = []
        for t in range(self.periods):
            h1 = self.cell1(node_features[:, :, :, t], adj_norm, h1)
            h1 = F.relu(h1)
            seq_h1.append(h1)

        # Stage 2: Second recurrent layer with Soft Attention Context Aggregation
        h2 = None
        weights = F.softmax(self.attention, dim=0)
        context = torch.zeros(b_size, num_nodes, self.hidden_dim_2, device=node_features.device)

        for t in range(self.periods):
            h2 = self.cell2(seq_h1[t], adj_norm, h2)
            context = context + weights[t] * h2

        predictions = self.output_head(F.relu(context))
        return predictions, weights


class FANGJointObjective(nn.Module):
    """FANG Joint Objective: Text representation, source credibility, and context graph head."""

    def __init__(
        self,
        embedding_dim: int = 768,
        source_dim: int = 16,
        context_dim: int = 32,
        hidden_dim: int = 64,
    ):
        super().__init__()
        in_dim = embedding_dim + source_dim + context_dim
        self.fc1 = nn.Linear(in_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, 32)
        self.rumor_head = nn.Linear(32, 2)
        self.cred_head = nn.Linear(32, 1)

    def forward(
        self,
        claim_emb: torch.Tensor,
        source_feat: torch.Tensor,
        context_feat: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        x = torch.cat([claim_emb, source_feat, context_feat], dim=-1)
        h = F.relu(self.fc1(x))
        h = F.relu(self.fc2(h))
        rumor_logits = self.rumor_head(h)
        cred_score = torch.sigmoid(self.cred_head(h))
        return rumor_logits, cred_score


class MuRILEncoder(nn.Module):
    """MuRIL Indic text encoder and sequence classification head for ONNX export."""

    def __init__(
        self,
        vocab_size: int = 30522,
        hidden_dim: int = 768,
        num_labels: int = 4,
    ):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, hidden_dim)
        self.fc_pool = nn.Linear(hidden_dim, hidden_dim)
        self.classifier = nn.Linear(hidden_dim, num_labels)

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        emb = self.embedding(input_ids)
        if attention_mask is not None:
            mask = attention_mask.unsqueeze(-1).to(dtype=emb.dtype)
            pooled = (emb * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
        else:
            pooled = emb.mean(dim=1)

        pooled_repr = torch.tanh(self.fc_pool(pooled))
        logits = self.classifier(pooled_repr)
        return logits, pooled_repr


# ============================================================================
# Helper: Build Normalized Degree-Laplacian Adjacency Matrix
# ============================================================================

def get_normalized_district_adjacency() -> np.ndarray:
    """Compute symmetric normalized degree adjacency D^-1/2 * A * D^-1/2 for 36 districts."""
    edge_index, edge_weight = build_static_district_edge_index()
    num_nodes = 36
    adj = np.zeros((num_nodes, num_nodes), dtype=np.float32)

    for i in range(edge_index.shape[1]):
        u = edge_index[0, i]
        v = edge_index[1, i]
        adj[u, v] = edge_weight[i]

    # Degree normalization: D^-1/2 * A * D^-1/2
    deg = np.sum(adj, axis=1)
    deg_inv_sqrt = np.zeros_like(deg)
    pos_mask = deg > 0
    deg_inv_sqrt[pos_mask] = 1.0 / np.sqrt(deg[pos_mask])
    d_mat = np.diag(deg_inv_sqrt)
    adj_norm = d_mat @ adj @ d_mat
    return adj_norm.astype(np.float32)


# ============================================================================
# Export & Quantization Functions
# ============================================================================

def export_and_quantize_stgnn(model_repo_dir: Path = REPO_ROOT) -> Path:
    """Freeze, export to ONNX, and apply INT8 PTQ to StGNN Forecaster."""
    print("\n--- [1/3] Exporting StGNN Forecaster (stgnn_forecaster) ---")
    stgnn_dir = model_repo_dir / "stgnn_forecaster" / "1"
    stgnn_dir.mkdir(parents=True, exist_ok=True)

    fp32_onnx = stgnn_dir / "model_fp32.onnx"
    int8_onnx = stgnn_dir / "model.onnx"

    model = FastA3TGCN(in_channels=3, hidden_dim_1=32, hidden_dim_2=16, periods=12, out_features=2)
    model.eval()

    dummy_x = torch.randn(2, 36, 3, 12)
    adj_norm = torch.tensor(get_normalized_district_adjacency(), dtype=torch.float32)

    torch.onnx.export(
        model,
        (dummy_x, adj_norm),
        str(fp32_onnx),
        input_names=["node_features", "adj_norm"],
        output_names=["predictions", "attention_weights"],
        dynamic_axes={
            "node_features": {0: "batch_size"},
            "predictions": {0: "batch_size"},
        },
        opset_version=17,
        dynamo=False,
    )
    print(f"  [OK] Exported FP32 ONNX -> {fp32_onnx}")

    # Dynamic INT8 Post-Training Quantization
    quantize_dynamic(
        model_input=str(fp32_onnx),
        model_output=str(int8_onnx),
        weight_type=QuantType.QUInt8,
    )
    print(f"  [OK] Applied Dynamic INT8 PTQ -> {int8_onnx}")

    # Verify session with onnxruntime
    session = ort.InferenceSession(str(int8_onnx))
    res = session.run(
        None,
        {
            "node_features": dummy_x.numpy(),
            "adj_norm": adj_norm.numpy(),
        },
    )
    print(f"  [OK] Verified INT8 Inference Session (Predictions: {res[0].shape}, Attention: {res[1].shape})")

    if fp32_onnx.exists():
        fp32_onnx.unlink()

    return int8_onnx


def export_and_quantize_fang(model_repo_dir: Path = REPO_ROOT) -> Path:
    """Freeze, export to ONNX, and apply INT8 PTQ to FANGJointObjective."""
    print("\n--- [2/3] Exporting FANG Joint Objective (fang_joint) ---")
    fang_dir = model_repo_dir / "fang_joint" / "1"
    fang_dir.mkdir(parents=True, exist_ok=True)

    fp32_onnx = fang_dir / "model_fp32.onnx"
    int8_onnx = fang_dir / "model.onnx"

    model = FANGJointObjective(embedding_dim=768, source_dim=16, context_dim=32, hidden_dim=64)
    model.eval()

    dummy_claim = torch.randn(2, 768)
    dummy_source = torch.randn(2, 16)
    dummy_context = torch.randn(2, 32)

    torch.onnx.export(
        model,
        (dummy_claim, dummy_source, dummy_context),
        str(fp32_onnx),
        input_names=["claim_emb", "source_feat", "context_feat"],
        output_names=["rumor_logits", "cred_score"],
        dynamic_axes={
            "claim_emb": {0: "batch_size"},
            "source_feat": {0: "batch_size"},
            "context_feat": {0: "batch_size"},
            "rumor_logits": {0: "batch_size"},
            "cred_score": {0: "batch_size"},
        },
        opset_version=17,
        dynamo=False,
    )
    print(f"  [OK] Exported FP32 ONNX -> {fp32_onnx}")

    quantize_dynamic(
        model_input=str(fp32_onnx),
        model_output=str(int8_onnx),
        weight_type=QuantType.QUInt8,
    )
    print(f"  [OK] Applied Dynamic INT8 PTQ -> {int8_onnx}")

    session = ort.InferenceSession(str(int8_onnx))
    res = session.run(
        None,
        {
            "claim_emb": dummy_claim.numpy(),
            "source_feat": dummy_source.numpy(),
            "context_feat": dummy_context.numpy(),
        },
    )
    print(f"  [OK] Verified INT8 Inference Session (Rumor Logits: {res[0].shape}, Cred Score: {res[1].shape})")

    if fp32_onnx.exists():
        fp32_onnx.unlink()

    return int8_onnx


def export_and_quantize_muril(model_repo_dir: Path = REPO_ROOT) -> Path:
    """Freeze, export to ONNX, and apply INT8 PTQ to MuRILEncoder."""
    print("\n--- [3/3] Exporting MuRIL Indic Encoder (muril_encoder) ---")
    muril_dir = model_repo_dir / "muril_encoder" / "1"
    muril_dir.mkdir(parents=True, exist_ok=True)

    fp32_onnx = muril_dir / "model_fp32.onnx"
    int8_onnx = muril_dir / "model.onnx"

    model = MuRILEncoder(vocab_size=30522, hidden_dim=768, num_labels=4)
    model.eval()

    dummy_ids = torch.randint(0, 30522, (2, 64), dtype=torch.long)
    dummy_mask = torch.ones((2, 64), dtype=torch.long)

    torch.onnx.export(
        model,
        (dummy_ids, dummy_mask),
        str(fp32_onnx),
        input_names=["input_ids", "attention_mask"],
        output_names=["logits", "pooled_embedding"],
        dynamic_axes={
            "input_ids": {0: "batch_size", 1: "seq_len"},
            "attention_mask": {0: "batch_size", 1: "seq_len"},
            "logits": {0: "batch_size"},
            "pooled_embedding": {0: "batch_size"},
        },
        opset_version=17,
        dynamo=False,
    )
    print(f"  [OK] Exported FP32 ONNX -> {fp32_onnx}")

    quantize_dynamic(
        model_input=str(fp32_onnx),
        model_output=str(int8_onnx),
        weight_type=QuantType.QUInt8,
    )
    print(f"  [OK] Applied Dynamic INT8 PTQ -> {int8_onnx}")

    session = ort.InferenceSession(str(int8_onnx))
    res = session.run(
        None,
        {
            "input_ids": dummy_ids.numpy(),
            "attention_mask": dummy_mask.numpy(),
        },
    )
    print(f"  [OK] Verified INT8 Inference Session (Logits: {res[0].shape}, Pooled: {res[1].shape})")

    if fp32_onnx.exists():
        fp32_onnx.unlink()

    return int8_onnx


def export_all_models(model_repo_dir: Path = REPO_ROOT) -> Dict[str, Path]:
    """Execute complete export and INT8 quantization for all 3 models."""
    print("=" * 72)
    print(" PROJECT EUREKA: ONNX EXPORT & INT8 QUANTIZATION (TRITON PIPELINE)")
    print(f" Target Model Repository: {model_repo_dir}")
    print("=" * 72)

    stgnn_path = export_and_quantize_stgnn(model_repo_dir)
    fang_path = export_and_quantize_fang(model_repo_dir)
    muril_path = export_and_quantize_muril(model_repo_dir)

    print("\n" + "=" * 72)
    print(" ALL 3 MODELS SUCCESSFULLY EXPORTED & QUANTIZED TO INT8:")
    print(f"  1. stgnn_forecaster -> {stgnn_path.stat().st_size / 1024:.1f} KB")
    print(f"  2. fang_joint       -> {fang_path.stat().st_size / 1024:.1f} KB")
    print(f"  3. muril_encoder    -> {muril_path.stat().st_size / 1024:.1f} KB")
    print("=" * 72 + "\n")

    return {
        "stgnn_forecaster": stgnn_path,
        "fang_joint": fang_path,
        "muril_encoder": muril_path,
    }


if __name__ == "__main__":
    export_all_models()
