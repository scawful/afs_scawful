# Skills Integration (Global Harnesses)

Source of truth lives in this repo:
- `/Users/scawful/src/lab/afs-scawful/skills/`

## Sync script

Run the sync script to wire skills into each harness:

```
python3 /Users/scawful/src/lab/afs-scawful/scripts/skills_sync.py
```

Optional flags:
- `--dry-run` to preview changes
- `--force` to replace conflicting paths (backs up existing targets)

## Harness mappings

- **Claude Code**
  - Skill directories symlinked into: `~/.claude/skills/<skill-name>`
- **Codex**
  - Skill directories symlinked into: `~/.codex/skills/<skill-name>`
  - Leave `~/.codex/skills/.system` untouched
- **Gemini CLI**
  - Extension: `~/.gemini/extensions/scawful-skills/`
  - Context file: `GEMINI.md` (symlinked to `skills/GEMINI.md`)
  - Enabled via `~/.gemini/extensions/extension-enablement.json`
- **AFS context**
  - Skills mirrored into: `~/.context/knowledge/skills` (symlink)

## Adding a new skill

1. Create a directory: `skills/<skill-name>/` with `SKILL.md`.
2. Add optional `references/` files.
3. Update `skills/GEMINI.md` with a new entry.
4. Run `scripts/skills_sync.py` to update harness wiring.