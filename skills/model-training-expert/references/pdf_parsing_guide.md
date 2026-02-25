# PDF Parsing Guide (2026)

## Multi-Modal Strategy
In 2026, text-only parsing is considered "Legacy". For high-accuracy technical ingestion, use a vision-first approach:

1. **Page-to-Image:** Convert PDF pages to high-res PNGs.
2. **Vision Analysis:** Use Gemini 2.0 Pro Vision to describe:
   - Memory maps and table layouts.
   - Flowcharts and architectural diagrams.
   - Hand-written annotations in older ROM documents.
3. **Structured Extraction:** Prompt for JSON output matching the `ResearchPaper` schema.

## Schema: ResearchPaper
```json
{
  "id": "slug-hash",
  "title": "Full Paper Title",
  "authors": ["Author 1", "Author 2"],
  "abstract": "...",
  "key_findings": ["...", "..."],
  "technical_specs": {
    "rom_addresses": {},
    "opcodes": [],
    "architectures": []
  }
}
```

## Tools
- `afs_scawful research`: Basic text/metadata extraction.
- `scripts/vision_ingest.py`: (Planned) Vision-based ingestion pipeline.
