from __future__ import annotations

import subprocess

from afs_scawful.windows import wsl


def test_envs_includes_expected_venv_names(monkeypatch):
    monkeypatch.setattr(
        wsl,
        "run_wsl_json_command",
        lambda argv, **kwargs: {
            "venvs": [
                {"name": "src-training", "exists": True},
                {"name": "text-serve", "exists": False},
                {"name": "diffusers", "exists": False},
            ]
        },
    )
    payload = wsl.envs()
    assert [item["name"] for item in payload["venvs"]] == ["src-training", "text-serve", "diffusers"]


def test_training_action_uses_json_service_script(monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return {"state": "running", "task": "oracle-fast"}

    monkeypatch.setattr(wsl, "run_wsl_json_command", fake_run)
    payload = wsl.training_action("status", task="oracle-fast", config="configs/zelda/qwen35_oracle_fast_v2.toml")
    assert payload["state"] == "running"
    assert seen["argv"][:4] == ["bash", "/mnt/d/src/training/scripts/wsl_training_service.sh", "status", "--task"]
    assert "--json" in seen["argv"]


def test_training_action_omits_tilde_venv_override(monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return {"state": "running", "task": "oracle-fast"}

    monkeypatch.setattr(wsl, "run_wsl_json_command", fake_run)
    wsl.training_action(
        "status",
        task="oracle-fast",
        config="configs/zelda/qwen35_oracle_fast_v2.toml",
        venv_dir="~/.venvs/src-training",
    )
    assert "--venv" not in seen["argv"]


def test_vllm_action_uses_json_service_script(monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return {"state": "running", "served_name": "local-helper-qwen3-8b-v1"}

    monkeypatch.setattr(wsl, "run_wsl_json_command", fake_run)
    payload = wsl.vllm_action("status", served_name="local-helper-qwen3-8b-v1")
    assert payload["state"] == "running"
    assert seen["argv"][:3] == ["bash", "/mnt/d/src/training/scripts/wsl_vllm_service.sh", "status"]
    assert "--json" in seen["argv"]


def test_eval_action_uses_json_service_script(monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return {"state": "running", "name": "oracle-main-capability"}

    monkeypatch.setattr(wsl, "run_wsl_json_command", fake_run)
    payload = wsl.eval_action(
        "status",
        name="oracle-main-capability",
        model="Qwen/Qwen3-14B",
        adapter="/mnt/d/src/training/output/qwen3-oracle-14b-v2/final",
        prompt_pack="/mnt/d/src/training/evals/oracle_main_capability_eval_v1.jsonl",
        out="/mnt/d/src/training/evals/runs/qwen3_oracle_14b_v2_oracle_main_capability_eval_v1.jsonl",
    )
    assert payload["state"] == "running"
    assert seen["argv"][:3] == ["bash", "/mnt/d/src/training/scripts/wsl_eval_service.sh", "status"]
    assert "--json" in seen["argv"]


def test_run_wsl_bash_falls_back_to_redirect_on_detached_wsl_pipe_error(monkeypatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="",
            stderr="Wsl/Service/0x800703e3",
        )

    monkeypatch.setattr(wsl.subprocess, "run", fake_run)
    monkeypatch.setattr(wsl.os, "name", "nt")
    monkeypatch.setattr(
        wsl,
        "_run_wsl_command_via_redirect",
        lambda argv, **kwargs: "redirect-ok",
    )
    assert wsl.run_wsl_bash("echo hi") == "redirect-ok"


def test_run_wsl_bash_falls_back_to_redirect_on_timeout(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs.get("timeout", 60.0))

    monkeypatch.setattr(wsl.subprocess, "run", fake_run)
    monkeypatch.setattr(wsl.os, "name", "nt")
    monkeypatch.setattr(
        wsl,
        "_run_wsl_command_via_redirect",
        lambda argv, **kwargs: "redirect-timeout-ok",
    )
    assert wsl.run_wsl_bash("echo hi") == "redirect-timeout-ok"


def test_redirect_runner_uses_file_handles(monkeypatch, tmp_path):
    calls = {}

    class DummyTempDir:
        def __enter__(self):
            tmp_path.mkdir(exist_ok=True)
            return str(tmp_path)

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_run(argv, **kwargs):
        calls["argv"] = argv
        calls["stdout_name"] = getattr(kwargs.get("stdout"), "name", "")
        calls["stderr_name"] = getattr(kwargs.get("stderr"), "name", "")
        kwargs["stdout"].write("ok\n")
        kwargs["stderr"].write("")
        return subprocess.CompletedProcess(args=argv, returncode=0)

    monkeypatch.setattr(wsl.tempfile, "TemporaryDirectory", lambda prefix="": DummyTempDir())
    monkeypatch.setattr(wsl.subprocess, "run", fake_run)

    output = wsl._run_wsl_bash_via_redirect("echo hi", distro="Ubuntu", timeout=5)
    assert output == "ok"
    assert calls["argv"] == ["wsl.exe", "-d", "Ubuntu", "--", "bash", "-lc", "echo hi"]
    assert calls["stdout_name"].endswith("stdout.txt")
    assert calls["stderr_name"].endswith("stderr.txt")
