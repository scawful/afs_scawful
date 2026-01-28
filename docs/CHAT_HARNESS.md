# Chat Harness (AFS CLI)

Interactive chat for local Ollama models, custom routers, and cloud providers.
Registry defaults live in `config/chat_registry.toml`.

## Quick Start

```bash
afs chat run --model scawful-echo
afs chat run --router oracle
afs chat run --provider studio --model gemini-3-flash-preview
afs chat run --provider openai --model gpt-5.2
afs chat run --provider anthropic --model opus-4.5
afs chat run --router cloud
```

## Local llama.cpp proxies (llama-harness)

The llama-harness project runs llama.cpp servers behind an Ollama-compatible shim.
Point the chat harness at the proxy by setting `OLLAMA_HOST`:

```bash
export OLLAMA_HOST=http://127.0.0.1:11437
afs chat run --router oracle

export OLLAMA_HOST=http://127.0.0.1:11439
afs chat run --router avatar

# Avatar router (auto-picks experts). Requires avatar_router.py running.
export OLLAMA_HOST=http://127.0.0.1:11441
afs chat run --model avatar
```

## Listing

```bash
afs chat list-models --registry
afs chat list-models --provider ollama
afs chat list-models --provider studio
afs chat list-models --provider openai
afs chat list-models --provider anthropic
afs chat list-routers
```

## Tools (Optional)

```bash
afs chat run --model nayru --tools
# In the REPL:
/tools
/tool route_to_expert {"expert":"din","prompt":"optimize this"}
```

## Thinking Tiers

```bash
afs chat run --provider openai --model gpt-5.2 --thinking-tier high
afs chat run --provider anthropic --model opus-4.5 --thinking-tier medium
```

Notes:
- `--thinking-tier` maps to provider-specific parameters. Verify expected behavior per API.

## Registry Notes

- Model aliases map to provider model IDs.
- Routers are keyword or ensemble strategies.
- Use `--registry-path` to point at an alternate registry file.
