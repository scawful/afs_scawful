#!/bin/bash
# Launch Veran PEFT eval on the Windows host and stage eval assets.

set -euo pipefail

HOST="${HOST:-medical-mechanica}"
TASK_NAME="${TASK_NAME:-AFS_Veran_v1_Eval}"
MODEL_NAME="${MODEL_NAME:-Qwen/Qwen2.5-Coder-7B-Instruct}"
ADAPTER_PATH="${ADAPTER_PATH:-D:\models\checkpoints\veran_v1_peft_20260210_224921\lora_adapters}"
WAIT_FOR_ADAPTER=true
WAIT_SECONDS="${WAIT_SECONDS:-60}"

LOCAL_ROOT="${LOCAL_ROOT:-$HOME/src/lab}"
LOCAL_REPO="${LOCAL_REPO:-$HOME/src/lab/afs-scawful}"
LOCAL_EVAL_SCRIPT="${LOCAL_EVAL_SCRIPT:-$LOCAL_REPO/scripts/eval_veran_peft.py}"
LOCAL_QUICK="${LOCAL_QUICK:-$LOCAL_ROOT/afs/training_data/veran_v1_eval_quick_keywords.jsonl}"
LOCAL_HOLDOUT="${LOCAL_HOLDOUT:-$LOCAL_ROOT/afs/training_data/veran_v1_eval_holdout.jsonl}"

REMOTE_DIR="D:/afs_training/evals/veran_v1"
REMOTE_SCRIPT="$REMOTE_DIR/eval_veran_peft.py"
REMOTE_QUICK="$REMOTE_DIR/veran_v1_eval_quick_keywords.jsonl"
REMOTE_HOLDOUT="$REMOTE_DIR/veran_v1_eval_holdout.jsonl"
REMOTE_RUNNER="D:/afs_training/scripts/run_veran_v1_eval.cmd"

usage() {
  cat <<USAGE
Usage: $0 [options]

Options:
  --host HOST                 Windows SSH host (default: medical-mechanica)
  --task-name NAME            Scheduled task name (default: AFS_Veran_v1_Eval)
  --model-name NAME           Base model name for adapter eval
  --adapter-path PATH         Windows adapter dir (contains adapter_model.safetensors)
  --wait-seconds N            Poll interval while waiting for adapter (default: 60)
  --no-wait-for-adapter       Start eval immediately
  --local-eval-script PATH    Local eval script path to sync
  --local-quick PATH          Local quick eval JSONL path
  --local-holdout PATH        Local holdout eval JSONL path
  -h, --help                  Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="$2"
      shift 2
      ;;
    --task-name)
      TASK_NAME="$2"
      shift 2
      ;;
    --model-name)
      MODEL_NAME="$2"
      shift 2
      ;;
    --adapter-path)
      ADAPTER_PATH="$2"
      shift 2
      ;;
    --wait-seconds)
      WAIT_SECONDS="$2"
      shift 2
      ;;
    --no-wait-for-adapter)
      WAIT_FOR_ADAPTER=false
      shift
      ;;
    --local-eval-script)
      LOCAL_EVAL_SCRIPT="$2"
      shift 2
      ;;
    --local-quick)
      LOCAL_QUICK="$2"
      shift 2
      ;;
    --local-holdout)
      LOCAL_HOLDOUT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

for path in "$LOCAL_EVAL_SCRIPT" "$LOCAL_QUICK" "$LOCAL_HOLDOUT"; do
  if [[ ! -f "$path" ]]; then
    echo "Missing local file: $path" >&2
    exit 1
  fi
done

echo "[*] Host: $HOST"
echo "[*] Task: $TASK_NAME"
echo "[*] Adapter path: $ADAPTER_PATH"
echo "[*] Staging eval assets..."

ssh "$HOST" "powershell -NoProfile -Command \"New-Item -ItemType Directory -Force -Path '$REMOTE_DIR','D:\afs_training\scripts','D:\afs_training\logs' | Out-Null\""

scp "$LOCAL_EVAL_SCRIPT" "$HOST:$REMOTE_SCRIPT"
scp "$LOCAL_QUICK" "$HOST:$REMOTE_QUICK"
scp "$LOCAL_HOLDOUT" "$HOST:$REMOTE_HOLDOUT"

cat <<PS | ssh "$HOST" powershell -NoProfile -
\$ErrorActionPreference = "Stop"
\$task = "$TASK_NAME"
\$model = "$MODEL_NAME"
\$adapter = "$ADAPTER_PATH"
\$wait = "$WAIT_FOR_ADAPTER"
\$waitSeconds = "$WAIT_SECONDS"
\$runner = "$REMOTE_RUNNER"
\$evalScript = "$REMOTE_SCRIPT"
\$quickFile = "$REMOTE_QUICK"
\$holdoutFile = "$REMOTE_HOLDOUT"
\$ts = Get-Date -Format yyyyMMdd_HHmmss
\$quickOut = "D:\afs_training\evals\veran_v1\results_quick_\$ts.json"
\$holdoutOut = "D:\afs_training\evals\veran_v1\results_holdout_\$ts.json"
\$logOut = "D:\afs_training\logs\veran_v1_eval_\$ts.log"
\$logErr = "D:\afs_training\logs\veran_v1_eval_\$ts.err.log"

\$runnerBody = @"
@echo off
setlocal enabledelayedexpansion
set ADAPTER=\$adapter
if /I "\$wait"=="true" goto wait_for_adapter
goto run_eval

:wait_for_adapter
if exist "!ADAPTER!\adapter_model.safetensors" goto run_eval
echo Waiting for adapter at !ADAPTER! >> "\$logOut"
timeout /t \$waitSeconds /nobreak >nul
goto wait_for_adapter

:run_eval
python "\$evalScript" --model-name "\$model" --adapter-path "!ADAPTER!" --eval-file "\$quickFile" --output "\$quickOut" --max-new-tokens 180 --limit 12 >> "\$logOut" 2>> "\$logErr"
python "\$evalScript" --model-name "\$model" --adapter-path "!ADAPTER!" --eval-file "\$holdoutFile" --output "\$holdoutOut" --max-new-tokens 220 >> "\$logOut" 2>> "\$logErr"
echo Eval complete >> "\$logOut"
"@
Set-Content -Path \$runner -Value \$runnerBody -Encoding ASCII

schtasks /create /tn \$task /tr "cmd /c \$runner" /sc once /st 00:00 /sd 01/01/2026 /f | Out-Null
schtasks /run /tn \$task | Out-Null

Write-Output "TASK=\$task"
Write-Output "RUNNER=\$runner"
Write-Output "LOG=\$logOut"
Write-Output "ERR=\$logErr"
Write-Output "QUICK_OUT=\$quickOut"
Write-Output "HOLDOUT_OUT=\$holdoutOut"
PS

echo "[*] Eval task submitted."
echo "[*] Pull latest outputs with: $LOCAL_REPO/scripts/pull_veran_eval_results.sh --host $HOST"
