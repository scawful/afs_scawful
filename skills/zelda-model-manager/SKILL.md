---
name: zelda-model-manager
description: Evaluate, train, register, or serve Zelda/ALTTP/Oracle models; curate ASM and tool-use datasets; verify GGUF/MLX artifacts and model readiness. Use for model lifecycle work, not ordinary Oracle or yaze code changes.
---

# Zelda Model Manager

1. **Name one adoption outcome.** Identify the task, model role, owner, consumer,
   and result the consumer will use. Tie release support to the existing Oracle
   Christmas plan. A model review does not start a training or deployment lane.
2. **Inspect the actual consumer.** AFS chat uses
   `~/src/lab/afs-scawful/config/chat_registry.toml`. Hobby z3cli defaults to
   `~/src/hobby/z3cli/config/chat_registry.toml`; check `Z3CLI_REGISTRY` for an
   override. Inspect the consumer's route implementation as well as its names.
   Offline answer selection, a prompt guard, and live model routing differ.
3. **Read raw results before portfolio prose.** Locate the candidate's newest
   `runs/<run>/result.json`, completions, compile/CPU reports and held-out gates
   under `~/src/training/`, plus real z3cli reports when applicable. Report failed
   or missing gates with their denominators and evidence scope. Distinguish
   development, held-out, offline selection, and live-tool results. Training loss,
   successful tool transport and a model's completion claim are not task success.
4. **State verified model state.** Use explicit terms: configured, artifact
   present, endpoint advertised, loaded, inference-tested, evaluated, promoted.
   Bind the relevant artifact/config/revision to the result. Catalog discovery
   proves availability, not loading or quality; deployment needs endpoint proof.
5. **Teach current tools before changing weights.** Discover the actual yaze,
   z3ed or MCP catalog and reuse its schemas and verified examples. Evaluate the
   model with that same contract. Train only for a measured gap; use verified
   tool/result/correction trajectories and keep held-out answers separate.
   Before an authorized run, check dataset schema, overlap, freshness and the
   slot's current hard gates. For ASM, require unchanged-source assembly and
   execution contracts; keep CPU fixtures separate from native game proof.

For cross-session delivery, update the existing AFS tooling task with entry point,
verification, adoption target and next action. Notify its consumer through AFS.
Verified branch output is ready; close delivery after adoption or explicit
deferral. Reuse the existing readiness watcher for changed-state alerts.

Load [operational sources](references/sources.md) only for the selected task.
Keep model family, hardware and quantization choices based on measured results
and the current serving contract, rather than a fixed size ladder.
