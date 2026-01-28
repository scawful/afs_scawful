# OCR Ingestion (PDF + Image Scans)

Goal: ingest scanned journals (PDF/images), extract text, and stage the results
for dataset curation without overwhelming the Mac.

## Recommended Storage

- Store raw scans on Windows (`D:\afs_training\raw\scans`)
- Run OCR outputs on Windows (`D:\afs_training\raw\ocr`)
- Keep only indexes + curated JSONL on the Mac

Mount on macOS:
- `~/Mounts/mm-d` -> `D:\` (primary)
- `~/Mounts/mm-e` -> `E:\` (overflow)

## Dependencies (local or on Windows)

- `ocrmypdf` (PDF OCR, creates searchable PDFs + sidecar text)
- `tesseract` (image OCR)
- `poppler` (optional; provides `pdftotext` fallback)

## Script

Script: `scripts/ingest_ocr.py`

Outputs:
- `text/` (plain text files)
- `ocr/` (OCR-processed PDFs)
- `manifest.jsonl`
- `failures.jsonl`
- `dataset.jsonl` (optional, with `--emit-dataset`)

## Example (Windows Mount)

```bash
python ./scripts/ingest_ocr.py \
  --input ~/Mounts/mm-d/afs_training/raw/scans/journals \
  --output-root ~/Mounts/mm-d/afs_training/raw/ocr/20260103_journals \
  --lang eng \
  --emit-dataset
```

## Notes

- `dataset.jsonl` is a staging artifact. Review and clean before using it for training.
- Use `--min-chars` to ignore tiny/blank OCR output (default: 200).
- OCR can be noisy; treat it as raw input and run a cleaning pass before curation.

## Next Steps (Curation)

1. Review OCR text (spot-check 1-2% of files).
2. Clean / normalize text (strip headers, page numbers, OCR noise).
3. Convert to your training schema (chat/instruction format).
4. Run QA checks and update indexes:
   - `python -m afs_scawful datasets index`
   - `python -m afs_scawful resources index`
