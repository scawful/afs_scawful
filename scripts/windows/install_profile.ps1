param(
    [string]$ProfilePath = $PROFILE
)

$line = ". 'D:\afs_training\scripts\afs_profile.ps1'"

if (-not (Test-Path $ProfilePath)) {
    New-Item -ItemType File -Path $ProfilePath -Force | Out-Null
}

$content = Get-Content -Path $ProfilePath -Raw -ErrorAction SilentlyContinue
if ($content -notmatch [regex]::Escape($line)) {
    Add-Content -Path $ProfilePath -Value "`r`n$line`r`n"
    Write-Host "Updated PowerShell profile: $ProfilePath"
} else {
    Write-Host "PowerShell profile already configured: $ProfilePath"
}
