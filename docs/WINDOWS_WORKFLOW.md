# Windows Workflow (MECHANICA)

`medical-mechanica` is now the primary local mixed-use train/infer host for the
Oracle-family and scawfulbot stack. WSL2 on top of the existing `D:\src`
layout is the preferred execution layer for training; native Windows remains
useful for LM Studio and host-level helpers.

## SSH Access

- Tailscale: `ssh medical-mechanica`
- LAN fallback: `ssh mm-lan`

For local scripts, override the host as needed:

```bash
HOST=mm-lan ./scripts/train_autocomplete_remote.sh --status
```

Macro plan: `docs/WINDOWS_DEV_STRATEGY.md`

## Windows Helper Scripts

Install/update the helpers on Windows:

```bash
./scripts/install_windows_helpers.sh --host medical-mechanica
```

Bootstrap or refresh WSL2 around the shared `D:\src` / `D:\src\training`
layout:

```bash
./scripts/windows_setup_wsl.sh --host medical-mechanica --distro Ubuntu
```

The helper default is `Ubuntu`, matching the live `medical-mechanica` distro.
Set `AFS_WSL_DISTRO` before running the Windows `.cmd` wrappers if a host uses
a different distro name:

```cmd
set AFS_WSL_DISTRO=Ubuntu-24.04
```

Phase-0 shared host-control skeleton:

```bash
ssh medical-mechanica "powershell -NoProfile -File D:\\afs_training\\scripts\\afs_hostd.ps1 -Mode start"
ssh medical-mechanica "powershell -NoProfile -File D:\\afs_training\\scripts\\afs_hostd.ps1 -Mode status"
```

Tunnel it from the Mac control plane with:

```bash
./scripts/tunnel_windows_hostd.sh --host mm-lan --background
```

Then point clients at:

```bash
export AFS_HOSTD_URL="http://127.0.0.1:8766"
```

This is now the preferred control surface for Windows LM Studio state and
model load/unload, plus WSL runtime status for training and `vllm`. Repo-local
wrappers should prefer `AFS_HOSTD_URL` first and only fall back to raw SSH +
PowerShell when the daemon is not running yet.

Current live hostd surfaces:

- `GET /healthz`
- `GET /v1/version`
- `GET /v1/status`
- `GET /v1/power/status`
- `POST /v1/power/training-on`
- `POST /v1/power/restore`
- `GET /v1/mode`
- `POST /v1/mode`
- `GET /v1/lmstudio/status`
- `GET /v1/lmstudio/models`
- `GET /v1/lmstudio/loaded`
- `POST /v1/lmstudio/load`
- `POST /v1/lmstudio/unload`
- `GET /v1/wsl/status`
- `GET /v1/wsl/envs`
- `GET /v1/vllm/status`
- `POST /v1/vllm/start`
- `POST /v1/vllm/stop`
- `GET /v1/eval/status`
- `POST /v1/eval/start`
- `POST /v1/eval/stop`
- `GET /v1/training/status`
- `POST /v1/training/start`
- `POST /v1/training/stop`

`/v1/training/status` now uses a direct Windows-side filesystem snapshot of
`D:\afs_training\run`, `D:\afs_training\logs`, config-resolved `metrics.jsonl`,
and checkpoint dirs instead of depending on a live `wsl.exe` status probe.
That makes last-step / loss / ETA reads much more reliable on mixed-use boxes.

Hostd-managed training now suppresses Windows sleep and hibernation on AC
automatically at training start and restores the previous AC values when the
run is stopped through hostd. The saved power policy lives in:

- `D:\afs_training\run\afs_hostd_power_state.json`

Manual power controls from the Mac side:

```bash
export AFS_HOSTD_URL="http://127.0.0.1:8766"
python /mnt/d/src/training/scripts/windows_zelda_ctl.py power-status
python /mnt/d/src/training/scripts/windows_zelda_ctl.py power-train-on
python /mnt/d/src/training/scripts/windows_zelda_ctl.py power-restore
```

Higher-level machine modes are now available too:

- `train` - suppress sleep on AC, stop `vllm`, unload LM Studio models
- `serve` - suppress sleep on AC, keep serving surfaces intact
- `interactive` - restore saved power policy, stop `vllm`, unload LM Studio models

Training-repo examples once the tunnel is open:

```bash
export AFS_HOSTD_URL="http://127.0.0.1:8766"
python scripts/windows_zelda_ctl.py mode-status --task qwen3-oracle-14b-v2 --config configs/zelda/qwen3_oracle_14b_v2.toml
python scripts/windows_zelda_ctl.py set-mode --mode train
python scripts/windows_zelda_ctl.py set-mode --mode interactive
```

If you want `serve` or `interactive` mode to stop a known training task too,
pass `--task ... --config ... --stop-training`.

The `afs_hostd.ps1` helper starts the daemon detached via `Win32_Process`, so
it survives the SSH session instead of dying with the job tree.

The live `medical-mechanica` validation path now works end-to-end for WSL
runtime control through hostd:

```bash
export AFS_HOSTD_URL="http://127.0.0.1:8766"
python scripts/windows_zelda_ctl.py wsl-status
python scripts/windows_zelda_ctl.py wsl-envs
python scripts/windows_zelda_ctl.py status --task qwen35-oracle-fast-v2 --config configs/zelda/qwen35_oracle_fast_v2.toml --tail 5
```

