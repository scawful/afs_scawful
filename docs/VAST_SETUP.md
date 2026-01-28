# Vast AI Setup Guide

Status: Active
Last updated: 2026-01-03

## Scope

Local scripts for renting GPU instances on Vast using the `vastai` CLI:
- **Training**: Fine-tune models on A100/H100 GPUs
- **Inference**: Run Ollama with Zelda expert models for fast evaluation

## Prerequisites

- `VAST_API_KEY` set in your shell environment (do not store in repo).
- `vastai` CLI installed:

```bash
python3 -m pip install --user vastai
```

Optional (recommended):
- Add an SSH key to your Vast account:

```bash
vastai create ssh-key
vastai show ssh-keys
```

If you need to attach a key to a running instance:

```bash
vastai attach <instance_id> "ssh-rsa AAAA..."
```

## Scripts (local only)

Scripts live under `infra/vast/` (ignored by git):

- `infra/vast/vast_deploy.sh` — search + create instance
- `infra/vast/vast_monitor.sh` — show instance details, optional SSH
- `infra/vast/vast_destroy.sh` — destroy instance

## Monitoring + Alerting (AFS CLI)

These commands read instance metadata from `infra/vast/instances/<name>.json` (or `--metadata`).

```bash
python -m afs_scawful vast status --name zelda-16b
python -m afs_scawful vast check --name zelda-16b --alert
python -m afs_scawful vast watch --name zelda-16b --interval 60
python -m afs_scawful vast status --all
```

Optional flags:

```bash
python -m afs_scawful vast status --name zelda-16b --json
python -m afs_scawful vast status --name zelda-16b --write-index
python -m afs_scawful vast status --name zelda-16b --output ~/src/training/index/vast_status.json
```

Alert delivery uses the existing ntfy config in `config/budget.toml` or `NTFY_TOPIC`/`NTFY_SERVER`.
Idle/disk alert toggles respect `alert_on_idle_detection` and `alert_on_disk_warning`.

AFS Studio note: `vast_status.json` is written to the training index when using `--write-index`.
Unknown / needs verification: whether AFS Studio ingests this file automatically.

## Quick Start (Training - A100 80GB)

```bash
# Search + create instance (A100 80GB, 1 GPU)
./infra/vast/vast_deploy.sh --name zelda-16b --gpu A100 --vram 80 --num-gpus 1 --disk 200

# Monitor / SSH
./infra/vast/vast_monitor.sh --name zelda-16b
./infra/vast/vast_monitor.sh --name zelda-16b --ssh

# Destroy
./infra/vast/vast_destroy.sh --name zelda-16b
```

## Quick Start (Ollama Inference)

For running zelda_eval with GPU-accelerated expert models:

```bash
# Deploy Ollama instance (RTX 4090, 24GB - sufficient for 7B models)
./infra/vast/vast_deploy_ollama.sh zelda-ollama

# Wait 2-3 minutes for setup, then test connection
curl http://<SSH_HOST>:11434/api/tags

# Run evaluation with remote Ollama
export OLLAMA_HOST=http://<SSH_HOST>:11434
python -m afs_scawful.zelda_eval eval --expert veran --category knowledge_65816

# When done, destroy instance
./infra/vast/vast_destroy.sh --name zelda-ollama
```

### Ollama Instance Costs

| GPU | VRAM | ~Cost/hr | Best For |
|-----|------|----------|----------|
| RTX 4090 | 24GB | $0.30-0.50 | Single 7B model |
| RTX 3090 | 24GB | $0.20-0.35 | Single 7B model |
| A100 40GB | 40GB | $1.00-1.50 | Multiple 7B models |
| A100 80GB | 80GB | $1.50-2.50 | All experts + 16B |

For zelda_eval with 4x 7B experts, RTX 4090 is cost-effective since models are loaded on-demand.

## Query Notes

The `--query` string uses Vast CLI fields (example: `gpu_name`, `num_gpus`, `gpu_ram`).

Unknown / needs verification:
- Exact `gpu_name` strings for A100 80GB in current Vast inventory.
- Whether `gpu_ram` should be filtered via `gpu_ram` or `gpu_total_ram` for some offers.

## Training Bootstrap

The deploy script only provisions the instance. After SSH:

### Gated Model Access (Hugging Face)

For models like Gemma that require authentication, push your local HF token to the instance:

```bash
~/src/training/scripts/push_vast_hf_token.sh --host <host> --port <port>
```

Or use the training watcher helper with token passthrough:

```bash
~/src/training/scripts/run_vast_training_with_watch.sh \
  --hf-token-file ~/.cache/huggingface/token \
  ...
```

Do not store tokens in repo files.

1. Create training directories:

```bash
mkdir -p /opt/training/{models,checkpoints,logs,scripts,datasets}
```

2. Copy scripts:

```bash
scp -r ./infra/scripts/* root@<host>:/opt/training/scripts/
scp ./infra/scripts/train_peft.py root@<host>:/opt/training/train_peft.py
```

3. Install dependencies:

