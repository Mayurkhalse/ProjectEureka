"""Project EUREKA Processor: MuRIL Sentiment, StGNN Spatio-Temporal Prep, and IPCS."""

from eureka.processor.muril_head import MuRILSentimentPipeline
from eureka.processor.stgnn_prep import StGNNDataPreparation
from eureka.processor.ipcs_adapter import IPCSAdapter

try:
    from eureka.processor.stgnn_dataset import (
        EurekaTemporalDatasetBuilder,
        build_static_district_edge_index,
        merge_static_and_dynamic_edges,
        MAHARASHTRA_DISTRICTS,
        NUM_MAHARASHTRA_DISTRICTS,
    )
    from eureka.processor.stgnn_model import EurekaA3TGCN
    from eureka.processor.stgnn_trainer import StGNNTrainer, infer_risk_diffusion, train_stgnn_task
except (ImportError, Exception):
    EurekaTemporalDatasetBuilder = None  # type: ignore
    build_static_district_edge_index = None  # type: ignore
    merge_static_and_dynamic_edges = None  # type: ignore
    MAHARASHTRA_DISTRICTS = []
    NUM_MAHARASHTRA_DISTRICTS = 36
    EurekaA3TGCN = None  # type: ignore
    StGNNTrainer = None  # type: ignore
    infer_risk_diffusion = None  # type: ignore
    train_stgnn_task = None  # type: ignore

__all__ = [
    "MuRILSentimentPipeline",
    "StGNNDataPreparation",
    "IPCSAdapter",
    "EurekaA3TGCN",
    "EurekaTemporalDatasetBuilder",
    "build_static_district_edge_index",
    "merge_static_and_dynamic_edges",
    "MAHARASHTRA_DISTRICTS",
    "NUM_MAHARASHTRA_DISTRICTS",
    "StGNNTrainer",
    "infer_risk_diffusion",
    "train_stgnn_task",
]

