# Windows Dev Strategy (MECHANICA)

This is a macro plan to keep MECHANICA as a reliable remote dev, training, and
inference node that fits the NERV mesh and `~/src` universe while still
allowing desktop/gaming use when needed.

## Goals

- Reliable remote access (LAN + Tailscale).
- Consistent dev tooling across Mac, Windows, and WSL2.
- Predictable training runtime + logs.
- A mixed-use policy where training/inference can be paused, throttled, or
  offloaded when gaming or interactive work takes priority.
- Minimal downtime and clear recovery steps.

## Current Snapshot (2026-01-01 audit)

- OS: Windows 11 Pro build 26220.
- LAN IP: <lan-ip> (prefer `mm-lan` alias).
- Services: sshd + Tailscale running (Automatic).
- WSL default: v2; Ubuntu is the expected helper-script distro name.
- Training: FIM run active (GPU 99-100% during audit).

## Current Live Check (2026-04-19)

- Host reachable via `ssh medical-mechanica`.
- `wsl --status`: default version is `2`.
- `wsl -l -v`: `Ubuntu` is already on `WSL2`.
- Primary local GPU policy now assumes the installed RTX `5090`; the old
  `5060 Ti` is no longer part of the main local training plan.
- `Ubuntu` is `20.04`, so the bootstrap should provision its own Python `3.11`
  env instead of relying on distro Python `3.8`.
- Inside Ubuntu, `/mnt/d/src` and `/mnt/d/src/training` are visible.
- Core CLI/build tools such as `rg`, `fzf`, `gcc`, and `make` were missing
  before bootstrap and are now managed by `afs_setup_wsl.ps1`.

## TODO List

Legend: [remote]=safe over SSH, [manual]=needs local UI/admin, [blocked]=wait
for training idle.

### Access + Identity

- [x] LAN SSH alias `mm-lan` in `~/.ssh/config` [remote]
- [x] sshd + Tailscale services running [remote]
- [ ] Confirm DHCP reservation for <lan-ip> [manual]
- [ ] Verify Windows firewall inbound rule for OpenSSH on Private profile
  [manual/admin]
- [ ] Optional WAN access (DDNS + port forward) [manual]

### WSL2 + Linux Toolchain

- [x] Confirm Ubuntu WSL2 (`wsl -l -v`) [remote]
- [ ] Start Ubuntu and run base updates (`apt update && apt upgrade`)
  [remote/manual]
- [ ] Install core tools in WSL: git, python3, rg, fzf, build-essential
  [remote/manual]
- [ ] Enable systemd in WSL (`/etc/wsl.conf`) if needed [remote/manual]
- [ ] Bootstrap WSL with
  `./scripts/windows_setup_wsl.sh --host medical-mechanica --distro Ubuntu`
  [remote/manual]
- [ ] Finish user bootstrap inside WSL with
  `/mnt/d/src/training/scripts/wsl_bootstrap_training.sh` [manual]
- [x] Prefer `D:\\src` as the Windows source root and expose it to WSL as
  `/mnt/d/src` [remote]
- [ ] Clone core repos in chosen root (oracle-of-secrets, yaze, afs-scawful,
  halext-org, ops, docs) [remote/manual]
- [ ] Configure git identity + SSH keys in WSL [remote/manual]
- [ ] Install `ws` CLI in WSL and confirm `ws list` works [remote/manual]
- [x] Create `D:\\src` universe root and bucket folders
  (`hobby/`, `lab/`, `halext/`, `tools/`, `third_party/`) [remote]

### Windows Tooling

- [ ] Install baseline tools via winget: Git, Python, VS Code, Windows
  Terminal, 7zip, ripgrep [remote/manual]
- [ ] Ensure Python + CUDA toolchain versions match training scripts [remote]
- [ ] Verify OpenSSH client/server versions [remote]
- [ ] Configure Windows Terminal profiles for PowerShell + WSL + SSH [manual]

### NERV + ~/src Universe + Halext

- [ ] Add LAN fallback note into NERV docs (optional) [remote]
- [ ] Add `halext-nj` SSH config + test access from Windows or WSL
  [remote/manual]
- [ ] Decide whether to mount `halext` via WSL sshfs or copy sync [manual]
- [ ] Align secrets: keep Windows `.secrets` separate from repo [manual]
- [x] Document Windows `D:\\src` mapping to `/mnt/d/src` for WSL workflows
  [remote]

### Training Ops + Observability

- [x] Windows helper scripts installed to `D:\\afs_training\\scripts`
  [remote]
- [x] FIM queue helper in repo (`queue_autocomplete_fim.sh`) [remote]
- [x] Install PowerShell profile helpers (`install_profile.ps1`) [remote]
- [ ] Schedule daily audit (`afs_audit.ps1`) to log to
  `D:\\afs_training\\logs` [remote/manual]
- [ ] Add GPU stat snapshot task (optional) [remote/manual]
- [ ] Implement log rotation / archive for `D:\\afs_training\\logs`
  [remote/manual]

### Performance + Reliability

