@echo off
set LOG_DIR=D:\afs_training\logs

if "%~1"=="" (
  powershell -NoProfile -File D:\afs_training\scripts\afs_tail.ps1 "%LOG_DIR%\training_autocomplete.log" 20
  powershell -NoProfile -File D:\afs_training\scripts\afs_tail.ps1 "%LOG_DIR%\training_fim_autocomplete.log" 20
  exit /b 0
)

powershell -NoProfile -File D:\afs_training\scripts\afs_tail.ps1 "%~1" 80
