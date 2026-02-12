date: 2026-02-12
summary:
- Patched scripts/eval_echoflow_avatar_remote.py with schema-first strict-json mode, extraction/normalization, and one retry.
- Re-ran served evals on medical-mechanica:
  - 7B microfix strictfix: 22/24 (invalid_json eliminated)
  - 1.5B repair strictfix: 21/24 (invalid_json eliminated)
- Updated promotion/gate/training loop docs with strictfix outcomes.
- Updated EchoFlow LocalLLMService strict-json handling and provider model defaults; iOS build passes.
