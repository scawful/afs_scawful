from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# These files were copied from core AFS before the repository split and have no
# afs_scawful implementation to exercise. Keep them visible for relocation
# history, but do not accidentally collect them against whichever core checkout
# happens to be installed in the active environment.
CORE_OWNED_TESTS = (
    "test_benchmarks.py",
    "test_continuous_learning.py",
    "test_deployment_validator.py",
    "test_integration.py",
    "test_quality.py",
    "test_quality_gates.py",
)
collect_ignore = list(CORE_OWNED_TESTS)
