# Cloud Model Integrations

Research-only notes for using Google AI Studio and Vertex AI Gemini models with AFS Scawful.

## Google AI Studio (Gemini API)

Requirements:
- API key in `GEMINI_API_KEY` (fallback: `AISTUDIO_API_KEY`).

List models:
```bash
python -m afs_scawful eval list-models --provider studio
```

Run a single prompt:
```bash
python -m afs_scawful eval test \
  --provider studio \
  --model gemini-3-pro-preview \
  --prompt "Explain what LDA $0E20,X does."
```

Notes:
- Use `eval list-models` to confirm availability.
- Model names can be passed as `gemini-...` or `models/gemini-...`.

## Vertex AI (Gemini API)

Requirements:
- `gcloud` authenticated (`gcloud auth login`).
- Project/region set via CLI flags or environment variables.

List models:
```bash
python -m afs_scawful eval list-models \
  --provider vertex \
  --vertex-project halext \
  --vertex-location us-east1
```

Run a single prompt:
```bash
python -m afs_scawful eval test \
  --provider vertex \
  --vertex-project halext \
  --vertex-location us-east1 \
  --model gemini-3-flash-preview \
  --prompt "Summarize this 65816 routine."
```

Notes:
- If `gcloud` is not on PATH, pass `--gcloud-path /opt/homebrew/bin/gcloud`.
- Model names can be passed as `gemini-...`, `publishers/google/models/gemini-...`,
  or full `projects/.../locations/.../publishers/google/models/...` paths.

## OpenAI

Requirements:
- API key in `OPENAI_API_KEY`.

List models:
```bash
python -m afs_scawful chat list-models --provider openai
```

Run a single prompt:
```bash
python -m afs_scawful chat run --provider openai --model gpt-5.2
```

Notes:
- Use `OPENAI_API_MODE=responses` to target the Responses API when needed.
- Model IDs should be verified against the provider list.

## Anthropic

Requirements:
- API key in `ANTHROPIC_API_KEY`.

List models:
```bash
python -m afs_scawful chat list-models --provider anthropic
```

Run a single prompt:
```bash
python -m afs_scawful chat run --provider anthropic --model opus-4.5
```

Notes:
- `ANTHROPIC_VERSION` overrides the API version header.
- Model IDs should be verified against the provider list.
