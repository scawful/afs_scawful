@echo off
echo === AFS Windows Helper Commands ===
echo Location: D:\afs_training\scripts
echo.
echo Status:
echo   afs_status.cmd
echo.
echo Logs (tail):
echo   afs_logs.cmd
echo   powershell -NoProfile -File D:\afs_training\scripts\afs_tail.ps1 D:\afs_training\logs\training_autocomplete.log
echo.
echo Audit:
echo   powershell -NoProfile -File D:\afs_training\scripts\afs_audit.ps1
echo.
echo SRC setup:
echo   powershell -NoProfile -File D:\afs_training\scripts\afs_setup_src.ps1
echo   powershell -NoProfile -File D:\afs_training\scripts\afs_setup_wsl.ps1
echo.
echo Profile helpers:
echo   powershell -NoProfile -File D:\afs_training\scripts\install_profile.ps1
echo   powershell -NoProfile -File D:\afs_training\scripts\install_hostd_startup.ps1
echo   powershell -NoProfile -File D:\afs_training\scripts\install_hostd_startup.ps1 -Mode status
echo.
echo Training task:
echo   schtasks /query /tn AFS_Autocomplete_Train
echo   schtasks /end /tn AFS_Autocomplete_Train
echo.
echo GPU:
echo   nvidia-smi
echo.
echo WSL ML helpers:
echo   set AFS_WSL_DISTRO=Ubuntu
echo   afs_vllm.cmd start
echo   afs_vllm.cmd stop
echo   afs_vllm.cmd status
echo   afs_stage_image_model.cmd --model-id segmind/SSD-1B
echo   afs_benchmark_5090.cmd run
