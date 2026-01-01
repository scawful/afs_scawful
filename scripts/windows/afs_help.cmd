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
echo.
echo Profile helpers:
echo   powershell -NoProfile -File D:\afs_training\scripts\install_profile.ps1
echo.
echo Training task:
echo   schtasks /query /tn AFS_Autocomplete_Train
echo   schtasks /end /tn AFS_Autocomplete_Train
echo.
echo GPU:
echo   nvidia-smi
