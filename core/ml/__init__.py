"""
core/ml/__init__.py — Central Machine Learning & Deep Learning Package for JARVIS.
"""

from core.ml.hardware_detector import (
    HardwareDetector,
    HardwareProfile,
    hardware_detector,
)
from core.ml.dataset_researcher import (
    DatasetCandidate,
    DatasetResearcher,
    dataset_researcher,
)
from core.ml.dataset_downloader import (
    DatasetDownloader,
    VerifiedDataset,
    dataset_downloader,
)
from core.ml.pipeline_builder import (
    MLPipelineBuilder,
    pipeline_builder,
)
from core.ml.ml_agent import (
    MLAgent,
    ml_agent,
)

__all__ = [
    "HardwareDetector",
    "HardwareProfile",
    "hardware_detector",
    "DatasetCandidate",
    "DatasetResearcher",
    "dataset_researcher",
    "DatasetDownloader",
    "VerifiedDataset",
    "dataset_downloader",
    "MLPipelineBuilder",
    "pipeline_builder",
    "MLAgent",
    "ml_agent",
]
