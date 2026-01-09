# Zelda Expert Models (Triforce MoE)

Fine-tuned models for 65816 assembly tasks, named after Oracle of Ages/Seasons characters.

## Remote Deployment (MECHANICA via Tunnel)

Models are hosted on MECHANICA (Windows GPU). The Mac uses an SSH tunnel for access;
do not install or cache Ollama models locally on macOS.

| Model | Version | Size | Purpose |
|-------|---------|------|---------|
| din-v2 | v2 | 4.7 GB | Optimization expert - reduces cycle counts, improves efficiency |
| nayru-v5 | v5 | 4.8 GB | Code generation - writes 65816 assembly from descriptions |
| veran-v1 | v1 | 4.7 GB | Code analysis - explains routines, documents functionality |
| farore-v5 | v5 | 8.1 GB | Debugging expert - identifies bugs, suggests fixes (84% eval score) |
| majora-v2 | v2 | 8.1 GB | Performance optimization - cycle counting, register optimization |

### Usage (Remote via Tunnel)

```bash
export OLLAMA_HOST=http://localhost:11435
ollama run din-v2 "Optimize this loop: ..."
ollama run nayru-v5 "Write a DMA transfer routine"
ollama run veran-v1 "Explain this code: ..."
ollama run farore-v5 "Debug this routine that crashes: ..."
ollama run majora-v2 "Count cycles in this routine: ..."
```

## Windows Archive (MECHANICA)

Full version history available on Windows storage (D: drive):

**Mount:** `~/Mounts/mm-d/` (use `mounts mm`; prefer `scp` for transfers)

**Path:** `~/Mounts/mm-d/Ollama/models/`

### Available Versions

| Model | Versions | Location |
|-------|----------|----------|
| Din | v1, v2, v3, v3-fewshot | `manifests/registry.ollama.ai/library/din-*/latest` |
| Nayru | v4, v5 | `manifests/registry.ollama.ai/library/nayru-*/latest` |
| Farore | v1, v4, v5 | `manifests/registry.ollama.ai/library/farore-*/latest` |
| Majora | v2 | `manifests/registry.ollama.ai/library/majora-*/latest` |

### Version Notes

- **Din v1-v3:** Progressive improvements in optimization quality
- **Din v3-fewshot:** Trained with few-shot examples
- **Nayru v4-v5:** v5 has improved code generation coherence
- **Veran:** Only v1 trained so far (from veran-lora-fused-v2 adapters)
- **Farore v1-v5:** v5 is the current production version (84% eval score on debugging benchmarks)
- **Majora v2:** Performance optimization specialist (cycle counting, register optimization)

## Local Project Assets

This repo keeps adapters, Modelfiles, and training data only (no GGUFs or Ollama blobs on Mac).

```
~/src/lab/afs/models/
├── din-lora-adapters-v2/
├── veran-lora-adapters/
├── nayru/
└── *.Modelfile
```

**Note:** Ollama blobs and GGUF binaries live on MECHANICA (`D:\`).

## Deployment Scripts

Modelfiles for creating Ollama models from GGUF:

```
~/src/lab/afs/scripts/
├── Modelfile.din              # din-v2 deployment config
└── Modelfile.veran            # veran-v1 deployment config
```

### Deploy from GGUF

```bash
cd ~/src/lab/afs/scripts
ollama create din-v2 -f Modelfile.din
ollama create veran-v1 -f Modelfile.veran
```

## Accessing Remote Models

To inspect manifests or logs, browse `~/Mounts/mm-d/Ollama/models/` or use `scp`
to copy small metadata. Avoid copying blobs to macOS; keep `~/.ollama` empty.

## Training Source

All models fine-tuned using MLX LoRA on Qwen2.5 base:

| Model | Base Model | Training |
|-------|------------|----------|
| Din | Qwen2.5-7B-Instruct | din-lora-adapters-v2 |
| Nayru | Qwen2.5-Coder-7B | (adapters on Windows) |
| Veran | Qwen2.5-7B-Instruct | veran-lora-fused-v2 |
| Farore | Qwen2.5-Coder-7B-Instruct | farore-v5 (70 curated samples) |
| Majora | Qwen2.5-Coder-7B-Instruct | majora-v2 (202 performance optimization samples) |

## Alternative Model Serving Backends

While Ollama is the primary serving mechanism, AFS is compatible with any OpenAI-compatible API.

### 1. LM Studio
LM Studio is a GUI-based local model server.
- **Port:** Default `1234`
- **Setup:** Launch LM Studio, load a model, and start the "Local Server".
- **AFS Config:**
  ```toml
  [orchestrator.default_agents]
  name = "onox"
  backend = "http://localhost:1234/v1"
  model = "your-model-id"
  ```

### 2. GGUF (via llama-cpp-python)
For lightweight serving without Ollama, use the `llama-cpp-python` server.
- **Installation:**
  ```bash
  # With macOS GPU acceleration (Metal)
  CMAKE_ARGS="-DGGML_METAL=on" pip install llama-cpp-python[server]
  ```
- **Service Command:**
  ```bash
  python3 -m llama_cpp.server --model models/your-model.gguf --port 8000
  ```

### 3. MLX (Apple Silicon Native)
For maximum efficiency on Mac during development or training:
- **Installation:**
  ```bash
  pip install mlx-lm
  ```
- **Service Command:**
  ```bash
  python3 -m mlx_lm.server --model models/fused-model-directory --port 8080
  ```
- **Usage with AFS:** Point your agent backend to `http://localhost:8080/v1`.

## Conversion Pipeline
... (rest of the file)

For MLX models with pre-quantization:

```bash
# 1. Dequantize MLX → bf16
python3 -m mlx_lm convert --hf-path <fused-model> --mlx-path <output> -d --dtype bfloat16

# 2. Convert to GGUF f16
python3 llama.cpp/convert_hf_to_gguf.py <bf16-model> --outtype f16 --outfile model-f16.gguf

# 3. Quantize to Q4_K_M
./llama.cpp/build/bin/llama-quantize model-f16.gguf model-q4_k_m.gguf Q4_K_M

# 4. Clean up intermediate files immediately to save storage
rm -rf <bf16-model> model-f16.gguf
```

**Important:** Delete intermediate files immediately after conversion to save storage.
