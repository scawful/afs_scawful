# Keeps eva-02 ready as the scawfulbot failover box without competing with games.
# Loop: while any process runs from a game folder, unload every model and stop the LM Studio
# server (the gateway then sees eva-02 as down); otherwise keep the server on :1234 (JIT loads,
# idle TTL unloads) and afs-hostd on the tailnet address for model identity.
# LM Studio has no API auth; :1234 and :8766 rely on the "block non-Tailscale" firewall rules.
param(
    [string] $Root = 'C:\afs',
    [string] $BindHost = '100.122.116.112',
    [int] $HostdPort = 8766,
    [int] $LmsPort = 1234,
    [int] $IntervalSeconds = 20,
    # Consecutive game-free checks before the server comes back.
    [int] $ClearChecks = 3,
    [string[]] $GameRoots = @(
        'C:\Program Files (x86)\Steam\steamapps\common',
        'D:\SteamLibrary\steamapps\common',
        'C:\XboxGames',
        'C:\Games',
        'C:\Program Files\Epic Games'
    ),
    [switch] $Once
)

$ErrorActionPreference = 'Continue'
$lms = Join-Path $env:USERPROFILE '.lmstudio\bin\lms.exe'
$log = Join-Path $Root 'logs\failover_guard.log'
$python = Join-Path $Root 'venv\Scripts\python.exe'
$hostdScript = Join-Path $Root 'afs-scawful\scripts\windows\afs_hostd.py'
$tokenFile = Join-Path $Root 'config\hostd.token'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null

function Log([string] $msg) {
    Add-Content -Path $log -Value ("{0} {1}" -f (Get-Date).ToString('s'), $msg)
}

function Get-GameProcess {
    $roots = $GameRoots | Where-Object { Test-Path $_ } | ForEach-Object { $_.TrimEnd('\') + '\' }
    if (-not $roots) { return $null }
    Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $path = $_.Path
        $path -and ($roots | Where-Object { $path.StartsWith($_, [StringComparison]::OrdinalIgnoreCase) })
    } | Select-Object -First 1
}

# Get-NetTCPConnection misses live listeners on this box; a real connect does not.
function Test-Listening([string] $address, [int] $port) {
    $client = [Net.Sockets.TcpClient]::new()
    try { return ($client.ConnectAsync($address, $port).Wait(1500) -and $client.Connected) }
    catch { return $false }
    finally { $client.Dispose() }
}

function Ensure-Hostd {
    if (Test-Listening $BindHost $HostdPort) { return }
    # A fresh start can take longer than one interval to bind.
    $running = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'afs_hostd\.py' }
    if ($running) { return }
    $ips = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | ForEach-Object IPAddress)
    if ($ips -notcontains $BindHost) { return }  # Tailscale not up yet
    $env:AFS_HOSTD_TOKEN_FILE = $tokenFile
    $env:PYTHONUNBUFFERED = '1'
    Start-Process -FilePath $python -ArgumentList @($hostdScript, '--host', $BindHost, '--port', $HostdPort) `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $Root 'logs\afs_hostd.out.log') `
        -RedirectStandardError (Join-Path $Root 'logs\afs_hostd.err.log')
    Log "hostd_started bind=${BindHost}:$HostdPort"
}

$clear = $ClearChecks
$gaming = $false
Log "guard_start pid=$PID"
while ($true) {
    try {
        Ensure-Hostd
        $game = Get-GameProcess
        if ($game) {
            $clear = 0
            $entered = -not $gaming
            if ($entered) { Log "game_detected name=$($game.Name)" }
            $gaming = $true
            if ($entered -or (Test-Listening '127.0.0.1' $LmsPort)) {
                & $lms unload --all 2>&1 | Out-Null
                & $lms server stop 2>&1 | Out-Null
                Log "lms_stopped_for_game name=$($game.Name)"
            }
        } else {
            $clear = [Math]::Min($clear + 1, $ClearChecks)
            if ($clear -ge $ClearChecks) {
                if ($gaming) { Log 'game_cleared' }
                $gaming = $false
                if (-not (Test-Listening '127.0.0.1' $LmsPort)) {
                    & $lms server start --port $LmsPort --bind 0.0.0.0 2>&1 | Out-Null
                    Log "lms_started listening=$(Test-Listening '127.0.0.1' $LmsPort)"
                }
            }
        }
    } catch {
        Log ("error: " + $_.Exception.Message)
    }
    if ($Once) { break }
    Start-Sleep -Seconds $IntervalSeconds
}
