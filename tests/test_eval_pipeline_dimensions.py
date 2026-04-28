from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from afs_scawful.eval.config import EvalConfig
from afs_scawful.eval.pipeline import EvalReport, EvalResult, EvalPipeline
from afs_scawful.integrations.ollama_client import ModelResponse, Prompt
from afs_scawful.validators import ValidationResult


def _result(*, surface: str, domain: str, mode: str, effort: str, score: float, valid: bool = True) -> EvalResult:
    prompt = Prompt(
        instruction=f"prompt for {surface}",
        category="oracle",
        surface=surface,
        domain=domain,
        mode=mode,
        effort=effort,
    )
    response = ModelResponse(text="ok", model="oracle", prompt="p", latency_ms=10.0)
    validation = ValidationResult(valid=valid, score=score, errors=[] if valid else ["bad"], warnings=[])
    return EvalResult(prompt=prompt, response=response, validation=validation, category="oracle")


def test_eval_report_tracks_surface_domain_mode_and_effort_stats() -> None:
    report = EvalReport(
        config=EvalConfig(),
        results=[
            _result(surface="oos-author", domain="oos", mode="author", effort="low", score=1.0),
            _result(surface="oos-author", domain="oos", mode="author", effort="high", score=0.6),
            _result(surface="xref", domain="xref", mode="trace", effort="high", score=0.8),
        ],
        start_time=datetime(2026, 1, 1),
        end_time=datetime(2026, 1, 1),
        model_name="oracle",
    )

    by_surface = report.surface_stats()
    by_domain = report.domain_stats()
    by_mode = report.mode_stats()
    by_effort = report.effort_stats()
    data = report.to_dict()

    assert by_surface["oos-author"]["total"] == 2
    assert by_domain["oos"]["total"] == 2
    assert by_mode["author"]["total"] == 2
    assert by_effort["high"]["total"] == 2
    assert "by_surface" in data and "xref" in data["by_surface"]
    assert "by_domain" in data and "oos" in data["by_domain"]
    assert "By Surface" in report.to_markdown(include_samples=False)


def test_eval_pipeline_load_prompts_from_jsonl_preserves_oracle_dimensions(tmp_path: Path) -> None:
    path = tmp_path / "matrix.jsonl"
    rows = [
        {
            "id": "oracle_boundary_01",
            "surface": "alttp-trace",
            "domain": "alttp-vanilla",
            "mode": "trace",
            "effort": "high",
            "instruction": "Trace this routine.",
            "input": "",
            "category": "oracle",
            "expected_keywords": ["trace"],
            "_metadata": {"tags": ["boundary", "trace"]},
        }
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    prompts = EvalPipeline.load_prompts_from_jsonl(path)

    assert len(prompts) == 1
    prompt = prompts[0]
    assert prompt.surface == "alttp-trace"
    assert prompt.domain == "alttp-vanilla"
    assert prompt.mode == "trace"
    assert prompt.effort == "high"
    assert prompt.tags == ["boundary", "trace"]
    assert prompt.category == "oracle"


def test_eval_pipeline_load_prompts_from_jsonl_falls_back_to_section_for_category(tmp_path: Path) -> None:
    path = tmp_path / "section_only.jsonl"
    row = {
        "id": "oracle_section_only_01",
        "section": "thinking",
        "instruction": "Explain the debugging order.",
        "input": "",
        "expected_keywords": ["debugging"],
        "_metadata": {"surface": "oos-debug", "domain": "oos", "mode": "debug", "effort": "high"},
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    prompts = EvalPipeline.load_prompts_from_jsonl(path)

    assert len(prompts) == 1
    assert prompts[0].category == "thinking"


def test_eval_pipeline_load_prompts_from_jsonl_tolerates_loose_metadata(tmp_path: Path) -> None:
    path = tmp_path / "loose_metadata.jsonl"
    row = {
        "instruction": "Check this trace.",
        "tags": "smoke",
        "_metadata": "not a mapping",
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    prompts = EvalPipeline.load_prompts_from_jsonl(path)

    assert len(prompts) == 1
    assert prompts[0].tags == ["smoke"]
    assert prompts[0].metadata == {}
