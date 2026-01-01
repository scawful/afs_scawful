param(
    [string]$OutputDir = "D:\afs_training\logs"
)

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $OutputDir "afs_audit_$timestamp.txt"
$lines = New-Object System.Collections.Generic.List[string]

function Add-Line {
    param([string]$Text)
    $lines.Add($Text)
}

Add-Line "=== AFS Windows Audit ==="
Add-Line "Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Add-Line "Host: $env:COMPUTERNAME"
Add-Line ""

$os = Get-CimInstance Win32_OperatingSystem
Add-Line "OS: $($os.Caption) ($($os.Version)) Build $($os.BuildNumber)"
Add-Line "Boot: $($os.LastBootUpTime)"
Add-Line ""

$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
Add-Line "CPU: $($cpu.Name)"
Add-Line "Cores: $($cpu.NumberOfCores) | Threads: $($cpu.NumberOfLogicalProcessors)"

$cs = Get-CimInstance Win32_ComputerSystem
$memGB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
Add-Line "RAM: $memGB GB"
Add-Line ""

$gpus = Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name
if ($gpus) {
    Add-Line "GPU: $([string]::Join(', ', $gpus))"
} else {
    Add-Line "GPU: not found"
}
Add-Line ""

Add-Line "Disks:"
Get-PSDrive -PSProvider FileSystem | ForEach-Object {
    $freeGB = [math]::Round($_.Free / 1GB, 1)
    $usedGB = [math]::Round($_.Used / 1GB, 1)
    Add-Line ("  {0}: Free {1} GB | Used {2} GB | Root {3}" -f $_.Name, $freeGB, $usedGB, $_.DisplayRoot)
}
Add-Line ""

Add-Line "SRC root:"
$srcRoot = "D:\src"
if (Test-Path $srcRoot) {
    $dirs = Get-ChildItem -Path $srcRoot -Directory -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name
    if ($dirs) {
        Add-Line "  D:\src exists"
        Add-Line ("  Buckets: {0}" -f ($dirs -join ", "))
    } else {
        Add-Line "  D:\src exists (empty)"
    }
} else {
    Add-Line "  missing D:\src"
}
Add-Line ""

Add-Line "Network:"
$ipv4 = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like "192.168.*" }
foreach ($ip in $ipv4) {
    Add-Line ("  {0} {1}/{2}" -f $ip.InterfaceAlias, $ip.IPAddress, $ip.PrefixLength)
}
$route = Get-NetRoute -DestinationPrefix "0.0.0.0/0" | Select-Object -First 1
if ($route) {
    Add-Line ("  Default GW: {0} ({1})" -f $route.NextHop, $route.InterfaceAlias)
}
Add-Line ""

Add-Line "Services:"
foreach ($svcName in @("sshd","Tailscale")) {
    $svc = Get-Service -Name $svcName -ErrorAction SilentlyContinue
    if ($svc) {
        Add-Line ("  {0}: {1} ({2})" -f $svc.Name, $svc.Status, $svc.StartType)
    } else {
        Add-Line ("  {0}: not installed" -f $svcName)
    }
}
Add-Line ""

Add-Line "Tailscale:"
$ts = Get-Command tailscale.exe -ErrorAction SilentlyContinue
if ($ts) {
    $tsStatus = tailscale.exe status 2>&1 | ForEach-Object { $_ -replace "`0", "" }
    if ($tsStatus) {
        $tsStatus | ForEach-Object { Add-Line "  $_" }
    } else {
        Add-Line "  (no output)"
    }
} else {
    Add-Line "  tailscale.exe not found"
}
Add-Line ""

Add-Line "WSL:"
$wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
if ($wsl) {
    try {
        $status = wsl.exe --status 2>&1 | ForEach-Object { $_ -replace "`0", "" }
        Add-Line "  wsl --status:"
        $status | ForEach-Object { Add-Line "    $_" }
        $list = wsl.exe -l -v 2>&1 | ForEach-Object { $_ -replace "`0", "" }
        Add-Line "  wsl -l -v:"
        $list | ForEach-Object { Add-Line "    $_" }
    } catch {
        Add-Line "  wsl.exe present but failed to query status"
    }
} else {
    Add-Line "  wsl.exe not found"
}
Add-Line ""

Add-Line "Training task:"
$task = schtasks /query /tn AFS_Autocomplete_Train 2>&1
$task | ForEach-Object { Add-Line "  $_" }
Add-Line ""

Add-Line "Logs:"
foreach ($log in @(
    "D:\afs_training\logs\training_autocomplete.log",
    "D:\afs_training\logs\training_fim_autocomplete.log"
)) {
    if (Test-Path $log) {
        $info = Get-Item $log
        Add-Line ("  {0} | {1} bytes | {2}" -f $info.FullName, $info.Length, $info.LastWriteTime)
    } else {
        Add-Line ("  missing {0}" -f $log)
    }
}
Add-Line ""

Add-Line "GPU util (nvidia-smi):"
$nvidia = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nvidia) {
    $gpuOut = nvidia-smi 2>&1
    $gpuOut | ForEach-Object { Add-Line "  $_" }
} else {
    Add-Line "  nvidia-smi not found"
}

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$lines | Out-File -FilePath $logPath -Encoding ascii
$lines | ForEach-Object { Write-Host $_ }
Write-Host ""
Write-Host "Audit saved to: $logPath"
