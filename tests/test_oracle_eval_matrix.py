from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = REPO_ROOT / "docs" / "eval" / "oracle_boundary_effort_matrix_v1.jsonl"

REQUIRED_SURFACES = {
    "oos-author",
    "oos-debug",
    "alttp-trace",
    "xref",
    "wrong-convention-suppression",
}
REQUIRED_EFFORTS = {"low", "medium", "high"}


def _load_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in MATRIX_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        rows.append(json.loads(stripped))
    return rows


def test_oracle_eval_matrix_has_required_surfaces_and_unique_ids() -> None:
    rows = _load_rows()

    assert rows, "matrix must not be empty"

    surfaces = {str(row["surface"]) for row in rows}
    ids = [str(row["id"]) for row in rows]

    assert REQUIRED_SURFACES.issubset(surfaces)
    assert len(ids) == len(set(ids)), "matrix IDs must be unique"


def test_oracle_eval_matrix_effort_groups_cover_all_tiers() -> None:
    rows = _load_rows()

    efforts_by_group: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        group = str(row["effort_group"])
        effort = str(row["effort"])
        efforts_by_group[group].add(effort)

    assert efforts_by_group, "matrix must include effort groups"
    for group, efforts in efforts_by_group.items():
        assert REQUIRED_EFFORTS == efforts, f"effort group {group} is missing a tier: {efforts}"


def test_oracle_eval_matrix_rows_include_boundary_fields() -> None:
    rows = _load_rows()

    required_fields = {
        "id",
        "surface",
        "domain",
        "mode",
        "effort",
        "effort_group",
        "instruction",
        "input",
        "category",
        "expected_keywords",
    }
    for row in rows:
        missing = required_fields - set(row)
        assert not missing, f"row {row.get('id', '(unknown)')} missing fields: {sorted(missing)}"
        assert isinstance(row["expected_keywords"], list) and row["expected_keywords"], (
            f"row {row['id']} must include non-empty expected_keywords"
        )
