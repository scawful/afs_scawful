@echo off
setlocal
if "%AFS_WSL_DISTRO%"=="" set "AFS_WSL_DISTRO=Ubuntu"
wsl -d "%AFS_WSL_DISTRO%" -- /mnt/d/src/training/scripts/wsl_run_5090_benchmark.sh %*
