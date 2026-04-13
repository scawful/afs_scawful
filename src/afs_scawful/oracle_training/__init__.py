"""Zelda/oracle training specs built on shared model_ops."""

from .zelda_bundle_specs import build_zelda_bundle, get_zelda_bundle_spec, validate_zelda_bundle_spec
from .zelda_eval_hooks import build_zelda_eval_plan, format_eval_plan, run_zelda_eval_hooks
from .zelda_registry_hooks import build_zelda_registry_plan, format_registry_plan, run_zelda_registry_hooks
from .zelda_tracks import ZELDA_TRACK_SPECS, get_zelda_track_spec, list_zelda_tracks

__all__ = [
    "ZELDA_TRACK_SPECS",
    "build_zelda_bundle",
    "build_zelda_eval_plan",
    "build_zelda_registry_plan",
    "format_eval_plan",
    "format_registry_plan",
    "get_zelda_bundle_spec",
    "get_zelda_track_spec",
    "list_zelda_tracks",
    "run_zelda_eval_hooks",
    "run_zelda_registry_hooks",
    "validate_zelda_bundle_spec",
]
