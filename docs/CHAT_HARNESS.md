# Chat Harness (AFS CLI)

Interactive chat for local Ollama models, custom routers, and cloud providers.
Registry defaults live in `config/chat_registry.toml`.

## Quick Start

```bash
afs chat run --model scawful-echo
afs chat run --router oracle
afs chat run --provider studio --model gemini-2.0-flash
```

## Listing

```bash
afs chat list-models --registry
afs chat list-models --provider ollama
afs chat list-routers
```

## Tools (Optional)

```bash
afs chat run --model nayru --tools
# In the REPL:
/tools
/tool route_to_expert {"expert":"din","prompt":"optimize this"}
```

## Registry Notes

- Model aliases map to provider model IDs.
- Routers are keyword or ensemble strategies.
- Use `--registry-path` to point at an alternate registry file.
