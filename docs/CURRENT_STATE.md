# Current State (2026-01-07)

Scope: afs-scawful (research-only plugin).

## Training

- scawful-echo training restarted on Vast (RTX 4090).
  - Instance: 29472137 (label: scawful-echo)
  - SSH: `ssh -p 10873 root@145.236.166.111`
  - Log: `/opt/training/logs/scawful-echo-gemma2-9b-v2.log`
  - Model output: `/opt/training/models/scawful-echo-gemma2-9b-v2` (verify path)
- Muse v2 training completed on Vast (RTX 4090).
  - Instance: 29465486 (label: muse-v2)
  - SSH: `ssh -p 25486 root@ssh4.vast.ai`
  - Log: `/opt/training/logs/muse-v2.log` (remote)
  - Model output: `/opt/training/models/muse-v2` (remote)
  - Local artifacts: `~/src/training/models/muse-v2`
  - Local log: `~/src/training/logs/muse-v2.log`
  - LoRA GGUF: `~/src/training/models/muse-v2/muse-v2-lora.gguf`
  - Modelfile: `~/src/training/models/muse-v2/Modelfile`
  - Ollama model: `muse-v2:latest` (base `qwen2.5:3b`)
  - Package: `~/src/training/models/muse-v2.tar.gz` (copied to `D:\afs_training\models`)
  - Eval pack: `~/src/training/evals/muse-v2_prompt_pack.jsonl`
  - Eval results: `~/src/training/evals/muse-v2_eval_2026-01-04.jsonl`
- Local Mac Ollama has `scawful-echo:latest` (Gemma2 9B + LoRA) from `/Users/scawful/src/training/models/scawful-echo-gemma2-9b/Modelfile`.
- scawful-echo dataset refreshed in `training/scribe-corpus` with full blog set + 1,783 twitter samples (ratio 0.5, cap 2000). See `training/docs/SCAWFUL_ECHO_AB_PLAN.md`.
- Qwen2.5-7B micro overfit succeeded on MECHANICA (loss 2.73 -> 0.40). Full run staged via `D:\afs_training\scripts\run_scawful_echo_full.cmd`.
- Alternate text datasets exported for A/B (`mlx_data_scawful_echo_text_chatml`, `mlx_data_scawful_echo_text_gemma`) and synced to `D:\afs_training\datasets`.
- A/B queue script staged on MECHANICA: `D:\afs_training\scripts\queue_scawful_echo_ab.ps1` (waits for Qwen chat run, then Gemma 2B micro + full chat training + evals).

## Data and OCR

- OCR pipeline: `scripts/ingest_ocr.py` (ocrmypdf + tesseract + pdftotext on macOS).
- Smoke run completed from two PDFs (scribe-corpus):
  - Output: `D:\afs_training\raw\ocr\ocr_smoke_output_20260103_105726`
  - `dataset.jsonl` empty (text length below default `--min-chars 200`).
  - Inputs staged at `D:\afs_training\raw\scans\ocr_smoke2`.
- Indexes refreshed on Windows:
  - `D:\afs_training\index\dataset_registry.json`
  - `D:\afs_training\index\resource_index.json`

## Storage and Mounts

- macOS system volume near capacity (last check: ~95% full).
- SSHFS mount `~/Mounts/mm-d` is unstable (process starts, mount not visible).
- Workaround used: direct `scp` to Windows (`mm-lan:/D:/afs_training`) for model/log sync.
- HF base cache archived and copied to Windows:
  - `~/src/training/cache/qwen2.5-3b-instruct_hf.tar.gz`
  - `D:\afs_training\cache\huggingface\qwen2.5-3b-instruct_hf.tar.gz`
- `D:\` content is accessible over SSH; `E:\` exists but is not mounted via SSHFS on macOS (Unknown / needs verification).

## Tooling

- Use the repo venv for CLI (`.venv/bin/python`); system `python` is 2.7.
- Vast CLI available at `~/.local/bin/vastai`.
- Vast status supports multiple instances: `python -m afs_scawful vast status --all`.

## Open Issues

- Re-run Gemma micro overfit after latest dataset refresh.
- Decide where to restart scawful-echo training (Vast vs Windows GPU).
- Stabilize mm-d (and mm-e) SSHFS mounts on macOS.
- Re-run OCR with real scans or lower `--min-chars` if needed.
