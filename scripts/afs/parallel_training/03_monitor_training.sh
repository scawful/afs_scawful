#!/bin/bash
# 03_monitor_training.sh
# Real-time monitoring dashboard

# Configuration - Updated for actual instances
VAST_PORT_1=${VAST_PORT_1:-29366}  # ssh6.vast.ai - Veran v4
VAST_PORT_2=${VAST_PORT_2:-29366}  # ssh8.vast.ai - Farore v4 + Agahnim v2
VAST_PORT_3=${VAST_PORT_3:-29368}  # ssh9.vast.ai - Majora v2

while true; do
  clear
  echo "╔════════════════════════════════════════════════════════════╗"
  echo "║     TRIFORCE EXPERTS v4 - PARALLEL TRAINING STATUS        ║"
  echo "╚════════════════════════════════════════════════════════════╝"
  echo ""
  echo "Last updated: $(date '+%Y-%m-%d %H:%M:%S')"
  echo ""

  # Veran v4
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "💎 Veran v4 (Instance #1 - ssh6) - 2,479 samples, 3 epochs"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  ssh -p $VAST_PORT_1 root@ssh6.vast.ai \
    "tail -3 /workspace/logs/veran-v4_training.log 2>/dev/null | grep -E '^ *[0-9]+%' || echo '  Status: Loading or starting...'" 2>/dev/null
  echo ""

  # Farore v4
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "🐛 Farore v4 (Instance #2 - ssh8) - 1,562 samples, 3 epochs"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  ssh -p $VAST_PORT_2 root@ssh8.vast.ai \
    "tail -3 /workspace/logs/farore-v4_training.log 2>/dev/null | grep -E '^ *[0-9]+%' || echo '  Status: Loading or starting...'" 2>/dev/null
  echo ""

  # Agahnim v2 (queued)
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "🔧 Agahnim v2 (Instance #2 - Queued) - 518 samples, 3 epochs"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  ssh -p $VAST_PORT_2 root@ssh8.vast.ai \
    "tail -3 /workspace/logs/agahnim-v2_training.log 2>/dev/null | grep -E '^ *[0-9]+%' || echo '  Status: Queued (waiting for Farore v4)'" 2>/dev/null
  echo ""

  # Majora v2
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "🏆 Majora v2 (Instance #3 - ssh9) - 6,411 samples, 4 epochs"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  ssh -p $VAST_PORT_3 root@ssh9.vast.ai \
    "tail -3 /workspace/logs/majora-v2_training.log 2>/dev/null | grep -E '^ *[0-9]+%' || echo '  Status: Loading or starting...'" 2>/dev/null
  echo ""

  echo "╔════════════════════════════════════════════════════════════╗"
  echo "║  Press Ctrl+C to exit monitoring                          ║"
  echo "║  Updates every 30 seconds                                 ║"
  echo "╚════════════════════════════════════════════════════════════╝"

  sleep 30
done
