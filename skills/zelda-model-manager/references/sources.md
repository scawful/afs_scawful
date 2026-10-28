# Operational sources

Open only the references needed for the current task. Dated plans explain
intent; newer raw results and the actual consumer establish current state.

| Task | Source |
|---|---|
| Dataset/run inventory | `~/src/training/INDEX.md`, `~/src/training/README.md`, candidate `runs/<run>/` and `configs/zelda/` |
| Actual readiness | `~/src/training/evals/runs/`, `~/src/training/configs/oracle_readiness_gates.json`, candidate compile/CPU reports |
| Real z3cli evaluation | `~/src/hobby/z3cli/reports/oracle-promotion-evals/`, `~/src/hobby/z3cli/docs/oracle-z3cli-promotion-eval-gate.md` |
| Consumer configuration | `~/src/lab/afs-scawful/config/chat_registry.toml` (AFS chat); `~/src/hobby/z3cli/config/chat_registry.toml` and `src/core/config.py` (z3cli) |
| Current tool contract | yaze `src/cli/service/agent/tool_registry.h` and `src/cli/service/ai/tool_schema_builder.h`; z3cli `src/protocol/z3ed_schema.py` consumes `z3ed --export-schemas` |
| Training/placement | `~/src/training/docs/TRAINING_OVERVIEW.md`, `~/src/training/docs/HOME_GPU_LAB_HARDWARE_TOPOLOGY.md`, `~/src/training/scripts/windows_zelda_ctl.py` |
| Historical role/gate decisions | `~/src/training/docs/ORACLE_FAMILY_SLOT_PLAN_20260420.md`, `ORACLE_MULTI_INTENT_READINESS_20260501.md`, `ORACLE_9B_V5_TEACHER_ROUTER_20260502.md` in that directory |
| Naming/history | `~/src/docs/NAMING_CONVENTIONS.md`, `~/src/lab/afs-scawful/docs/MODEL_PORTFOLIO.md` |
| Tool adoption | `~/.context/projects/oracle-of-secrets/scratchpad/operations/tooling_delivery.md` |

Reuse these existing entry points within the authorized task:

- Dataset QA: `afs training freshness-gate`, `afs training dataset ...`.
- Inventory: `~/src/tools/model-mgr/model-mgr list`, `info <model>` and
  `working-set-report`; use `artifacts-index` when refreshing inventory.
- Conversion: `model-mgr convert <model> --quantize <format>` or
  `model-mgr mlx-convert <model> --hf-path <path>`; verify the resulting artifact
  and its consumer before claiming deployment.
- Host access: use configured SSH aliases such as `medical-mechanica` or
  `halext-nj`. Passive status does not authorize starting or restarting a job.
