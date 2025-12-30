"""AFS Scawful package stub."""

__version__ = "0.0.0"

from .config import load_research_paths, load_training_paths, load_training_resources
from .paths import resolve_datasets_root, resolve_index_root, resolve_training_root
from .research import (
    build_research_catalog,
    load_research_catalog,
    resolve_research_catalog_path,
    resolve_research_root,
    write_research_catalog,
)
from .registry import build_dataset_registry, index_datasets, write_dataset_registry
from .resource_index import ResourceIndexer

__all__ = [
    "load_research_paths",
    "load_training_paths",
    "load_training_resources",
    "resolve_training_root",
    "resolve_datasets_root",
    "resolve_index_root",
    "resolve_research_root",
    "resolve_research_catalog_path",
    "build_research_catalog",
    "write_research_catalog",
    "load_research_catalog",
    "build_dataset_registry",
    "write_dataset_registry",
    "index_datasets",
    "ResourceIndexer",
]
