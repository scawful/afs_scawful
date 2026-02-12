# Echo Model Training Loop (2026-02-11)

## Scope
This runbook prepares Echo personality/capability evals for post-train gating and builds repair samples for the next fine-tune cycle used by EchoFlow iOS/macOS.

## Latest Gate Run (2026-02-12)
- Execution report: `docs/ECHO_MODEL_GATE_20260212.md`
- Baseline (`echo-qwen25-1p5b-v1`): `4/24`
- New 1.5B repair adapter: `22/24`
- New 7B v4+repair adapter: `23/24`
- Residual issue: bullet list formatting (`cap_bullets_001`)

## Artifacts Added
- Eval pack: `docs/eval/echoflow_avatar_eval_v2.jsonl`
- Remote eval runner: `scripts/eval_echoflow_avatar_remote.py`
- Repair dataset builder: `scripts/build_echo_repair_dataset.py`

## 1) Run Avatar Eval Against medical-mechanica
```bash
cd ~/src/lab/afs-scawful
python3 scripts/eval_echoflow_avatar_remote.py \
  --endpoint http://medical-mechanica:1234 \
  --model gguf/afs/echo-qwen25-1p5b-v1-q8_0.gguf \
  --eval-pack docs/eval/echoflow_avatar_eval_v2.jsonl \
  --strict-json-response-format \
  --timeout 25 \
  --max-tokens 160 \
  --out docs/eval/echoflow_avatar_eval_run_medical_$(date +%Y%m%d_%H%M%S).json
```

## 2) Build Repair Dataset From Failures
```bash
cd ~/src/lab/afs-scawful
python3 scripts/build_echo_repair_dataset.py \
  --eval-pack docs/eval/echoflow_avatar_eval_v2.jsonl \
  --eval-report docs/eval/echoflow_avatar_eval_run_medical_<timestamp>.json \
  --out-dir docs/eval/echo_repair_seed_v1
```

Output files:
- `docs/eval/echo_repair_seed_v1/train.jsonl`
- `docs/eval/echo_repair_seed_v1/valid.jsonl`
- `docs/eval/echo_repair_seed_v1/manifest.json`

## 3) Merge Repair Samples Into Training Corpus
Use existing chat-format corpus tooling in `~/src/training/datasets/scribe-corpus/`.
The repair seed files are already `{"messages": [...]}` format.

## 4) Re-Eval Gate Before Promoting Defaults
Minimum gate for app default promotion:
- pass rate >= 0.80 on `echoflow_avatar_eval_v2.jsonl`
- all JSON cases parse cleanly
- no safety-forbidden strings on safety/memory cases

## 5) Windows First, Vast.ai Fallback
If `medical-mechanica` is unavailable:
1. Follow `docs/VAST_SETUP.md`.
2. Host an OpenAI-compatible endpoint.
3. Re-run the same eval command by swapping `--endpoint`.

## API Freshness Check (Gemini-CLI + docs)
Validated against current provider docs before this update:
- Gemini structured outputs: use `responseMimeType` + `responseSchema` when strict schema is required. (`https://ai.google.dev/gemini-api/docs/structured-output`)
- LM Studio OpenAI-compatible API: supports `response_format` with `json_object` and `json_schema` modes. (`https://lmstudio.ai/docs/app/api/structured-output`)
- Ollama structured outputs: `format` can be a JSON schema object for stricter output constraints. (`https://ollama.com/blog/structured-outputs`)

Recommendation for next app pass:
1. keep current JSON-object enforcement for compatibility.
2. add per-feature schema payloads for classify/tool routes to reduce contract drift.

## Cleanup Expectations
- Keep eval outputs in `docs/eval/` with timestamped names.
- Remove temporary local files from `/tmp` after ad-hoc tests.
- Remove temporary remote files from `%TEMP%` on Windows after manual experiments.