Hostd now executes WSL probes and service scripts through direct
`wsl.exe -- <argv>` calls instead of shell-heavy `bash -lc` heredocs. That
avoids the timeout/hanging path we were seeing on the live Windows host.

Quick post-install checks:

```bash
./scripts/tunnel_windows_hostd.sh --host medical-mechanica --background
curl -fsS http://127.0.0.1:8766/healthz
curl -fsS http://127.0.0.1:8766/v1/version
curl -fsS http://127.0.0.1:8766/v1/wsl/status
```

Stage the LM Studio preset bundle on Windows:

```bash
./scripts/sync_windows_lmstudio_presets.sh --host mm-lan
```

Create the Windows `D:\src` universe (if missing):

```bash
./scripts/windows_setup_src.sh --host mm-lan
```

Bootstrap WSL2 around the same `D:\src` / `D:\src\training` layout:

```bash
./scripts/windows_setup_wsl.sh --host medical-mechanica --distro Ubuntu
```

Then, inside WSL on the Windows machine:

```bash
/mnt/d/src/training/scripts/wsl_bootstrap_training.sh
/mnt/d/src/training/scripts/wsl_install_qwen_fast_path.sh
```

That bootstrap installs `uv`, builds a Python `3.11` venv at `~/.venvs/src-training`, creates `~/src -> /mnt/d/src`, and writes `~/.config/afs/wsl-training.env.sh` so shared caches stay on `D:`.

The fast-path helper keeps a private CUDA 12.9 toolchain under `~/.local/cuda-wsl-12.9`, installs `flash-linear-attention`, and builds `causal-conv1d` for the `5090` without requiring `sudo` inside WSL.

Optional dedicated envs:

```bash
/mnt/d/src/training/scripts/wsl_bootstrap_text_serve.sh
/mnt/d/src/training/scripts/wsl_bootstrap_diffusers.sh
```

Those create:
- `~/.venvs/text-serve` for `vllm` and OpenAI-compatible text serving
- `~/.venvs/diffusers` for image / video generation work

Common WSL runtime helpers after bootstrap:

```bash
/mnt/d/src/training/scripts/wsl_vllm_service.sh start
/mnt/d/src/training/scripts/stage_diffusers_model.py --model-id segmind/SSD-1B
/mnt/d/src/training/scripts/wsl_run_5090_benchmark.sh run
```

Run these on the Windows host after SSH:

```cmd
D:\afs_training\scripts\afs_help.cmd
D:\afs_training\scripts\afs_status.cmd
D:\afs_training\scripts\afs_logs.cmd
powershell -NoProfile -File D:\afs_training\scripts\afs_audit.ps1
D:\afs_training\scripts\afs_vllm.cmd start
D:\afs_training\scripts\afs_stage_image_model.cmd --model-id segmind/SSD-1B
D:\afs_training\scripts\afs_benchmark_5090.cmd run
```

Install PowerShell profile helpers (optional, per-user):

```cmd
powershell -NoProfile -File D:\afs_training\scripts\install_profile.ps1
```

Install the local host-control daemon at logon (optional, per-user):

```cmd
powershell -NoProfile -File D:\afs_training\scripts\install_hostd_startup.ps1
```

Tail a specific log:

```powershell
powershell -NoProfile -File D:\afs_training\scripts\afs_tail.ps1 D:\afs_training\logs\training_autocomplete.log
```

Run an audit report:

```bash
./scripts/windows_audit.sh --host mm-lan
```

## Common Paths

- Logs: `D:\afs_training\logs`
- Models: `D:\afs_training\models`
- Datasets: `D:\afs_training\datasets`
- Scripts: `D:\afs_training\scripts`
- SRC root: `D:\src`
- WSL src root: `/mnt/d/src`
- WSL training root: `/mnt/d/src/training`

## Placement Policy

- local-first on `medical-mechanica` + WSL2 for `oracle-fast`,
  `oracle-coder`, specialist `9B` lines, evals, merges, quant/export, and most
  corrective work
- `14B` is also local-first now; use Vast only when local stability, runtime,
  or desktop availability is not good enough
- `scawfulbot` inference is shared on the same machine, but should be
  throttled, paused, or offloaded when training, gaming, or interactive work
  needs the box
- current policy assumes the `5090` as the local training GPU; do not rely on a
  `5060 Ti` sidecar in the main workflow docs

## Training Task Control

```cmd
schtasks /query /tn AFS_Autocomplete_Train
schtasks /end /tn AFS_Autocomplete_Train
```

## FIM Queue

```bash
HOST=mm-lan ./scripts/queue_autocomplete_fim.sh
```

## WSL Notes

- Treat `D:\src` as the Windows source root and expose it into Linux as `/mnt/d/src`.
- Keep Linux-only virtual environments in the WSL home directory, not under `D:\src`.
- After `wsl_bootstrap_training.sh`, the WSL user should have `~/src -> /mnt/d/src`.
- `ws` expects `~/src`, so the symlink matters.
- Shared caches should live on `D:` via `~/.config/afs/wsl-training.env.sh`, not inside the distro filesystem.
