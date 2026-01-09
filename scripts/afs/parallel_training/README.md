# Parallel Training Scripts

Orchestration scripts for training 5 Triforce Expert models simultaneously across multiple Vast.ai instances + local MECHANICA GPU.

## Quick Start

### 1. Launch Vast.ai Instances

```bash
# Search for available instances
vastai search offers 'gpu_ram >= 24 reliability > 0.95 inet_down > 100' | head -10

# Launch 3 instances (24GB VRAM each)
vastai create instance <ID1> --image pytorch/pytorch:2.1.0-cuda11.8-cudnn8-devel --disk 50
vastai create instance <ID2> --image pytorch/pytorch:2.1.0-cuda11.8-cudnn8-devel --disk 50
vastai create instance <ID3> --image pytorch/pytorch:2.1.0-cuda11.8-cudnn8-devel --disk 50

# Note the SSH ports for each instance
```

### 2. Setup Each Instance

```bash
# SSH into each instance and run setup
ssh -p <PORT> root@ssh1.vast.ai < 00_instance_setup.sh

# Repeat for all 3 instances
```

### 3. Configure Ports

Edit the port numbers in each script:

```bash
export VAST_PORT_1=14998  # Instance 1 (Majora v2)
export VAST_PORT_2=15234  # Instance 2 (Veran v4)
export VAST_PORT_3=16789  # Instance 3 (Farore v4 + Agahnim v2)
export MECHANICA_HOST="mechanica.local"  # Or IP address
```

### 4. Upload Training Data

```bash
./01_upload_data.sh
```

### 5. Launch Training

```bash
./02_launch_training.sh
```

### 6. Monitor Progress

```bash
./03_monitor_training.sh
```

## Training Timeline

| Model | Instance | Start | Duration | Complete |
|-------|----------|-------|----------|----------|
| Majora v2 | Vast.ai #1 | T+0 | 10.5h | T+10.5h |
| Veran v4 | Vast.ai #2 | T+0 | 4.5h | T+4.5h |
| Nayru v8 | MECHANICA | T+0 | 4.5h | T+4.5h |
| Farore v4 | Vast.ai #3 | T+0 | 3.0h | T+3h |
| Agahnim v2 | Vast.ai #3 | T+3h | 1.5h | T+4.5h |

**Total wallclock time**: ~10.5 hours (vs 24 hours sequential)

## Cost Estimate

- Vast.ai #1 (Majora): 10.5h × $0.50/h = $5.25
- Vast.ai #2 (Veran): 4.5h × $0.50/h = $2.25
- Vast.ai #3 (Farore + Agahnim): 4.5h × $0.50/h = $2.25
- MECHANICA (Nayru): Free (local GPU)

**Total**: ~$10 (worth it for 56% time reduction)

## Scripts Overview

| Script | Purpose |
|--------|---------|
| `00_instance_setup.sh` | Run on each Vast.ai instance to install deps |
| `01_upload_data.sh` | Upload training data to all instances |
| `02_launch_training.sh` | Start all training jobs in parallel |
| `03_monitor_training.sh` | Real-time monitoring dashboard |

## Monitoring Output Example

```
╔════════════════════════════════════════════════════════════╗
║     TRIFORCE EXPERTS v4 - PARALLEL TRAINING STATUS        ║
╚════════════════════════════════════════════════════════════╝

🏆 Majora v2 (Vast.ai #1) - 6,411 samples, 4 epochs
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Step 1000/6411 | Loss: 0.823 | LR: 0.00028
  Epoch 2/4 | ETA: 7.2h

💎 Veran v4 (Vast.ai #2) - 2,479 samples, 3 epochs
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Step 1850/2479 | Loss: 0.645 | LR: 0.00015
  Epoch 3/3 | ETA: 1.8h

...
```

## Troubleshooting

### Instance won't connect
```bash
# Check instance status
vastai show instances

# Restart instance
vastai stop instance <ID>
vastai start instance <ID>
```

### Out of memory
```bash
# Reduce batch size in train_model.sh
per_device_train_batch_size=2  # Instead of 4
gradient_accumulation_steps=8  # Maintain effective batch
```

### Training diverges (NaN loss)
```bash
# Resume from last checkpoint
# Checkpoints saved every 500 steps in /workspace/adapters/<model>/checkpoint-XXX
```

### Kill training job
```bash
ssh -p <PORT> root@ssh1.vast.ai
kill $(cat /workspace/logs/<model>.pid)
```

## Post-Training

After all models complete:

1. **Download adapters**: `scp -r -P <PORT> root@ssh1.vast.ai:/workspace/adapters/<model> ~/src/lab/afs/models/lora/`
2. **Convert to GGUF**: Use merge/convert scripts on Vast.ai instance
3. **Import to Ollama**: `ollama create <model> -f Modelfile`
4. **Run benchmarks**: `python3 evaluation/run_benchmarks.py --model <model> --suite all`

## Resource Cleanup

```bash
# Destroy instances when done
vastai destroy instance <ID1>
vastai destroy instance <ID2>
vastai destroy instance <ID3>
```

## Support

Issues? Check:
- `/workspace/logs/<model>_training.log` on each instance
- `PARALLEL_TRAINING_STRATEGY.md` for detailed documentation
- Vast.ai dashboard for instance health
