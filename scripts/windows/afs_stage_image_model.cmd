@echo off
setlocal
if "%AFS_WSL_DISTRO%"=="" set "AFS_WSL_DISTRO=Ubuntu"
wsl -d "%AFS_WSL_DISTRO%" -- bash -lc "exec \"${AFS_DIFFUSERS_PY:-$HOME/.venvs/diffusers/bin/python}\" /mnt/d/src/training/scripts/stage_diffusers_model.py \"$@\"" afs_stage_image_model %*
