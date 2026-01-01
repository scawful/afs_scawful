# Windows Workflow (MECHANICA)

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
./scripts/install_windows_helpers.sh --host mm-lan
```

Create the Windows `D:\src` universe (if missing):

```bash
./scripts/windows_setup_src.sh --host mm-lan
```

Run these on the Windows host after SSH:

```cmd
D:\afs_training\scripts\afs_help.cmd
D:\afs_training\scripts\afs_status.cmd
D:\afs_training\scripts\afs_logs.cmd
powershell -NoProfile -File D:\afs_training\scripts\afs_audit.ps1
```

Install PowerShell profile helpers (optional, per-user):

```cmd
powershell -NoProfile -File D:\afs_training\scripts\install_profile.ps1
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

## Training Task Control

```cmd
schtasks /query /tn AFS_Autocomplete_Train
schtasks /end /tn AFS_Autocomplete_Train
```

## FIM Queue

```bash
HOST=mm-lan ./scripts/queue_autocomplete_fim.sh
```
