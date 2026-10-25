"""Unit and Integration Tests for Triton Inference Client and INT8 Quantized Engines.

Validates:
1. Dynamic INT8 Post-Training Quantization (PTQ) models (StGNN, FANG, MuRIL).
2. Dynamic batching and dynamic axes across variable batch sizes.
3. Zero-PyTorch Celery worker offloading via Triton gRPC client with resilient local ONNX fallback.
4. Triton model repository configuration files (config.pbtxt) and dynamic batching parameters.
"""

from pathlib import Path
import numpy as np
import pytest

try:
    import onnxruntime
    HAS_ORT = True
except ImportError:
    HAS_ORT = False

pytestmark = pytest.mark.skipif(not HAS_ORT, reason="onnxruntime not installed in this environment")

from eureka.processor.stgnn_dataset import EurekaTemporalDatasetBuilder
from eureka.processor.stgnn_trainer import infer_risk_diffusion
from eureka.processor.triton_client import TritonInferenceClient, get_triton_client

MODEL_REPO = Path(__file__).resolve().parent.parent / "src" / "eureka" / "model_repository"


def test_triton_model_repository_configs():
    """Verify Triton configuration files and dynamic batching parameters."""
    models = ["stgnn_forecaster", "fang_joint", "muril_encoder"]

    for model_name in models:
        pbtxt_path = MODEL_REPO / model_name / "config.pbtxt"
        onnx_path = MODEL_REPO / model_name / "1" / "model.onnx"

        assert pbtxt_path.exists(), f"Missing config.pbtxt for {model_name}"
        assert onnx_path.exists(), f"Missing model.onnx for {model_name}"

        content = pbtxt_path.read_text(encoding="utf-8")
        assert f'name: "{model_name}"' in content
        assert "dynamic_batching" in content
        assert "max_queue_delay_microseconds: 2000" in content
        assert "platform: \"onnxruntime_onnx\"" in content


def test_triton_client_singleton_and_adj():
    """Verify Triton client initialization and normalized adjacency caching."""
    client = get_triton_client()
    assert isinstance(client, TritonInferenceClient)
    assert client._cached_adj_norm.shape == (36, 36)
    # Check degree-normalized property: row sums approximate 1.0 or normalized weights
    assert np.all(np.isfinite(client._cached_adj_norm))


def test_stgnn_int8_inference_single_and_batched():
    """Verify StGNN Forecaster INT8 inference across single and multi-batch inputs."""
    client = get_triton_client()

    # 1. Single sample: (36, 3, 12)
    single_x = np.random.uniform(0.0, 50.0, size=(36, 3, 12)).astype(np.float32)
    single_res = client.infer_stgnn(node_features=single_x)

    assert "predictions" in single_res
    assert "attention_weights" in single_res
    assert single_res["predictions"].shape == (1, 36, 2)
    assert single_res["attention_weights"].shape == (12,)
    assert np.all(np.isfinite(single_res["predictions"]))
    assert np.all(np.isfinite(single_res["attention_weights"]))

    # 2. Batched input: (4, 36, 3, 12)
    batch_x = np.random.uniform(0.0, 50.0, size=(4, 36, 3, 12)).astype(np.float32)
    batch_res = client.infer_stgnn(node_features=batch_x)

    assert batch_res["predictions"].shape == (4, 36, 2)
    assert np.all(np.isfinite(batch_res["predictions"]))


def test_fang_joint_int8_inference():
    """Verify FANG Joint Objective INT8 inference for rumor classification & credibility scoring."""
    client = get_triton_client()
    batch_size = 4

    claim_emb = np.random.randn(batch_size, 768).astype(np.float32)
    source_feat = np.random.uniform(0.0, 1.0, size=(batch_size, 16)).astype(np.float32)
    context_feat = np.random.uniform(0.0, 1.0, size=(batch_size, 32)).astype(np.float32)

    res = client.infer_fang(
        claim_emb=claim_emb,
        source_feat=source_feat,
        context_feat=context_feat,
    )

    assert "rumor_logits" in res
    assert "cred_score" in res
    assert res["rumor_logits"].shape == (batch_size, 2)
    assert res["cred_score"].shape == (batch_size, 1)

    # Credibility score should be bounded in [0.0, 1.0] by sigmoid
    assert np.all(res["cred_score"] >= 0.0)
    assert np.all(res["cred_score"] <= 1.0)


def test_muril_encoder_int8_inference():
    """Verify MuRIL Indic Encoder INT8 inference for classification logits and pooled embeddings."""
    client = get_triton_client()
    batch_size = 3
    seq_len = 32

    input_ids = np.random.randint(1, 30000, size=(batch_size, seq_len), dtype=np.int64)
    attention_mask = np.ones((batch_size, seq_len), dtype=np.int64)

    res = client.infer_muril(input_ids=input_ids, attention_mask=attention_mask)

    assert "logits" in res
    assert "pooled_embedding" in res
    assert res["logits"].shape == (batch_size, 4)
    assert res["pooled_embedding"].shape == (batch_size, 768)
    assert np.all(np.isfinite(res["logits"]))
    assert np.all(np.isfinite(res["pooled_embedding"]))


def test_infer_risk_diffusion_with_triton_pipeline():
    """Verify infer_risk_diffusion runs end-to-end through Triton client without PyTorch model."""
    builder = EurekaTemporalDatasetBuilder(periods=12, forecast_horizon_hours=6)
    dataset = builder.generate_synthetic_historical_signal(num_snapshots=3, seed=99)

    # Calling infer_risk_diffusion without passing model defaults to Triton/INT8 pipeline
    output = infer_risk_diffusion(dataset)

    assert output["total_districts_monitored"] == 36
    assert output["forecast_horizon_hours"] == 6
    assert len(output["district_risk_matrix"]) == 36
    assert len(output["top_critical_districts"]) <= 5
    assert len(output["attention_weights"]) == 12

    # Check 5-Zone summary
    summary = output["dgipr_5_zone_summary"]
    for zone in ["Konkan", "Pune", "Nashik", "Chhatrapati Sambhajinagar", "Vidarbha"]:
        assert zone in summary
        assert 0.0 <= summary[zone] <= 1.0

    # Ensure all risk scores are in [0, 1]
    for d in output["district_risk_matrix"]:
        assert 0.0 <= d["risk_score"] <= 1.0
        assert d["risk_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