- [ ] Set power plan to High/Ultimate Performance [manual/admin]
- [ ] Disable sleep/hibernation on AC; keep display timeout reasonable
  [manual/admin]
- [ ] Set Windows Update active hours + pause during long runs [manual]
- [ ] Trim startup apps not needed for training (NZXT CAM, Armoury Crate,
  overlays) [manual]
- [ ] Optional Defender exclusions for `D:\\afs_training` (risk tradeoff)
  [manual/admin]
- [ ] Keep pagefile enabled (auto-managed or fixed size) [manual]

### Backups + Recovery

- [ ] Decide backup target for `D:\\afs_training\\models` [manual]
- [ ] Document recovery steps for SSH/Tailscale/training [remote]

## Phase 0: Audit (safe, remote)

Run the audit and save a baseline report:

```bash
./scripts/windows_audit.sh --host mm-lan
```

Windows script: `D:\\afs_training\\scripts\\afs_audit.ps1`

## Phase 1: Access + Identity

- OpenSSH Server on Windows (auto-start).
- Key-only SSH (disable password auth).
- Firewall rule for SSH on LAN.
- Tailscale installed + auto-start.
- LAN fallback host entry (`mm-lan`).
- Optional: DHCP reservation for a stable LAN IP.

## Phase 2: WSL2 + Dev Shell

Recommended: WSL2 Ubuntu. The helper default is the live distro name
`Ubuntu`; pass `--distro Ubuntu-24.04` only for hosts that installed that exact
name.

- Enable WSL2 features (requires reboot).
- Install Ubuntu and set default distro.
- Install core tools: `git`, `python3`, `rg`, `fzf`, `build-essential`.
- Enable systemd in WSL if needed.
- Preferred source-of-truth on Windows: keep repos in `D:\\src` and expose them
  to WSL at `/mnt/d/src`.
- Preferred training policy: use WSL as the default execution layer for local
  training, keep native Windows for LM Studio and host control, and fall back
  to Vast when the shared desktop cannot spare the GPU.
- Inside WSL, create `~/src -> /mnt/d/src` so existing `ws` and `~/src/...`
  tooling continues to work.
- Use Linux-only venvs in `~/.venvs/` instead of trying to share a `.venv`
  across Windows and WSL.
- Bootstrap commands:
  - Windows side:
    `./scripts/windows_setup_wsl.sh --host medical-mechanica --distro Ubuntu`
  - WSL side: `/mnt/d/src/training/scripts/wsl_bootstrap_training.sh`

The intended steady-state is:

- WSL is the default execution layer for local training
- native Windows remains the host-control and LM Studio layer
- Vast is the fallback when the shared desktop cannot spare the GPU
- `afs-hostd` should own LM Studio and host-level actions so repo-local tools
  stop duplicating SSH + encoded PowerShell control paths
- `afs-hostd` should also own WSL runtime surfaces for `training.status`,
  `training.start`, `training.stop`, `vllm.status`, `vllm.start`, and
  `vllm.stop`, with repo-local controllers becoming thin HTTP clients over the
  local `127.0.0.1:8766` tunnel
- `afs-hostd` should own host-level sleep policy for training mode; current
  live behavior now suppresses AC sleep/hibernation at training start and
  restores the prior values when the run is stopped through hostd
- `afs-hostd` should also expose a higher-level machine mode surface so Mac
  operators can flip between `train`, `serve`, and `interactive` without
  manually coordinating power, LM Studio unloads, and `vllm` state
- the live WSL control path is now validated on `medical-mechanica`; hostd no
  longer drives those endpoints through `bash -lc` heredocs and instead uses
  direct `wsl.exe -- <argv>` execution for status/env probes and service-script
  actions

## Phase 3: Tooling + Workspace

- `winget` baseline: Git, Python, VS Code, 7zip, Windows Terminal.
- GPU drivers (NVIDIA Studio or Game Ready, consistent with CUDA).
- SSH keys + `~/.ssh/config` alignment.
- Optional: VS Code Remote WSL for consistent tooling.

## Phase 4: Performance + Reliability

- Power plan: High Performance or Ultimate Performance.
- Disable sleep on AC, keep display timeout reasonable.
- Set Windows Update active hours to avoid mid-run reboots.
- Optional Defender exclusions for training paths (risk tradeoff).
- Keep pagefile enabled (auto-managed or fixed size).

## Phase 5: Observability + Maintenance

- Health script scheduled daily (logs to `D:\\afs_training\\logs`).
- Tail commands and status helpers on Windows:
  - `afs_help.cmd`, `afs_status.cmd`, `afs_logs.cmd`, `afs_tail.ps1`
- Optional scheduled task to snapshot `nvidia-smi` stats.

## Phase 6: Backups + Recovery

- Document recovery steps for SSH, Tailscale, and training.
- Export SSH host keys if needed.
- File History or external backup for `D:\\afs_training\\models`.

## Related Docs

- `docs/WINDOWS_WORKFLOW.md` (daily usage)
- `~/src/docs/NERV_INFRASTRUCTURE.md` (mesh overview)
- `~/src/docs/SRC_UNIVERSE_NETWORK.md` (sync + source-of-truth)
