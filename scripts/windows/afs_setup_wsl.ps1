param(
    [string]$Distro = "Ubuntu",
    [string]$SrcRoot = "D:\src",
    [string]$TrainingRoot = "D:\src\training",
    [string]$Memory = "",
    [int]$Processors = 0,
    [string]$Swap = "16GB",
    [switch]$SkipPackageInstall,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$InformationPreference = "SilentlyContinue"

function Write-Info {
    param([string]$Message)
    Write-Host "[afs_setup_wsl] $Message"
}

function Get-LogicalCpuCount {
    $cs = Get-CimInstance Win32_ComputerSystem
    if ($cs.NumberOfLogicalProcessors) {
        return [int]$cs.NumberOfLogicalProcessors
    }

    $sum = (Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum
    if ($sum) {
        return [int]$sum
    }
    return 4
}

function Ensure-Dir {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Get-InstalledDistros {
    $raw = & wsl.exe -l -q 2>&1 | ForEach-Object { $_ -replace "`0", "" }
    return @($raw | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

function Get-DistroVersion {
    param([string]$Name)
    $rows = & wsl.exe -l -v 2>&1 | ForEach-Object { $_ -replace "`0", "" }
    foreach ($row in $rows) {
        if ($row -match "^\s*\*?\s*$([regex]::Escape($Name))\s+\S+\s+(\d+)\s*$") {
            return [int]$Matches[1]
        }
    }
    return $null
}

function Invoke-WSLRoot {
    param([string]$Command)
    & wsl.exe -d $Distro -u root -- bash -lc $Command
    if ($LASTEXITCODE -ne 0) {
        throw "WSL command failed: $Command"
    }
}

function Write-WSLFile {
    param(
        [string]$Path,
        [string]$Content,
        [string]$Mode = "644"
    )

    $dir = Split-Path -Path $Path -Parent
    $encoded = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($Content))
    Invoke-WSLRoot "mkdir -p '$dir' && printf '%s' '$encoded' | base64 -d > '$Path' && chmod $Mode '$Path'"
}

function Set-ManagedFile {
    param(
        [string]$Path,
        [string]$Content,
        [switch]$ForceWrite
    )

    $marker = "Managed by afs_setup_wsl.ps1"
    $shouldWrite = $true

    if (Test-Path $Path) {
        $existing = Get-Content -Raw $Path
        if ($existing -eq $Content) {
            $shouldWrite = $false
        } elseif (($existing -notmatch [regex]::Escape($marker)) -and (-not $ForceWrite)) {
            Write-Info "Leaving existing unmanaged file unchanged: $Path"
            $shouldWrite = $false
        } else {
            Copy-Item -Path $Path -Destination "${Path}.bak.$((Get-Date).ToString('yyyyMMdd_HHmmss'))"
        }
    }

    if ($shouldWrite) {
        Set-Content -Path $Path -Value $Content -Encoding ascii
        Write-Info "Wrote managed file: $Path"
    }
}

$SrcRoot = $SrcRoot.Trim("'").Trim('"')
$TrainingRoot = $TrainingRoot.Trim("'").Trim('"')
$Distro = $Distro.Trim("'").Trim('"')

Ensure-Dir $SrcRoot
Ensure-Dir $TrainingRoot
Ensure-Dir (Join-Path $TrainingRoot "logs")
Ensure-Dir (Join-Path $TrainingRoot "output")
Ensure-Dir (Join-Path $TrainingRoot "models")
Ensure-Dir (Join-Path $TrainingRoot "datasets")

$logical = Get-LogicalCpuCount
$totalMemoryGB = [math]::Floor((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
if ([string]::IsNullOrWhiteSpace($Memory)) {
    $recommendedMemory = [math]::Max(8, [math]::Floor($totalMemoryGB * 0.75))
    $Memory = "${recommendedMemory}GB"
}
if ($Processors -le 0) {
    $Processors = [math]::Max(4, [math]::Floor($logical * 0.75))
}

$wslConfig = @"
# Managed by afs_setup_wsl.ps1
[wsl2]
memory=$Memory
processors=$Processors
swap=$Swap

[experimental]
autoMemoryReclaim=gradual
"@

$wslConfigPath = Join-Path $env:USERPROFILE ".wslconfig"
Set-ManagedFile -Path $wslConfigPath -Content $wslConfig -ForceWrite:$Force

$distros = Get-InstalledDistros
if ($distros -notcontains $Distro) {
    Write-Info "Distro '$Distro' not installed. Attempting install."
    & wsl.exe --install -d $Distro --no-launch
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install WSL distro '$Distro'. If WSL itself is not enabled yet, rerun this from an elevated PowerShell and reboot if prompted."
    }
}

& wsl.exe --set-default-version 2
if ($LASTEXITCODE -ne 0) {
    throw "Failed to set WSL default version to 2"
}

$version = Get-DistroVersion -Name $Distro
if ($version -eq 1) {
    Write-Info "Converting '$Distro' from WSL1 to WSL2."
    & wsl.exe --set-version $Distro 2
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to convert '$Distro' to WSL2"
    }
}

$wslConf = @'
# Managed by afs_setup_wsl.ps1
[boot]
systemd=true

[automount]
mountFsTab=true
'@

$profileScript = @'
# Managed by afs_setup_wsl.ps1
export SRC_WIN=/mnt/d/src
export TRAIN_WIN=/mnt/d/src/training

alias csrc="cd /mnt/d/src"
alias ctrain="cd /mnt/d/src/training"

if command -v fdfind >/dev/null 2>&1 && ! command -v fd >/dev/null 2>&1; then
  alias fd="fdfind"
fi

if [ -f "$HOME/.config/afs/wsl-training.env.sh" ]; then
  source "$HOME/.config/afs/wsl-training.env.sh"
fi

if [ -f "$HOME/src/tools/ws/ws.sh" ]; then
  source "$HOME/src/tools/ws/ws.sh"
elif [ -f /mnt/d/src/tools/ws/ws.sh ]; then
  source /mnt/d/src/tools/ws/ws.sh
fi
'@

Write-WSLFile -Path "/etc/wsl.conf" -Content $wslConf
Write-WSLFile -Path "/etc/profile.d/afs-src.sh" -Content $profileScript

if (-not $SkipPackageInstall) {
    Write-Info "Installing base WSL packages inside '$Distro'."
    Invoke-WSLRoot "export DEBIAN_FRONTEND=noninteractive && apt-get update && apt-get install -y build-essential curl fd-find fzf git jq pkg-config python3 python3-pip python3-venv ripgrep rsync unzip zip"
}

& wsl.exe --shutdown
if ($LASTEXITCODE -ne 0) {
    throw "Failed to restart WSL after configuration changes"
}

$status = [ordered]@{
    distro = $Distro
    src_root = $SrcRoot
    training_root = $TrainingRoot
    wslconfig = $wslConfigPath
    memory = $Memory
    processors = $Processors
    swap = $Swap
    package_install_skipped = [bool]$SkipPackageInstall
    next_steps = @(
        "Launch $Distro once and complete first-login user setup if prompted.",
        "Inside WSL, run: /mnt/d/src/training/scripts/wsl_bootstrap_training.sh",
        "Use ~/src as the Linux-side symlink to /mnt/d/src after bootstrap."
    )
}

$status | ConvertTo-Json -Depth 4