```bash
python3 -m venv /opt/training/venv
/opt/training/venv/bin/pip install --upgrade pip setuptools wheel
/opt/training/venv/bin/pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
/opt/training/venv/bin/pip install transformers>=4.44.0 datasets>=2.20.0 peft>=0.12.0 bitsandbytes>=0.43.0 accelerate>=0.32.0 sentencepiece protobuf huggingface-hub
```

4. Start training (example):

```bash
/opt/training/venv/bin/python /opt/training/train_peft.py \
  --model-name deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct \
  --data-dir /opt/training/datasets \
  --epochs 1
```

## Vast.ai CLI Reference

### Installation

```bash
pip install vastai
```

### Authentication

```bash
# Set API key (get from https://cloud.vast.ai/account/)
export VAST_API_KEY=your_key_here

# Or configure via CLI
vastai set api-key your_key_here
```

### SSH Key Setup

```bash
# Generate key if needed
ssh-keygen -t ed25519 -C "vast-ai"

# Add to Vast account
vastai create ssh-key

# View registered keys
vastai show ssh-keys
```

### Searching Offers

```bash
# Search for GPUs
vastai search offers "gpu_name=RTX_4090 num_gpus=1"
vastai search offers "gpu_name=A100 gpu_ram>=40"
vastai search offers "gpu_name=H100 num_gpus>=2"

# Filter by price
vastai search offers "dph_total<1.0 gpu_ram>=24"

# Sort by score (default) or price
vastai search offers --order "score-" "gpu_name=RTX_4090"
vastai search offers --order "dph_total" "gpu_name=RTX_4090"
```

### Managing Instances

```bash
# List your instances
vastai show instances

# Show instance details
vastai show instance <instance_id>
vastai show instance <instance_id> --raw  # JSON output

# Get SSH URL
vastai ssh-url <instance_id>

# Destroy instance
vastai destroy instance <instance_id>
```

### Creating Instances

```bash
# Create from offer ID
vastai create instance <offer_id> --image nvidia/cuda:12.1-base-ubuntu22.04 --disk 100

# With onstart script
vastai create instance <offer_id> --image nvidia/cuda:12.1-base-ubuntu22.04 \
  --disk 100 --onstart ./onstart.sh

# With port mapping (for Ollama)
vastai create instance <offer_id> --image nvidia/cuda:12.1-base-ubuntu22.04 \
  --disk 100 --env "-p 11434:11434"

# Enable SSH and direct connection
vastai create instance <offer_id> --ssh --direct
```

### Useful Filters

| Field | Description | Example |
|-------|-------------|---------|
| `gpu_name` | GPU model | `gpu_name=RTX_4090` |
| `num_gpus` | Number of GPUs | `num_gpus>=2` |
| `gpu_ram` | VRAM in GB | `gpu_ram>=24` |
| `dph_total` | Price per hour | `dph_total<0.50` |
| `inet_down` | Download speed | `inet_down>200` |
| `inet_up` | Upload speed | `inet_up>100` |
| `reliability` | Host reliability | `reliability>0.95` |
| `disk_space` | Available disk | `disk_space>=100` |

## Loading Custom Expert Models

After deploying Ollama, you may need to load custom Zelda expert models:

### From GGUF Files

```bash
# Copy model file to instance
scp -P <SSH_PORT> ./models/din-v2.gguf root@<SSH_HOST>:/opt/models/

# Create Modelfile
ssh -p <SSH_PORT> root@<SSH_HOST> 'cat > /opt/models/din-v2.Modelfile <<EOF
FROM /opt/models/din-v2.gguf
SYSTEM "You are Din, an expert in 65816 assembly optimization..."
PARAMETER temperature 0.5
PARAMETER num_ctx 4096
EOF'

# Create model in Ollama
ssh -p <SSH_PORT> root@<SSH_HOST> 'ollama create din-v2 -f /opt/models/din-v2.Modelfile'
```

### From Hugging Face (via llama.cpp conversion)

```bash
# On the Vast instance
pip install huggingface-hub llama-cpp-python

# Download and convert
python -c "
from huggingface_hub import snapshot_download
snapshot_download('your-org/din-v2', local_dir='/opt/models/din-v2-hf')
"

# Convert to GGUF (requires llama.cpp)
python llama.cpp/convert.py /opt/models/din-v2-hf --outfile /opt/models/din-v2.gguf
```

## Troubleshooting

### Ollama not responding

```bash
# Check service status
ssh -p <PORT> root@<HOST> 'systemctl status ollama'

# View logs
ssh -p <PORT> root@<HOST> 'journalctl -u ollama -f'

# Restart service
ssh -p <PORT> root@<HOST> 'systemctl restart ollama'
```

### GPU not detected

```bash
# Check NVIDIA driver
ssh -p <PORT> root@<HOST> 'nvidia-smi'

# Check CUDA
ssh -p <PORT> root@<HOST> 'nvcc --version'
```

### Port not accessible

Make sure the instance was created with `-p 11434:11434` and firewall allows it:

```bash
# Check listening ports
ssh -p <PORT> root@<HOST> 'netstat -tlpn | grep 11434'

# Test from instance itself
ssh -p <PORT> root@<HOST> 'curl localhost:11434/api/tags'
```
