from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "cores" / "load_core.py"


def _write_registry(tmp_path: Path, *, base_model: str) -> Path:
    prompt_path = tmp_path / "prompts" / "tester.md"
    prompt_path.parent.mkdir(parents=True)
    prompt_path.write_text("you are tester\n", encoding="utf-8")

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "cores": [
                    {
                        "id": "tester",
                        "name": "Tester",
                        "description": "test core",
                        "status": "draft",
                        "version": "0.1.0",
                        "base_model": base_model,
                        "adapter_path": None,
                        "system_prompt_path": "prompts/tester.md",
                        "training_data_path": None,
                        "eval_pack_path": None,
                        "tags": [],
                        "parameters": {"temperature": 0.5},
                        "notes": "test",
                        "created_at": "2026-03-30",
                        "updated_at": "2026-03-30",
                    }
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return registry_path


def _write_fake_lms(tmp_path: Path, *, installed: list[dict], loaded: list[dict]) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script_path = bin_dir / "lms"
    script_path.write_text(
        f"""#!/usr/bin/env python3
import json
import sys

installed = {json.dumps(installed)}
loaded = {json.dumps(loaded)}

if sys.argv[1:] == ["ls", "--json"]:
    print(json.dumps(installed))
elif sys.argv[1:] == ["ps", "--json"]:
    print(json.dumps(loaded))
else:
    sys.exit(1)
""",
        encoding="utf-8",
    )
    script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR)
    return bin_dir


def test_load_core_info_reports_lmstudio_install_and_load_state(tmp_path: Path) -> None:
    base_model = "gguf/example-installed.gguf"
    registry_path = _write_registry(tmp_path, base_model=base_model)
    fake_path = _write_fake_lms(
        tmp_path,
        installed=[
            {
                "modelKey": base_model,
                "path": base_model,
                "indexedModelIdentifier": base_model,
            }
        ],
        loaded=[],
    )

    env = os.environ.copy()
    env["PATH"] = f"{fake_path}:{env['PATH']}"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--core",
            "tester",
            "--action",
            "info",
            "--registry",
            str(registry_path),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Installed: yes" in result.stdout
    assert "Loaded   : no" in result.stdout
    assert f"Local key : {base_model}" in result.stdout


def test_load_core_info_suggests_closest_local_model_when_missing(tmp_path: Path) -> None:
    registry_path = _write_registry(
        tmp_path,
        base_model="gguf/afs/echo-qwen25-7b-v4plusrepair_microfix3_20260225-q8_0.gguf",
    )
    fake_path = _write_fake_lms(
        tmp_path,
        installed=[
            {
                "modelKey": "gguf/scawful/scawful-echo-qwen25-7b-v4-q4km.gguf",
                "path": "gguf/scawful/scawful-echo-qwen25-7b-v4-q4km.gguf",
                "indexedModelIdentifier": "gguf/scawful/scawful-echo-qwen25-7b-v4-q4km.gguf",
            }
        ],
        loaded=[],
    )

    env = os.environ.copy()
    env["PATH"] = f"{fake_path}:{env['PATH']}"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--core",
            "tester",
            "--action",
            "info",
            "--registry",
            str(registry_path),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Installed: no" in result.stdout
    assert "Closest local matches: gguf/scawful/scawful-echo-qwen25-7b-v4-q4km.gguf" in result.stdout
