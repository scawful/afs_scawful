# Dataset Lifecycle and QA

This describes the preferred flow for building training datasets that stay
auditable and easy to index.

## Folder Phases (suggested)

```
raw/         # untouched input (scans, exports, dumps)
ocr/         # OCR outputs + extracted text
staging/     # cleaned text, deduped, normalized
datasets/    # final train/val/test artifacts
index/       # dataset_registry.json, resource_index.json
```

## Lifecycle Steps

1) **Collect raw**
   - Keep raw data in `raw/` (never train directly on this).

2) **Extract / OCR**
   - Use `scripts/ingest_ocr.py` for PDFs/images.
   - Output goes to `ocr/` with `manifest.jsonl` and `failures.jsonl`.

3) **Clean + Normalize**
   - Strip headers/footers, page numbers, OCR noise.
   - Deduplicate if necessary.
   - Keep cleaned text in `staging/`.

4) **Build dataset**
   - Convert to the training schema (chat or instruction).
   - Write `train.jsonl`, `val.jsonl`, `test.jsonl` into `datasets/<name>/`.

5) **Validate**
   - ASM datasets: `scripts/validate_asm_dataset.py` or `validate_asm_dataset_v2.py`
   - Label-free evals: `scripts/evaluate_model.py` (as needed)

6) **QA summary**
   - `scripts/dataset_qa_summary.py --inputs ... --output <report.md>`

7) **Index**
   - `python -m afs_scawful datasets index`
   - `python -m afs_scawful resources index`

8) **Train + log**
   - Store logs under `runs/` and keep run metadata next to models.

## QA Checklist

- [ ] Parse clean JSONL (no errors)
- [ ] Required fields present (instruction/output or chat schema)
- [ ] Duplicates removed
- [ ] No private info that should be excluded
- [ ] Length distribution is reasonable (no 0-char samples)
- [ ] Validation split exists and is not empty
- [ ] Registry + resource index updated

## Notes on Indexing

The dataset registry only includes:
- Directories with `train.jsonl` / `val.jsonl` / `test.jsonl` / `stats.json`
- Top-level JSONL files inside the datasets root

Keep raw/ocr/staging outside the datasets root to avoid indexing noise.
