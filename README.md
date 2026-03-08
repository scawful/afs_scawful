# AFS Scawful

**Personal Skills & Context for AFS.**

This repository contains personal configurations, skills, model registries, and
domain-specific workflows for the Agentic File System (AFS). It serves as an
extension of core AFS, keeping personal and specialist surfaces out of the core
repo.

## Contents

- **Skills:** specialized capabilities for agents (e.g., specific coding styles, project management).
- **Context:** Personal documentation, notes, and memory files.
- **Config:** Custom configurations for AFS services and tools.
- **Legacy command surfaces:** model, gateway, benchmark, and training commands
  that should not ship in core `afs` by default.
- **Policies:** Guidelines and rules for agent behavior.

## Usage

This repository is intended to be mounted or linked into an AFS installation to
provide personalized context and capabilities.

## Extension Setup

Enable this repo as an AFS extension:

```toml
[extensions]
enabled_extensions = ["afs_scawful"]
extension_dirs = ["~/src/lab/afs-scawful"]
```

The extension manifest lives at `extension.toml` and re-exposes legacy
model/training/gateway CLI groups through `afs_scawful.extension_cli`.

## License

MIT
