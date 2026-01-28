# Agent Tool Policy (Global)

Purpose: one place to declare what shell commands are allowed for agents.

Source of truth:
- `policies/agent_tools.json`

How to update:
1. Edit `policies/agent_tools.json` (add/remove commands).
2. Sync exports:
```
python3 /Users/scawful/src/lab/afs-scawful/scripts/policy_sync.py --targets context,config,harness --wire
```

Where it writes:
- `~/.context/knowledge/agent_tools.json`
- `~/.config/agent-tools/agent_tools.json`
- `~/.{claude,codex,gemini}/agent_tools.json` (symlinked when `--wire` is used)
- `~/.codex/rules/default.rules` (injects an allowlist block when `--wire` is used)

Important:
- Codex CLI enforces `~/.codex/rules/default.rules`. The agent_tools JSON is an export + human reference unless the runner reads it.

Deletion approvals (streamlined):
- Use the trash-first helper instead of `rm -rf`:
```
python3 /Users/scawful/src/lab/afs-scawful/scripts/agent_delete.py trash <paths> --reason "cleanup"
```
- Approve purges for a short window (default 30 minutes):
```
python3 /Users/scawful/src/lab/afs-scawful/scripts/agent_delete.py approve --ttl 30 --note "cleanup window"
```
- Purge entries without additional prompts while approval is active:
```
python3 /Users/scawful/src/lab/afs-scawful/scripts/agent_delete.py purge <id-or-path>
```
- Check/revoke approval:
```
python3 /Users/scawful/src/lab/afs-scawful/scripts/agent_delete.py status
python3 /Users/scawful/src/lab/afs-scawful/scripts/agent_delete.py revoke
```
