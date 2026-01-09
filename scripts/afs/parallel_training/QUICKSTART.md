# Parallel Training - Quick Start Guide

Train all 5 Triforce Expert models in 10.5 hours instead of 24 hours.

## Prerequisites

- [ ] Vast.ai account with credits
- [ ] `vastai` CLI installed (`pip install vastai`)
- [ ] Training data prepared (`~/src/lab/afs/training_data/combined/`)
- [ ] MECHANICA GPU available (optional, saves $2.25)

## Step-by-Step

### 1. Launch Vast.ai Instances (5 minutes)

```bash
# Find cheapest 24GB instances
vastai search offers 'gpu_ram >= 24 reliability > 0.95' \
  --order 'dph_total' | head -10

# Launch 3 instances
vastai create instance <ID1> \
  --image pytorch/pytorch:2.1.0-cuda11.8-cudnn8-devel \
  --disk 50

vastai create instance <ID2> \
  --image pytorch/pytorch:2.1.0-cuda11.8-cudnn8-devel \
  --disk 50

vastai create instance <ID3> \
  --image pytorch/pytorch:2.1.0-cuda11.8-cudnn8-devel \
  --disk 50

# Note the SSH ports (e.g., 14998, 15234, 16789)
```

### 2. Setup Instances (10 minutes)

```bash
# Instance 1
ssh -p 14998 root@ssh1.vast.ai < 00_instance_setup.sh

# Instance 2
ssh -p 15234 root@ssh1.vast.ai < 00_instance_setup.sh

# Instance 3
ssh -p 16789 root@ssh1.vast.ai < 00_instance_setup.sh

# Check MECHANICA
ping mechanica.local  # Should respond
```

### 3. Configure Ports (1 minute)

```bash
# In current terminal
export VAST_PORT_1=14998
export VAST_PORT_2=15234
export VAST_PORT_3=16789
export MECHANICA_HOST="mechanica.local"  # Or IP
```

### 4. Upload Data (15 minutes)

```bash
./01_upload_data.sh

# Watch for "✓ All Data Uploaded"
```

### 5. Launch Training (2 minutes)

```bash
./02_launch_training.sh

# Should show:
# ✓ Majora v2 training started
# ✓ Veran v4 training started
# ✓ Nayru v8 training started
# ✓ Farore v4 training started
# ✓ Agahnim v2 queued
```

### 6. Monitor Progress

```bash
# In separate terminal/tmux
./03_monitor_training.sh

# Updates every 30 seconds
# Press Ctrl+C to exit
```

### 7. Wait for Completion

**Timeline:**
- ☕ **T+3h**: Farore v4 done, Agahnim v2 starts
- ☕ **T+4.5h**: Veran v4, Nayru v8, Agahnim v2 done
- 🍕 **T+10.5h**: Majora v2 done (COMPLETE!)

### 8. Download Results (30 minutes)

```bash
# Download all adapters
scp -r -P 14998 root@ssh1.vast.ai:/workspace/adapters/majora-v2 \
  ~/src/lab/afs/models/lora/

scp -r -P 15234 root@ssh1.vast.ai:/workspace/adapters/veran-v4 \
  ~/src/lab/afs/models/lora/

scp -r -P 16789 root@ssh1.vast.ai:/workspace/adapters/farore-v4 \
  ~/src/lab/afs/models/lora/

scp -r -P 16789 root@ssh1.vast.ai:/workspace/adapters/agahnim-v2 \
  ~/src/lab/afs/models/lora/

scp -r mechanica.local:/workspace/training/adapters/nayru-v8 \
  ~/src/lab/afs/models/lora/
```

### 9. Cleanup

```bash
# Destroy Vast.ai instances
vastai destroy instance <ID1>
vastai destroy instance <ID2>
vastai destroy instance <ID3>

# Cost: ~$10 total
```

## Next Steps

1. Convert adapters to GGUF format
2. Import to Ollama
3. Run benchmarks: `python3 evaluation/run_benchmarks.py --model <model> --suite all`
4. Generate reports
5. Iterate if scores < 0.80

## Troubleshooting

**"Cannot connect to instance"**
→ Wait 2-3 minutes for instance to fully boot

**"No such file or directory"**
→ Re-run setup script: `ssh -p <PORT> root@ssh1.vast.ai < 00_instance_setup.sh`

**"Out of memory"**
→ Edit `/workspace/train_model.sh`, set `batch_size=2`

**"Training stuck"**
→ Check logs: `ssh -p <PORT> root@ssh1.vast.ai tail -f /workspace/logs/<model>_training.log`

## Success Criteria

- [ ] All 5 models complete without errors
- [ ] Loss curves decrease smoothly (no NaN)
- [ ] Final loss < 1.0 for all models
- [ ] Benchmark scores ≥ 0.70 (acceptable), target 0.80+

## Estimated Costs

| Item | Cost |
|------|------|
| Vast.ai #1 (10.5h) | $5.25 |
| Vast.ai #2 (4.5h) | $2.25 |
| Vast.ai #3 (4.5h) | $2.25 |
| MECHANICA (free) | $0.00 |
| **Total** | **~$10** |

Worth it for 56% faster completion (10.5h vs 24h sequential)!

## Timeline Visualization

```
T+0h  ████████████ Majora v2 (Vast.ai #1) ███████████████████████████
      ████ Veran v4 (Vast.ai #2) █████████
      ████ Nayru v8 (MECHANICA) █████████
      ███ Farore v4 (Vast.ai #3) ████

T+3h                              ██ Agahnim v2 (Vast.ai #3) ███

T+10.5h                                                            ✓
```

**All models trained in parallel = massive time savings!**
