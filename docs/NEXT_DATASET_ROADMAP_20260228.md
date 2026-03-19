# Next Dataset Roadmap (2026-02-28)

Scope: convert current ideas into executable dataset/training steps for coding + personal models.

## 1) Multi-Teacher Coding Distillation from Logs

Build a fresh prompt pack from local chat/coding datasets:

```bash
python3 scripts/build_distill_prompts_from_logs.py \
  --sources data/training_data/claude_log_pairs.jsonl \
            data/training_data/cpp_log_pairs.jsonl \
            data/training_data/commit_diff_v1.jsonl \
  --output docs/eval/distill_prompts_logs_v1.jsonl \
  --target-count 220
```

Run cloud-teacher distillation on that prompt pack:

```bash
python3 scripts/distill_cloud.py \
  --prompts docs/eval/distill_prompts_logs_v1.jsonl \
  --models sonnet-4.6,codex-5.3,gemini-3.1-pro \
  --output data/training_data/distill_logs_coding_v1.jsonl \
  --min-score 0.6
```

## 2) Conductor v3 Dataset (Schema + Repair)

Generate Conductor v3 training data with normal DAG plans plus JSON-repair samples:

```bash
python3 scripts/build_conductor_v3_dataset.py \
  --output data/training_data/conductor_v3.jsonl \
  --plan-count 80 \
  --repair-count 40
```

Train:

```bash
python3 scripts/train_persona.py --persona conductor_v3
```

## 3) Poet v4 Form Control

Generate a new poetry dataset with explicit form tags (`haiku`, `imagist`, `free_verse`, `sonnet_like`, `prose_to_poem`):

```bash
python3 scripts/persona_dataset.py generate \
  --persona poet_v4 \
  --teacher gemini \
  --limit 40
```

Train:

```bash
python3 scripts/train_persona.py --persona poet_v4
```

## 4) Essay Import Goal via Google Drive CLI

Import likely essay documents from Google Drive into local raw text files + JSONL manifest:

```bash
python3 scripts/import_gdrive_essays.py \
  --max-files 80 \
  --output-dir data/raw/essays_gdrive \
  --manifest data/training_data/essays_gdrive_manifest_v1.jsonl \
  --raw-text-jsonl data/training_data/essays_gdrive_raw_v1.jsonl
```

If OAuth has not been granted for `gdrive`, run:

```bash
gdrive account add
```

Then rerun the import command.

## 5) Quick Audit

```bash
python3 scripts/dataset_audit.py --section data
```

Targets now tracked:
- `conductor_v3.jsonl` (120)
- `poet_v4.jsonl` (40)
- `essays_gdrive_raw_v1.jsonl` (80)
