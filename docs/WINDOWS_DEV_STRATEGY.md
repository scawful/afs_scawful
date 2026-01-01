# Windows Dev Strategy (MECHANICA)

This is a macro plan to turn MECHANICA from gaming-first into a reliable remote dev and training node that fits the NERV mesh and `~/src` universe.

## Goals

- Reliable remote access (LAN + Tailscale).
- Consistent dev tooling across Mac, Windows, and WSL2.
- Predictable training runtime + logs.
- Minimal downtime and clear recovery steps.

## Current Snapshot (2026-01-01 audit)

- OS: Windows 11 Pro build 26220.
- LAN IP: 192.168.1.190.
- Services: sshd + Tailscale running (Automatic).
- WSL default: v2; Ubuntu distro is still v1 (needs conversion).
- Training: FIM run active (GPU 99-100% during audit).

## TODO List

Legend: [remote]=safe over SSH, [manual]=needs local UI/admin, [blocked]=wait for training idle.

### Access + Identity

- [x] LAN SSH alias `mm-lan` in `~/.ssh/config` [remote]
- [x] sshd + Tailscale services running [remote]
- [ ] Confirm DHCP reservation for 192.168.1.190 [manual]
- [ ] Verify Windows firewall inbound rule for OpenSSH on Private profile [manual/admin]
- [ ] Optional WAN access (DDNS + port forward) [manual]

### WSL2 + Linux Toolchain

- [ ] Convert Ubuntu WSL1 -> WSL2 (`wsl --set-version Ubuntu 2`) [remote] (in progress)
- [ ] Start Ubuntu and run base updates (`apt update && apt upgrade`) [remote/manual]
- [ ] Install core tools in WSL: git, python3, rg, fzf, build-essential [remote/manual]
- [ ] Enable systemd in WSL (`/etc/wsl.conf`) if needed [remote/manual]
- [ ] Decide `~/src` location: WSL `/home/<user>/src` vs `D:\src` [manual]
- [ ] Clone core repos in chosen root (oracle-of-secrets, yaze, afs-scawful, halext-org, ops, docs) [remote/manual]
- [ ] Configure git identity + SSH keys in WSL [remote/manual]
- [ ] Install `ws` CLI in WSL and confirm `ws list` works [remote/manual]
- [x] Create `D:\src` universe root and bucket folders (`hobby/`, `lab/`, `halext/`, `tools/`, `third_party/`) [remote]

### Windows Tooling

- [ ] Install baseline tools via winget: Git, Python, VS Code, Windows Terminal, 7zip, ripgrep [remote/manual]
- [ ] Ensure Python + CUDA toolchain versions match training scripts [remote]
- [ ] Verify OpenSSH client/server versions [remote]
- [ ] Configure Windows Terminal profiles for PowerShell + WSL + SSH [manual]

### NERV + ~/src Universe + Halext

- [ ] Add LAN IP fallback into NERV docs (optional) [remote]
- [ ] Add `halext-nj` SSH config + test access from Windows or WSL [remote/manual]
- [ ] Decide whether to mount `halext` via WSL sshfs or copy sync [manual]
- [ ] Align secrets: keep Windows `.secrets` separate from repo [manual]
- [x] Document Windows `D:\src` mapping to `/mnt/d/src` for WSL workflows [remote]

### Training Ops + Observability

- [x] Windows helper scripts installed to `D:\afs_training\scripts` [remote]
- [x] FIM queue helper in repo (`queue_autocomplete_fim.sh`) [remote]
- [x] Install PowerShell profile helpers (`install_profile.ps1`) [remote]
- [ ] Schedule daily audit (`afs_audit.ps1`) to log to `D:\afs_training\logs` [remote/manual]
- [ ] Add GPU stat snapshot task (optional) [remote/manual]
- [ ] Implement log rotation / archive for `D:\afs_training\logs` [remote/manual]

### Performance + Reliability

- [ ] Set power plan to High/Ultimate Performance [manual/admin]
- [ ] Disable sleep/hibernation on AC; keep display timeout reasonable [manual/admin]
- [ ] Set Windows Update active hours + pause during long runs [manual]
- [ ] Trim startup apps not needed for training (NZXT CAM, Armoury Crate, overlays) [manual]
- [ ] Optional Defender exclusions for `D:\afs_training` (risk tradeoff) [manual/admin]
- [ ] Keep pagefile enabled (auto-managed or fixed size) [manual]

### Backups + Recovery

- [ ] Decide backup target for `D:\afs_training\models` [manual]
- [ ] Document recovery steps for SSH/Tailscale/training [remote]

## Phase 0: Audit (safe, remote)

Run the audit and save a baseline report:

```bash
./scripts/windows_audit.sh --host mm-lan
```

Windows script: `D:\afs_training\scripts\afs_audit.ps1`

## Phase 1: Access + Identity

- OpenSSH Server on Windows (auto-start).
- Key-only SSH (disable password auth).
- Firewall rule for SSH on LAN.
- Tailscale installed + auto-start.
- LAN fallback host entry (`mm-lan`).
- Optional: DHCP reservation for a stable LAN IP.

## Phase 2: WSL2 + Dev Shell

Recommended: WSL2 Ubuntu (24.04 or 22.04).

- Enable WSL2 features (requires reboot).
- Install Ubuntu and set default distro.
- Install core tools: `git`, `python3`, `rg`, `fzf`, `build-essential`.
- Enable systemd in WSL if needed.
- Decide source-of-truth for `~/src`:
  - Option A: Keep repos in WSL (`/home/<user>/src`) and use Windows tools sparingly.
  - Option B: Keep repos in `D:\src` and access via `/mnt/d/src` from WSL.

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

- Health script scheduled daily (logs to `D:\afs_training\logs`).
- Tail commands and status helpers on Windows:
  - `afs_help.cmd`, `afs_status.cmd`, `afs_logs.cmd`, `afs_tail.ps1`
- Optional scheduled task to snapshot `nvidia-smi` stats.

## Phase 6: Backups + Recovery

- Document recovery steps for SSH, Tailscale, and training.
- Export SSH host keys if needed.
- File History or external backup for `D:\afs_training\models`.

## Related Docs

- `docs/WINDOWS_WORKFLOW.md` (daily usage)
- `docs/NERV_INFRASTRUCTURE.md` (mesh overview)
