@echo off
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
echo Disk:
powershell -NoProfile -Command "Get-PSDrive -PSProvider FileSystem | Select-Object Name,Free,Used,DisplayRoot | Format-Table -AutoSize"
echo.
echo Logs:
powershell -NoProfile -Command "if (Test-Path 'D:\\afs_training\\logs\\training_autocomplete.log') { Write-Host '--- training_autocomplete.log'; Get-Content -Tail 8 'D:\\afs_training\\logs\\training_autocomplete.log' } else { Write-Host 'missing training_autocomplete.log' }"
powershell -NoProfile -Command "if (Test-Path 'D:\\afs_training\\logs\\training_fim_autocomplete.log') { Write-Host '--- training_fim_autocomplete.log'; Get-Content -Tail 8 'D:\\afs_training\\logs\\training_fim_autocomplete.log' } else { Write-Host 'missing training_fim_autocomplete.log' }"
