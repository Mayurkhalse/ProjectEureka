"""Spatio-Temporal Graph Neural Network (A3TGCN) for Predictive Rumor Diffusion.

Implements the Attention Temporal Graph Convolutional Network (A3TGCN) architecture
for multi-horizon rumor diffusion and sentiment velocity forecasting across
Maharashtra's 36 administrative districts.
"""

import logging
import os
import sys
import types
from typing import Dict, Optional, Tuple

# PyG 2.x and PyTorch 2.x compatibility shims for torch-sparse and torch-scatter
if "torch_sparse" not in sys.modules:
    _ts = types.ModuleType("torch_sparse")
    class _DummySparseTensor:
        pass
    _ts.SparseTensor = _DummySparseTensor
    sys.modules["torch_sparse"] = _ts

if "torch_scatter" not in sys.modules:
    sys.modules["torch_scatter"] = types.ModuleType("torch_scatter")

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch_geometric.nn import GCNConv
    from torch_geometric_temporal.nn.recurrent import TGCN
    HAS_TORCH = True
    _BaseModule = nn.Module
except ImportError:
    HAS_TORCH = False
    torch = None
    nn = None
    F = None
    GCNConv = None
    TGCN = None
    _BaseModule = object

logger = logging.getLogger(__name__)


class EurekaA3TGCN(_BaseModule):
    """Attention Temporal Graph Convolutional Network (A3TGCN) for Project EUREKA.

    Combines spatial graph convolutions (aggregating non-Euclidean district boundary neighborhoods)
    with gated recurrent units and a learned soft attention mechanism over historical time steps.

    Architecture Flow:
        Input (N, F_in, T)
           │
        A3TGCN Layer 1 (Spatial GCN + Temporal GRU across T periods)
           │
         ReLU
           │
        A3TGCN Layer 2 (Spatial GCN + Temporal GRU + Soft Attention Context)
           │
         ReLU
           │
        Linear Output Head -> Predictive Risk Score / Target Vectors
    """

    def __init__(
        self,
        in_channels: int = 3,
        hidden_dim_1: int = 32,
        hidden_dim_2: int = 16,
        periods: int = 12,
        out_features: int = 2,
    ):
        super().__init__()
        self.in_channels = in_channels
        self.hidden_dim_1 = hidden_dim_1
        self.hidden_dim_2 = hidden_dim_2
        self.periods = periods
        self.out_features = out_features

        # Layer 1: Spatial GCN + Temporal GRU across T periods
        self.tgcn_layer1 = TGCN(
            in_channels=in_channels,
            out_channels=hidden_dim_1,
            improved=False,
            cached=False,
            add_self_loops=True,
        )

        # Layer 2: Spatial GCN + Temporal GRU
        self.tgcn_layer2 = TGCN(
            in_channels=hidden_dim_1,
            out_channels=hidden_dim_2,
            improved=False,
            cached=False,
            add_self_loops=True,
        )

        # Soft Attention parameter vector over historical periods
        self.attention_weights = nn.Parameter(torch.empty(periods))
        nn.init.uniform_(self.attention_weights, a=0.01, b=1.0)

        # Output projection head: Linear (hidden_dim_2 -> out_features)
        self.output_head = nn.Linear(hidden_dim_2, out_features)

    def forward(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        edge_weight: Optional[torch.Tensor] = None,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Forward pass through the two-stage A3TGCN architecture.

        Args:
            x: Node feature tensor of shape (num_nodes, in_channels, periods).
            edge_index: Graph edge index tensor of shape (2, num_edges).
            edge_weight: Optional edge weight tensor of shape (num_edges,).

        Returns:
            Tuple of:
                - output: Tensor of shape (num_nodes, out_features)
                - soft_attention: Normalized attention weights of shape (periods,)
        """
        num_nodes = x.shape[0]

        # 1. First A3TGCN Stage: Spatial GCN + Temporal GRU propagation
        h1 = None
        layer1_hidden_sequence = []
        for t in range(self.periods):
            # x[:, :, t] has shape (num_nodes, in_channels)
            h1 = self.tgcn_layer1(x[:, :, t], edge_index, edge_weight, h1)
            h1 = F.relu(h1)
            layer1_hidden_sequence.append(h1)

        # Stack into temporal tensor (num_nodes, hidden_dim_1, periods)
        h1_temporal = torch.stack(layer1_hidden_sequence, dim=-1)

        # 2. Second A3TGCN Stage with Soft Attention Context Aggregation
        h2 = None
        normalized_attention = F.softmax(self.attention_weights, dim=0)
        context_state = torch.zeros(num_nodes, self.hidden_dim_2, device=x.device)

        for t in range(self.periods):
            # h1_temporal[:, :, t] has shape (num_nodes, hidden_dim_1)
            h2 = self.tgcn_layer2(h1_temporal[:, :, t], edge_index, edge_weight, h2)
            # Soft attention accumulation
            context_state = context_state + normalized_attention[t] * h2

        # 3. Non-linear activation & Output Projection
        activated_context = F.relu(context_state)
        predictions = self.output_head(activated_context)

        return predictions, normalized_attention

    def compute_risk_scores(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        edge_weight: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """Compute normalized [0.0, 1.0] rumor contagion risk scores for each district."""
        self.eval()
        with torch.no_grad():
            preds, _ = self.forward(x, edge_index, edge_weight)
            # If multi-target: preds[:, 0] is volume, preds[:, 1] is active rumors
            if self.out_features >= 2:
                norm_vol = torch.clamp(preds[:, 0] / 300.0, 0.0, 1.0)
                norm_rumors = torch.clamp(preds[:, 1] / 15.0, 0.0, 1.0)
                risk = 0.4 * norm_vol + 0.6 * norm_rumors
            else:
                risk = torch.sigmoid(preds[:, 0])
            return torch.clamp(risk, 0.0, 1.0)

    def save_weights(self, path: str) -> None:
        """Save model state dictionary to disk."""
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        torch.save(self.state_dict(), path)
        logger.info("Saved EurekaA3TGCN model weights to %s", path)

    def load_weights(self, path: str) -> None:
        """Load model state dictionary from disk."""
        device = next(self.parameters()).device
        state_dict = torch.load(path, map_location=device)
        self.load_state_dict(state_dict)
        self.eval()
        logger.info("Loaded EurekaA3TGCN model weights from %s", path)
