#!/bin/bash
# 01_upload_data.sh
# Upload training data to all instances

set -e

# Configuration - UPDATE THESE AFTER LAUNCHING INSTANCES
VAST_PORT_1=${VAST_PORT_1:-14998}  # Majora v2
VAST_PORT_2=${VAST_PORT_2:-15234}  # Veran v4
VAST_PORT_3=${VAST_PORT_3:-16789}  # Farore v4 + Agahnim v2
MECHANICA_HOST=${MECHANICA_HOST:-"mechanica.local"}

DATA_DIR="$HOME/src/lab/afs/training_data/combined"

echo "========================================"
echo "  Uploading Training Data"
echo "========================================"
echo "Data directory: $DATA_DIR"
echo ""

# Check data files exist
for file in majora_v2_training.jsonl veran_v4_training.jsonl nayru_v8_training.jsonl farore_v4_training.jsonl agahnim_v2_training.jsonl; do
    if [ ! -f "$DATA_DIR/$file" ]; then
        echo "Error: $DATA_DIR/$file not found"
        exit 1
    fi
done

echo "All data files found ✓"
echo ""

# Upload in parallel
echo "[1/4] Uploading Veran v4 (2,479 samples, 6.4M) to Vast.ai #1 (ssh6)..."
scp -P $VAST_PORT_1 \
  "$DATA_DIR/veran_v4_training.jsonl" \
  root@ssh6.vast.ai:/workspace/data/ &
PID1=$!

echo "[2/4] Uploading Farore v4 & Agahnim v2 to Vast.ai #2 (ssh8)..."
scp -P $VAST_PORT_2 \
  "$DATA_DIR/farore_v4_training.jsonl" \
  "$DATA_DIR/agahnim_v2_training.jsonl" \
  root@ssh8.vast.ai:/workspace/data/ &
PID2=$!

echo "[3/4] Uploading Majora v2 (6,411 samples, 15.1M) to Vast.ai #3 (ssh9)..."
scp -P $VAST_PORT_3 \
  "$DATA_DIR/majora_v2_training.jsonl" \
  root@ssh9.vast.ai:/workspace/data/ &
PID3=$!

echo "[4/4] Skipping MECHANICA (Nayru v8 - will train on 4th instance later)..."
PID4=""

# Wait for all uploads
echo ""
echo "Waiting for uploads to complete..."
wait $PID1 && echo "  ✓ Veran v4 upload complete"
wait $PID2 && echo "  ✓ Farore v4 & Agahnim v2 upload complete"
wait $PID3 && echo "  ✓ Majora v2 upload complete"

echo ""
echo "========================================"
echo "  ✓ All Data Uploaded"
echo "========================================"
echo ""
echo "Next: ./02_launch_training.sh"
