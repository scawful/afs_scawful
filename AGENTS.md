# Agent Instructions (AFS Scawful Plugin)

## Do not invent or market
- No marketing language or product claims.
- If something is unknown, state "Unknown / needs verification" and propose a test.

## Truth policy
- Only claim what is evidenced in this repo or cited notes.
- Do not guess roadmap, compatibility, or performance.

## Scope control
- Research-only plugin scope; keep to Scawful-specific tooling.

## Provenance / separation
- Do not use employer or internal material.
- If provenance is unclear, leave it out.

## Secrets / credentials
- Never commit secrets (API keys, passwords, private keys, terraform state).
- Store Vultr passwords in `infra/.passwords/` and keep them out of git.
- Run `infra/secret_scan.sh` before sharing or committing changes.

## Infrastructure awareness
- Use workspace docs: `docs/NERV_INFRASTRUCTURE.md`, `docs/WINDOWS_WORKFLOW.md`, `docs/WINDOWS_DEV_STRATEGY.md`.
- Prefer SSH aliases (`medical-mechanica`, `mm-lan`, `halext-nj`) over raw IPs.
- Windows src root is `D:\src`; Mac mounts live under `~/Mounts/`.

## Output style
- Concise, engineering notebook tone.

## How to verify (tests/commands)
- `pytest`
