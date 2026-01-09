#!/bin/bash
# 02_launch_training.sh
# Launch all training jobs in parallel

set -e

# Configuration - Correct ports and hosts
VAST_PORT_1=${VAST_PORT_1:-29366}  # ssh6.vast.ai - Veran v4
VAST_PORT_2=${VAST_PORT_2:-29366}  # ssh8.vast.ai - Farore v4 + Agahnim v2
VAST_PORT_3=${VAST_PORT_3:-29368}  # ssh9.vast.ai - Majora v2

echo "========================================"
echo "  PARALLEL TRAINING LAUNCH"
echo "========================================"
echo "Start time: $(date)"
echo ""

# Vast.ai Instance 1 - Veran v4
echo "[1/3] Launching Veran v4 on Instance 1 (ssh6)..."
echo "  • 2,479 samples"
echo "  • 3 epochs"
echo "  • Est. 4.5 hours"
ssh -p $VAST_PORT_1 root@ssh6.vast.ai << 'EOF'
cd /workspace
nohup bash train_model.sh veran-v4 veran_v4_training.jsonl 3 > logs/veran_v4_training.log 2>&1 &
echo $! > logs/veran_v4.pid
echo "  ✓ Veran v4 training started (PID: $(cat logs/veran_v4.pid))"
EOF

# Vast.ai Instance 2 - Farore v4 + Agahnim v2 (queued)
echo "[2/3] Launching Farore v4 on Instance 2 (ssh8)..."
echo "  • 1,562 samples"
echo "  • 3 epochs"
echo "  • Est. 3.0 hours"
echo "  • Agahnim v2 queued (auto-start after Farore)"
ssh -p $VAST_PORT_2 root@ssh8.vast.ai << 'EOF'
cd /workspace

# Start Farore v4
nohup bash train_model.sh farore-v4 farore_v4_training.jsonl 3 > logs/farore_v4_training.log 2>&1 &
echo $! > logs/farore_v4.pid
echo "  ✓ Farore v4 training started (PID: $(cat logs/farore_v4.pid))"

# Queue Agahnim v2 to start after Farore completes
nohup bash -c '
    while kill -0 $(cat logs/farore_v4.pid) 2>/dev/null; do sleep 60; done
    echo "Farore v4 complete. Starting Agahnim v2..."
    bash train_model.sh agahnim-v2 agahnim_v2_training.jsonl 3 > logs/agahnim_v2_training.log 2>&1
' > logs/agahnim_queue.log 2>&1 &
echo "  ✓ Agahnim v2 queued (starts after Farore)"
EOF

# Vast.ai Instance 3 - Majora v2 (4 epochs for large dataset)
echo "[3/3] Launching Majora v2 on Instance 3 (ssh9)..."
echo "  • 6,411 samples"
echo "  • 4 epochs (large dataset benefit)"
echo "  • Est. 10.5 hours"
ssh -p $VAST_PORT_3 root@ssh9.vast.ai << 'EOF'
cd /workspace
nohup bash train_model.sh majora-v2 majora_v2_training.jsonl 4 > logs/majora_v2_training.log 2>&1 &
echo $! > logs/majora_v2.pid
echo "  ✓ Majora v2 training started (PID: $(cat logs/majora_v2.pid))"
EOF

echo ""
echo "========================================"
echo "  ✓ ALL TRAINING JOBS LAUNCHED"
echo "========================================"
echo ""
echo "Monitor progress:"
echo "  ./03_monitor_training.sh"
echo ""
echo "Estimated completion:"
echo "  Farore v4:  T+3h   ($(date -v+3H '+%H:%M' 2>/dev/null))"
echo "  Veran v4:   T+4.5h ($(date -v+4H30M '+%H:%M' 2>/dev/null))"
echo "  Agahnim v2: T+4.5h (queued after Farore)"
echo "  Majora v2:  T+10.5h ($(date -v+10H30M '+%H:%M' 2>/dev/null)) ★ Longest"
echo ""
