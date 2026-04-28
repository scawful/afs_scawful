@echo off
setlocal
if "%AFS_WSL_DISTRO%"=="" set "AFS_WSL_DISTRO=Ubuntu"
echo === AFS Training Status ===
echo Host: %COMPUTERNAME%
echo Time: %DATE% %TIME%
echo.
echo Task:
schtasks /query /tn AFS_Autocomplete_Train
echo.
echo Python:
tasklist | findstr /i python
echo.
echo GPU:
nvidia-smi
echo.
echo WSL services:
if exist D:\src\training\scripts\wsl_vllm_service.sh (
  wsl -d "%AFS_WSL_DISTRO%" -- /mnt/d/src/training/scripts/wsl_vllm_service.sh status
) else (
  echo missing D:\src\training\scripts\wsl_vllm_service.sh
)
if exist D:\src\training\scripts\wsl_run_5090_benchmark.sh (
  wsl -d "%AFS_WSL_DISTRO%" -- /mnt/d/src/training/scripts/wsl_run_5090_benchmark.sh status
) else (
  echo missing D:\src\training\scripts\wsl_run_5090_benchmark.sh
)
echo.
echo Disk:
powershell -NoProfile -Command "Get-PSDrive -PSProvider FileSystem | Select-Object Name,Free,Used,DisplayRoot | Format-Table -AutoSize"
echo.
echo Logs:
powershell -NoProfile -Command "if (Test-Path 'D:\\afs_training\\logs\\training_autocomplete.log') { Write-Host '--- training_autocomplete.log'; Get-Content -Tail 8 'D:\\afs_training\\logs\\training_autocomplete.log' } else { Write-Host 'missing training_autocomplete.log' }"
powershell -NoProfile -Command "if (Test-Path 'D:\\afs_training\\logs\\training_fim_autocomplete.log') { Write-Host '--- training_fim_autocomplete.log'; Get-Content -Tail 8 'D:\\afs_training\\logs\\training_fim_autocomplete.log' } else { Write-Host 'missing training_fim_autocomplete.log' }"
powershell -NoProfile -Command "if (Test-Path 'D:\\afs_training\\logs\\scawfulbot-qwen3-8b-v1_8008.log') { Write-Host '--- scawfulbot-qwen3-8b-v1_8008.log'; Get-Content -Tail 8 'D:\\afs_training\\logs\\scawfulbot-qwen3-8b-v1_8008.log' } else { Write-Host 'missing scawfulbot-qwen3-8b-v1_8008.log' }"
powershell -NoProfile -Command "if (Test-Path 'D:\\afs_training\\logs\\qwen35-oracle-fast-v2-benchmark-5090.log') { Write-Host '--- qwen35-oracle-fast-v2-benchmark-5090.log'; Get-Content -Tail 8 'D:\\afs_training\\logs\\qwen35-oracle-fast-v2-benchmark-5090.log' } else { Write-Host 'missing qwen35-oracle-fast-v2-benchmark-5090.log' }"
