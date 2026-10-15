"""High-Speed gRPC Inference Client for Triton Inference Server in Project EUREKA.

Replaces in-process PyTorch model forward passes inside Celery workers with lightweight,
zero-copy gRPC tensor offload to Triton Inference Server using Post-Training Quantized (INT8)
ONNX engines with server-side dynamic batching (2ms aggregation window).

Features:
- Triton gRPC transport with connection pooling and health checks.
- Zero native PyTorch memory footprint inside Celery workers.
- Dynamic fallback to local INT8 ONNX Runtime when Triton server is unreachable (CI / local testing).
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import onnxruntime as ort
import tritonclient.grpc as grpcclient
from tritonclient.utils import InferenceServerException

from eureka.core.config import get_settings
from eureka.processor.export_models import get_normalized_district_adjacency

logger = logging.getLogger(__name__)

MODEL_REPO_PATH = Path(__file__).resolve().parent.parent / "model_repository"


class TritonInferenceClient:
    """Production gRPC client communicating with Triton Inference Server."""

    def __init__(
        self,
        server_url: Optional[str] = None,
        model_repo_dir: Optional[Path] = None,
        timeout: float = 5.0,
    ):
        settings = get_settings()
        self.server_url = server_url or settings.TRITON_SERVER_URL
        self.model_repo_dir = model_repo_dir or MODEL_REPO_PATH
        self.timeout = timeout
        self._grpc_client: Optional[grpcclient.InferenceServerClient] = None
        self._ort_sessions: Dict[str, ort.InferenceSession] = {}
        self._cached_adj_norm = get_normalized_district_adjacency()

    def _get_client(self) -> grpcclient.InferenceServerClient:
        """Initialize or return the gRPC client channel."""
        if self._grpc_client is None:
            self._grpc_client = grpcclient.InferenceServerClient(
                url=self.server_url,
                verbose=False,
            )
        return self._grpc_client

    def is_server_live(self) -> bool:
        """Check if Triton Inference Server is reachable via gRPC."""
        try:
            client = self._get_client()
            return bool(client.is_server_live())
        except Exception:
            return False

    def is_model_ready(self, model_name: str) -> bool:
        """Check if a specific model is loaded and ready on Triton."""
        try:
            client = self._get_client()
            return bool(client.is_model_ready(model_name))
        except Exception:
            return False

    def _get_local_ort_session(self, model_name: str) -> ort.InferenceSession:
        """Retrieve local INT8 ONNX Runtime session for offline fallback."""
        if model_name not in self._ort_sessions:
            onnx_path = self.model_repo_dir / model_name / "1" / "model.onnx"
            if not onnx_path.exists():
                raise FileNotFoundError(f"Local ONNX model not found at {onnx_path}")
            self._ort_sessions[model_name] = ort.InferenceSession(
                str(onnx_path),
                providers=["CPUExecutionProvider"],
            )
            logger.info("Initialized fallback local INT8 ONNX session for %s", model_name)
        return self._ort_sessions[model_name]

    # =========================================================================
    # StGNN Forecaster Inference
    # =========================================================================

    def infer_stgnn(
        self,
        node_features: np.ndarray,
        adj_norm: Optional[np.ndarray] = None,
    ) -> Dict[str, np.ndarray]:
        """Perform predictive rumor diffusion inference via StGNN Forecaster.

        Args:
            node_features: Shape (36, 3, 12) or (batch_size, 36, 3, 12) float32.
            adj_norm: Optional normalized adjacency matrix (36, 36).

        Returns:
            Dict containing:
                - 'predictions': Array of shape (batch_size, 36, 2)
                - 'attention_weights': Array of shape (12,)
        """
        # Ensure batch dimension
        if node_features.ndim == 3:
            node_features = np.expand_dims(node_features, axis=0)
        node_features = node_features.astype(np.float32)

        if adj_norm is None:
            adj_norm = self._cached_adj_norm
        adj_norm = adj_norm.astype(np.float32)

        # 1. Attempt Triton gRPC inference
        if self.is_server_live():
            try:
                client = self._get_client()
                inputs = [
                    grpcclient.InferInput("node_features", list(node_features.shape), "FP32"),
                    grpcclient.InferInput("adj_norm", list(adj_norm.shape), "FP32"),
                ]
                inputs[0].set_data_from_numpy(node_features)
                inputs[1].set_data_from_numpy(adj_norm)

                outputs = [
                    grpcclient.InferRequestedOutput("predictions"),
                    grpcclient.InferRequestedOutput("attention_weights"),
                ]

                response = client.infer(
                    model_name="stgnn_forecaster",
                    inputs=inputs,
                    outputs=outputs,
                    timeout=self.timeout,
                )

                preds = response.as_numpy("predictions")
                attn = response.as_numpy("attention_weights")
                return {"predictions": preds, "attention_weights": attn}
            except Exception as exc:
                logger.warning("Triton gRPC StGNN inference failed (%s); using local INT8 fallback.", exc)

        # 2. Resilient local INT8 ONNX fallback
        sess = self._get_local_ort_session("stgnn_forecaster")
        res = sess.run(None, {"node_features": node_features, "adj_norm": adj_norm})
        return {"predictions": res[0], "attention_weights": res[1]}

    # =========================================================================
    # FANG Joint Objective Inference
    # =========================================================================

    def infer_fang(
        self,
        claim_emb: np.ndarray,
        source_feat: np.ndarray,
        context_feat: np.ndarray,
    ) -> Dict[str, np.ndarray]:
        """Perform joint rumor classification and credibility scoring via FANG.

        Args:
            claim_emb: Semantic embedding (B, 768) float32.
            source_feat: Source authority features (B, 16) float32.
            context_feat: Context graph features (B, 32) float32.

        Returns:
            Dict containing:
                - 'rumor_logits': Array of shape (B, 2)
                - 'cred_score': Array of shape (B, 1)
        """
        if claim_emb.ndim == 1:
            claim_emb = np.expand_dims(claim_emb, axis=0)
        if source_feat.ndim == 1:
            source_feat = np.expand_dims(source_feat, axis=0)
        if context_feat.ndim == 1:
            context_feat = np.expand_dims(context_feat, axis=0)

        claim_emb = claim_emb.astype(np.float32)
        source_feat = source_feat.astype(np.float32)
        context_feat = context_feat.astype(np.float32)

        # 1. Attempt Triton gRPC inference
        if self.is_server_live():
            try:
                client = self._get_client()
                inputs = [
                    grpcclient.InferInput("claim_emb", list(claim_emb.shape), "FP32"),
                    grpcclient.InferInput("source_feat", list(source_feat.shape), "FP32"),
                    grpcclient.InferInput("context_feat", list(context_feat.shape), "FP32"),
                ]
                inputs[0].set_data_from_numpy(claim_emb)
                inputs[1].set_data_from_numpy(source_feat)
                inputs[2].set_data_from_numpy(context_feat)

                outputs = [
                    grpcclient.InferRequestedOutput("rumor_logits"),
                    grpcclient.InferRequestedOutput("cred_score"),
                ]

                response = client.infer(
                    model_name="fang_joint",
                    inputs=inputs,
                    outputs=outputs,
                    timeout=self.timeout,
                )

                return {
                    "rumor_logits": response.as_numpy("rumor_logits"),
                    "cred_score": response.as_numpy("cred_score"),
                }
            except Exception as exc:
                logger.warning("Triton gRPC FANG inference failed (%s); using local INT8 fallback.", exc)

        # 2. Resilient local INT8 ONNX fallback
        sess = self._get_local_ort_session("fang_joint")
        res = sess.run(
            None,
            {
                "claim_emb": claim_emb,
                "source_feat": source_feat,
                "context_feat": context_feat,
            },
        )
        return {"rumor_logits": res[0], "cred_score": res[1]}

    # =========================================================================
    # MuRIL Indic Encoder Inference
    # =========================================================================

    def infer_muril(
        self,
        input_ids: np.ndarray,
        attention_mask: Optional[np.ndarray] = None,
    ) -> Dict[str, np.ndarray]:
        """Perform Indic text encoding and sentiment classification via MuRIL.

        Args:
            input_ids: Array of token IDs (B, seq_len) int64.
            attention_mask: Optional attention mask (B, seq_len) int64.

        Returns:
            Dict containing:
                - 'logits': Array of shape (B, 4)
                - 'pooled_embedding': Array of shape (B, 768)
        """
        if input_ids.ndim == 1:
            input_ids = np.expand_dims(input_ids, axis=0)
        input_ids = input_ids.astype(np.int64)

        if attention_mask is None:
            attention_mask = np.ones_like(input_ids, dtype=np.int64)
        elif attention_mask.ndim == 1:
            attention_mask = np.expand_dims(attention_mask, axis=0)
        attention_mask = attention_mask.astype(np.int64)

        # 1. Attempt Triton gRPC inference
        if self.is_server_live():
            try:
                client = self._get_client()
                inputs = [
                    grpcclient.InferInput("input_ids", list(input_ids.shape), "INT64"),
                    grpcclient.InferInput("attention_mask", list(attention_mask.shape), "INT64"),
                ]
                inputs[0].set_data_from_numpy(input_ids)
                inputs[1].set_data_from_numpy(attention_mask)

                outputs = [
                    grpcclient.InferRequestedOutput("logits"),
                    grpcclient.InferRequestedOutput("pooled_embedding"),
                ]

                response = client.infer(
                    model_name="muril_encoder",
                    inputs=inputs,
                    outputs=outputs,
                    timeout=self.timeout,
                )

                return {
                    "logits": response.as_numpy("logits"),
                    "pooled_embedding": response.as_numpy("pooled_embedding"),
                }
            except Exception as exc:
                logger.warning("Triton gRPC MuRIL inference failed (%s); using local INT8 fallback.", exc)

        # 2. Resilient local INT8 ONNX fallback
        sess = self._get_local_ort_session("muril_encoder")
        res = sess.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
            },
        )
        return {"logits": res[0], "pooled_embedding": res[1]}


# Singleton getter
_triton_client_instance: Optional[TritonInferenceClient] = None


def get_triton_client() -> TritonInferenceClient:
    """Retrieve or initialize singleton TritonInferenceClient."""
    global _triton_client_instance
    if _triton_client_instance is None:
        _triton_client_instance = TritonInferenceClient()
    return _triton_client_instance
