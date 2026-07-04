from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "cores" / "eval" / "personality_eval.py"


def _write_core_fixture(tmp_path: Path) -> tuple[Path, Path]:
    prompt_path = tmp_path / "prompts" / "tester.md"
    prompt_path.parent.mkdir(parents=True)
    prompt_path.write_text("you are tester.\n", encoding="utf-8")

    eval_pack_path = tmp_path / "eval" / "tester_eval.jsonl"
    eval_pack_path.parent.mkdir(parents=True)
    eval_pack_path.write_text(
        json.dumps(
            {
                "id": "case-001",
                "prompt": "review this function",
                "category": "code_review",
                "expected_content": ["function"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "cores": [
                    {
                        "id": "tester",
                        "name": "Tester",
                        "base_model": "gguf/example-base.gguf",
                        "system_prompt_path": "prompts/tester.md",
                        "eval_pack_path": "eval/tester_eval.jsonl",
                        "parameters": {"temperature": 0.25, "max_tokens": 333},
                    }
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return registry_path, eval_pack_path


def test_personality_eval_cli_uses_core_defaults_in_dry_run(tmp_path: Path) -> None:
    registry_path, _ = _write_core_fixture(tmp_path)
    output_path = tmp_path / "results.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--core",
            "tester",
            "--registry",
            str(registry_path),
            "--dry-run",
            "--output",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["model_id"] == "gguf/example-base.gguf"
    assert payload["provider"] == "studio"
    assert payload["target_source"] == "core"
    assert payload["system_prompt_enabled"] is True
    assert payload["temperature"] == 0.25
    assert payload["max_tokens"] == 333
    assert payload["total_cases"] == 1


def test_personality_eval_cli_supports_chat_model_override_and_no_system_prompt(tmp_path: Path) -> None:
    registry_path, _ = _write_core_fixture(tmp_path)
    output_path = tmp_path / "results.json"

    chat_registry_path = tmp_path / "chat_registry.toml"
    chat_registry_path.write_text(
        """
[[models]]
name = "baseline"
provider = "anthropic"
model_id = "claude-test"
system_prompt = "chat registry prompt"
options = { temperature = 0.91, max_tokens = 777 }
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--core",
            "tester",
            "--registry",
            str(registry_path),
            "--chat-registry",
            str(chat_registry_path),
            "--chat-model",
            "baseline",
            "--no-system-prompt",
            "--dry-run",
            "--output",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["model_id"] == "claude-test"
    assert payload["provider"] == "anthropic"
    assert payload["target_label"] == "baseline"
    assert payload["target_source"] == "chat_registry"
    assert payload["system_prompt_enabled"] is False
    assert payload["temperature"] == 0.91
    assert payload["max_tokens"] == 777
