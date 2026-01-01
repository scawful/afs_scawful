param(
    [string]$Path = "D:\afs_training\logs\training_autocomplete.log",
    [int]$Tail = 80
)

if (-not (Test-Path $Path)) {
    Write-Host "Missing log: $Path"
    exit 1
}

Get-Content -Path $Path -Tail $Tail -Wait
