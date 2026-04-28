param(
    [ValidateSet('start', 'stop', 'status')]
    [string] $Mode = 'status',
    [string] $BindHost = '127.0.0.1',
    [int] $Port = 8766,
    [string] $Python = 'py',
    [string] $ScriptPath = 'D:\afs_training\scripts\afs_hostd.py',
    [string] $LogDir = 'D:\afs_training\logs'
)

$ErrorActionPreference = 'Stop'

function Get-HostdProcesses {
    Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -match 'afs_hostd\.py'
    }
}

function Get-JsonStatus {
    $procs = @(Get-HostdProcesses)
    $listen = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object LocalAddress, LocalPort, OwningProcess)
    $health = $null
    $healthError = $null
    try {
        $health = Invoke-RestMethod -Uri ("http://{0}:{1}/healthz" -f $BindHost, $Port) -Method Get
    } catch {
        $healthError = $_.Exception.Message
    }
    @{
        mode = $Mode
        host = $BindHost
        port = $Port
        script_path = $ScriptPath
        processes = @($procs | Select-Object ProcessId, Name, CommandLine)
        listeners = $listen
        health = $health
        health_error = $healthError
        stdout_log = Join-Path $LogDir 'afs_hostd.out.log'
        stderr_log = Join-Path $LogDir 'afs_hostd.err.log'
    } | ConvertTo-Json -Depth 8 -Compress
}

switch ($Mode) {
    'stop' {
        @(Get-HostdProcesses) | ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 1
        Get-JsonStatus
        exit 0
    }
    'start' {
        [IO.Directory]::CreateDirectory($LogDir) | Out-Null
        @(Get-HostdProcesses) | ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 1
        $stdoutLog = Join-Path $LogDir 'afs_hostd.out.log'
        $stderrLog = Join-Path $LogDir 'afs_hostd.err.log'
        $commandLine = 'cmd.exe /c "set PYTHONUNBUFFERED=1 && {0} -3 ""{1}"" --host {2} --port {3} 1>>""{4}"" 2>>""{5}"""' -f $Python, $ScriptPath, $BindHost, $Port, $stdoutLog, $stderrLog
        $create = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $commandLine }
        Start-Sleep -Seconds 3
        Get-JsonStatus
        exit ([int]$create.ReturnValue)
    }
    'status' {
        Get-JsonStatus
        exit 0
    }
}
