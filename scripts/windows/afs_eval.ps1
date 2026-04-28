param(
    [ValidateSet('start', 'status', 'stop')]
    [string] $Mode = 'status',
    [ValidateSet('auto', 'wsl', 'native')]
    [string] $Backend = 'auto',
    [string] $Name,
    [string] $Distro = 'Ubuntu',
    [string] $VenvDir = '~/.venvs/src-training',
    [string] $TrainRoot = 'D:\src\training',
    [string] $Python = 'C:\Python312\python.exe',
    [string] $Model,
    [string] $Adapter,
    [string] $PromptPack,
    [string] $Out,
    [double] $Temperature = 0.0,
    [double] $TopP = 1.0,
    [int] $MaxNewTokens = 220
)

$ErrorActionPreference = 'Stop'

function Convert-WslPathToWindows([string] $Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return $null
    }
    if ($Path -match '^/mnt/([a-zA-Z])/(.*)$') {
        $drive = $matches[1].ToUpperInvariant()
        $rest = ($matches[2] -replace '/', '\')
        return '{0}:\{1}' -f $drive, $rest
    }
    return $Path
}

function Shorten([string] $Text, [int] $Limit = 240) {
    if ([string]::IsNullOrEmpty($Text)) { return $Text }
    if ($Text.Length -le $Limit) { return $Text }
    return $Text.Substring(0, $Limit) + '...'
}

function Ensure-Array($Value) {
    if ($null -eq $Value) { return @() }
    if ($Value -is [System.Array]) { return $Value }
    return @($Value)
}

function Resolve-Backend([string] $Requested, [string] $EvalName) {
    if ($Requested -ne 'auto') {
        return $Requested
    }
    $statusFile = 'D:\afs_training\run\{0}.status.json' -f $EvalName
    if (Test-Path $statusFile) {
        try {
            $statusObj = Get-Content $statusFile -Raw | ConvertFrom-Json
            if ($statusObj.backend -in @('native', 'wsl')) {
                return [string]$statusObj.backend
            }
        } catch {
        }
    }
    return 'wsl'
}

function Get-WslEvalStatus(
    [string] $EvalName,
    [string] $DistroName,
    [string] $ModelName,
    [string] $AdapterPath,
    [string] $PromptPackPath,
    [string] $OutPath,
    [double] $EvalTemperature,
    [double] $EvalTopP,
    [int] $EvalMaxNewTokens
) {
    if ([string]::IsNullOrWhiteSpace($ModelName) -or
        [string]::IsNullOrWhiteSpace($AdapterPath) -or
        [string]::IsNullOrWhiteSpace($PromptPackPath) -or
        [string]::IsNullOrWhiteSpace($OutPath)) {
        return $null
    }

    $args = @(
        '-d', $DistroName,
        '--',
        'bash', '/mnt/d/src/training/scripts/wsl_eval_service.sh',
        'status',
        '--name', $EvalName,
        '--model', $ModelName,
        '--adapter', $AdapterPath,
        '--prompt-pack', $PromptPackPath,
        '--out', $OutPath,
        '--temperature', ('{0}' -f $EvalTemperature),
        '--top-p', ('{0}' -f $EvalTopP),
        '--max-new-tokens', ('{0}' -f $EvalMaxNewTokens),
        '--json'
    )

    try {
        $raw = & wsl.exe @args
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) {
            return $null
        }
        return $raw | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Get-NativeEvalProcesses([string] $OutFileName) {
    return @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq 'python.exe' -and
        $_.CommandLine -match 'eval_iquest_zelda.py' -and
        ([string]::IsNullOrWhiteSpace($OutFileName) -or $_.CommandLine -match [regex]::Escape($OutFileName))
    } | Sort-Object ProcessId)
}

function Get-NativeEvalStatus(
    [string] $EvalName,
    [string] $OutPath
) {
    $pidFile = 'D:\afs_training\run\{0}.pid' -f $EvalName
    $statusFile = 'D:\afs_training\run\{0}.status.json' -f $EvalName
    $stdoutLog = 'D:\afs_training\logs\{0}.out.log' -f $EvalName
    $stderrLog = 'D:\afs_training\logs\{0}.err.log' -f $EvalName
    $runnerPath = 'D:\afs_training\run\{0}.run.cmd' -f $EvalName
    $windowsOut = Convert-WslPathToWindows $OutPath
    $outFileName = if ($windowsOut) { [System.IO.Path]::GetFileName($windowsOut) } else { '' }
    $evalPid = $null

    if (Test-Path $pidFile) {
        $rawPid = (Get-Content -Path $pidFile -TotalCount 1 -ErrorAction SilentlyContinue).Trim()
        if ($rawPid -match '^\d+$') {
            $evalPid = [int]$rawPid
        }
    }

    $tracked = $null
    if ($evalPid) {
        $tracked = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $evalPid) -ErrorAction SilentlyContinue
    }

    $statusObj = $null
    if (Test-Path $statusFile) {
        try { $statusObj = Get-Content $statusFile -Raw | ConvertFrom-Json } catch { $statusObj = $null }
    }

    $evalProcs = @(Get-NativeEvalProcesses -OutFileName $outFileName)
    $stdoutTail = Ensure-Array @((Get-Content $stdoutLog -Tail 40 -ErrorAction SilentlyContinue) | ForEach-Object { [string]$_ })
    $stderrTail = Ensure-Array @((Get-Content $stderrLog -Tail 40 -ErrorAction SilentlyContinue) | ForEach-Object { [string]$_ })
    $completedSeen = @($stdoutTail | Where-Object { $_ -match 'Wrote eval output to' }).Count -gt 0
    $outExists = $windowsOut -and (Test-Path $windowsOut)
    $outSize = if ($outExists) { (Get-Item $windowsOut).Length } else { $null }

    $state = if ($evalProcs.Count -gt 0) {
        'running'
    } elseif ($completedSeen) {
        'completed'
    } elseif ($outExists -and $outSize -gt 0) {
        'completed'
    } elseif (Test-Path $pidFile) {
        'stopped'
    } else {
        'stopped'
    }

    if (-not $evalPid -and $evalProcs.Count -gt 0) {
        $evalPid = $evalProcs[0].ProcessId
    }

    [pscustomobject]@{
        mode = $Mode
        backend = 'native'
        name = $EvalName
        state = $state
        pid = $evalPid
        pid_file = $pidFile
        status_file = $statusFile
        stdout_log = $stdoutLog
        stderr_log = $stderrLog
        runner_script = $runnerPath
        out = $windowsOut
        pid_exists = Test-Path $pidFile
        status_exists = Test-Path $statusFile
        stdout_exists = Test-Path $stdoutLog
        stderr_exists = Test-Path $stderrLog
        out_exists = [bool]$outExists
        out_size = $outSize
        tracked_process = if ($null -eq $tracked) { $null } else { [ordered]@{
            process_id = $tracked.ProcessId
            parent_process_id = $tracked.ParentProcessId
            name = $tracked.Name
            command_line = (Shorten $tracked.CommandLine)
        } }
        eval_processes = @($evalProcs | ForEach-Object { [ordered]@{
            process_id = $_.ProcessId
            parent_process_id = $_.ParentProcessId
            name = $_.Name
            command_line = (Shorten $_.CommandLine)
        } })
        stdout_tail = $stdoutTail
        stderr_tail = $stderrTail
    }
}

function Get-WslStatusPayload(
    [string] $EvalName,
    [string] $OutPath,
    [string] $DistroName,
    [string] $ModelName,
    [string] $AdapterPath,
    [string] $PromptPackPath,
    [double] $EvalTemperature,
    [double] $EvalTopP,
    [int] $EvalMaxNewTokens
) {
    $pidFile = 'D:\afs_training\run\{0}.pid' -f $EvalName
    $stdoutLog = 'D:\afs_training\logs\{0}.out.log' -f $EvalName
    $stderrLog = 'D:\afs_training\logs\{0}.err.log' -f $EvalName
    $launcherStdoutLog = 'D:\afs_training\logs\{0}.launcher.out.log' -f $EvalName
    $launcherStderrLog = 'D:\afs_training\logs\{0}.launcher.err.log' -f $EvalName
    $windowsOut = Convert-WslPathToWindows $OutPath
    $evalPid = $null
    $state = 'stopped'
    $wslStatus = Get-WslEvalStatus `
        -EvalName $EvalName `
        -DistroName $DistroName `
        -ModelName $ModelName `
        -AdapterPath $AdapterPath `
        -PromptPackPath $PromptPackPath `
        -OutPath $OutPath `
        -EvalTemperature $EvalTemperature `
        -EvalTopP $EvalTopP `
        -EvalMaxNewTokens $EvalMaxNewTokens

    if (Test-Path $pidFile) {
        $rawPid = (Get-Content -Path $pidFile -TotalCount 1 -ErrorAction SilentlyContinue).Trim()
        if ($rawPid -match '^\d+$') {
            $evalPid = [int]$rawPid
            if ($wslStatus -and $wslStatus.pid -eq $evalPid -and -not [string]::IsNullOrWhiteSpace($wslStatus.state)) {
                $state = [string]$wslStatus.state
            } else {
                $proc = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $evalPid) -ErrorAction SilentlyContinue
                if ($proc) {
                    $state = 'running'
                } else {
                    $state = 'stale'
                }
            }
        }
    }

    if (($state -eq 'stopped' -or $state -eq 'stale') -and $wslStatus -and -not [string]::IsNullOrWhiteSpace($wslStatus.state)) {
        $state = [string]$wslStatus.state
        if (-not $evalPid -and $wslStatus.pid) {
            $evalPid = [int]$wslStatus.pid
        }
    }

    [pscustomobject]@{
        mode = $Mode
        backend = 'wsl'
        name = $EvalName
        state = $state
        pid = $evalPid
        pid_file = $pidFile
        stdout_log = $stdoutLog
        stderr_log = $stderrLog
        launcher_stdout_log = $launcherStdoutLog
        launcher_stderr_log = $launcherStderrLog
        out = $windowsOut
        pid_exists = Test-Path $pidFile
        stdout_exists = Test-Path $stdoutLog
        stderr_exists = Test-Path $stderrLog
        launcher_stdout_exists = Test-Path $launcherStdoutLog
        launcher_stderr_exists = Test-Path $launcherStderrLog
        out_exists = if ($windowsOut) { Test-Path $windowsOut } else { $false }
        out_size = if ($windowsOut -and (Test-Path $windowsOut)) { (Get-Item $windowsOut).Length } else { $null }
        wsl_state = if ($wslStatus) { [string]$wslStatus.state } else { $null }
    }
}

if ([string]::IsNullOrWhiteSpace($Name)) {
    throw 'Name is required.'
}

$ResolvedBackend = Resolve-Backend -Requested $Backend -EvalName $Name

switch ($Mode) {
    'start' {
        foreach ($field in @('Model', 'Adapter', 'PromptPack', 'Out')) {
            if ([string]::IsNullOrWhiteSpace((Get-Variable -Name $field -ValueOnly))) {
                throw "$field is required for start mode."
            }
        }

        if ($ResolvedBackend -eq 'native') {
            $pidFile = 'D:\afs_training\run\{0}.pid' -f $Name
            $statusFile = 'D:\afs_training\run\{0}.status.json' -f $Name
            $stdoutLog = 'D:\afs_training\logs\{0}.out.log' -f $Name
            $stderrLog = 'D:\afs_training\logs\{0}.err.log' -f $Name
            $runnerPath = 'D:\afs_training\run\{0}.run.cmd' -f $Name
            $windowsAdapter = Convert-WslPathToWindows $Adapter
            $windowsPromptPack = Convert-WslPathToWindows $PromptPack
            $windowsOut = Convert-WslPathToWindows $Out
            $evalScript = Join-Path $TrainRoot 'scripts\eval_iquest_zelda.py'

            foreach ($requiredPath in @($windowsAdapter, $windowsPromptPack, $windowsOut, $evalScript)) {
                if ([string]::IsNullOrWhiteSpace($requiredPath)) {
                    throw 'Native eval requires Windows-resolvable adapter, prompt pack, output, and script paths.'
                }
            }

            New-Item -ItemType Directory -Force -Path 'D:\afs_training\run', 'D:\afs_training\logs', (Split-Path -Parent $windowsOut) | Out-Null
            foreach ($path in @($stdoutLog, $stderrLog, $pidFile, $statusFile)) {
                if (Test-Path $path) { Remove-Item -Force $path }
            }

            @"
@echo off
set "HF_HUB_DISABLE_XET=1"
cd /d "$TrainRoot"
"$Python" "$evalScript" --model "$Model" --adapter "$windowsAdapter" --prompt-pack "$windowsPromptPack" --out "$windowsOut" --temperature "$Temperature" --top-p "$TopP" --max-new-tokens "$MaxNewTokens" 1>> "$stdoutLog" 2>> "$stderrLog"
"@ | Set-Content -Path $runnerPath

            $launchCommand = "cmd.exe /c `"$runnerPath`""
            $created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
                CommandLine = $launchCommand
                CurrentDirectory = $TrainRoot
            }
            if ($created.ReturnValue -ne 0) { throw "Failed to launch native eval via Win32_Process.Create ($($created.ReturnValue))" }
            Start-Sleep -Seconds 5

            $outFileName = [System.IO.Path]::GetFileName($windowsOut)
            $evalProcs = @(Get-NativeEvalProcesses -OutFileName $outFileName)
            $recordPid = if ($evalProcs.Count -gt 0) { $evalProcs[0].ProcessId } else { $null }
            if ($recordPid) {
                Set-Content -Path $pidFile -Value $recordPid
            }

            [ordered]@{
                backend = 'native'
                name = $Name
                pid = $recordPid
                wrapper_pid = $created.ProcessId
                pid_file = $pidFile
                status_file = $statusFile
                stdout_log = $stdoutLog
                stderr_log = $stderrLog
                runner_script = $runnerPath
                out = $windowsOut
                launched_at = (Get-Date).ToString('o')
            } | ConvertTo-Json -Depth 4 | Set-Content -Path $statusFile

            (Get-NativeEvalStatus -EvalName $Name -OutPath $Out) | ConvertTo-Json -Compress -Depth 6
            exit 0
        }

        $args = @(
            '-d', $Distro,
            '--',
            'bash', '/mnt/d/src/training/scripts/wsl_eval_service.sh',
            'start',
            '--name', $Name,
            '--model', $Model,
            '--adapter', $Adapter,
            '--prompt-pack', $PromptPack,
            '--out', $Out,
            '--temperature', ('{0}' -f $Temperature),
            '--top-p', ('{0}' -f $TopP),
            '--max-new-tokens', ('{0}' -f $MaxNewTokens),
            '--json'
        )

        $launcherStdout = 'D:\afs_training\logs\{0}.launcher.out.log' -f $Name
        $launcherStderr = 'D:\afs_training\logs\{0}.launcher.err.log' -f $Name
        $proc = Start-Process -FilePath 'wsl.exe' -ArgumentList $args -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput $launcherStdout -RedirectStandardError $launcherStderr
        Start-Sleep -Seconds 5
        $launcherExited = $false
        $launcherExitCode = $null
        try {
            Wait-Process -Id $proc.Id -Timeout 1 -ErrorAction Stop
            $proc.Refresh()
            $launcherExited = $proc.HasExited
            if ($launcherExited) {
                $launcherExitCode = $proc.ExitCode
            }
        } catch {
            $launcherExited = $false
            $launcherExitCode = $null
        }
        $status = Get-WslStatusPayload `
            -EvalName $Name `
            -OutPath $Out `
            -DistroName $Distro `
            -ModelName $Model `
            -AdapterPath $Adapter `
            -PromptPackPath $PromptPack `
            -EvalTemperature $Temperature `
            -EvalTopP $TopP `
            -EvalMaxNewTokens $MaxNewTokens
        $status | Add-Member -NotePropertyName launcher_pid -NotePropertyValue $proc.Id
        $status | Add-Member -NotePropertyName launcher_exited -NotePropertyValue $launcherExited
        $status | Add-Member -NotePropertyName launcher_exit_code -NotePropertyValue $launcherExitCode
        $status | ConvertTo-Json -Compress -Depth 5
        exit 0
    }
    'stop' {
        if ($ResolvedBackend -eq 'native') {
            $pidFile = 'D:\afs_training\run\{0}.pid' -f $Name
            $statusFile = 'D:\afs_training\run\{0}.status.json' -f $Name
            $windowsOut = Convert-WslPathToWindows $Out
            $outFileName = if ($windowsOut) { [System.IO.Path]::GetFileName($windowsOut) } else { '' }
            $statusObj = $null
            if (Test-Path $statusFile) {
                try { $statusObj = Get-Content $statusFile -Raw | ConvertFrom-Json } catch { $statusObj = $null }
            }

            $candidatePids = @()
            if (Test-Path $pidFile) {
                try { $candidatePids += [int](Get-Content $pidFile -TotalCount 1 -ErrorAction SilentlyContinue).Trim() } catch { }
            }
            if ($statusObj -and $statusObj.wrapper_pid) {
                $candidatePids += [int]$statusObj.wrapper_pid
            }
            $candidatePids += @(Get-NativeEvalProcesses -OutFileName $outFileName | ForEach-Object { $_.ProcessId })
            $candidatePids = @($candidatePids | Where-Object { $_ } | Sort-Object -Unique)

            $stopped = @()
            foreach ($pid in $candidatePids) {
                & taskkill /PID $pid /T /F *> $null
                if ($LASTEXITCODE -eq 0) { $stopped += $pid }
            }

            if (Test-Path $pidFile) { Remove-Item -Force $pidFile }
            if ($statusObj) {
                $statusObj | Add-Member -NotePropertyName stopped_at -NotePropertyValue (Get-Date).ToString('o') -Force
                $statusObj | Add-Member -NotePropertyName stopped_pids -NotePropertyValue $stopped -Force
                $statusObj | ConvertTo-Json -Depth 4 | Set-Content -Path $statusFile
            }
            (Get-NativeEvalStatus -EvalName $Name -OutPath $Out) | ConvertTo-Json -Compress -Depth 6
            exit 0
        }

        $args = @(
            '-d', $Distro,
            '--',
            'bash', '/mnt/d/src/training/scripts/wsl_eval_service.sh',
            'stop',
            '--name', $Name,
            '--json'
        )
        $launcherStdout = 'D:\afs_training\logs\{0}.launcher.out.log' -f $Name
        $launcherStderr = 'D:\afs_training\logs\{0}.launcher.err.log' -f $Name
        Start-Process -FilePath 'wsl.exe' -ArgumentList $args -WindowStyle Hidden `
            -RedirectStandardOutput $launcherStdout -RedirectStandardError $launcherStderr | Out-Null
        Start-Sleep -Seconds 2
        Get-WslStatusPayload `
            -EvalName $Name `
            -OutPath $Out `
            -DistroName $Distro `
            -ModelName $Model `
            -AdapterPath $Adapter `
            -PromptPackPath $PromptPack `
            -EvalTemperature $Temperature `
            -EvalTopP $TopP `
            -EvalMaxNewTokens $MaxNewTokens | ConvertTo-Json -Compress -Depth 5
        exit 0
    }
    'status' {
        if ($ResolvedBackend -eq 'native') {
            (Get-NativeEvalStatus -EvalName $Name -OutPath $Out) | ConvertTo-Json -Compress -Depth 6
            exit 0
        }
        Get-WslStatusPayload `
            -EvalName $Name `
            -OutPath $Out `
            -DistroName $Distro `
            -ModelName $Model `
            -AdapterPath $Adapter `
            -PromptPackPath $PromptPack `
            -EvalTemperature $Temperature `
            -EvalTopP $TopP `
            -EvalMaxNewTokens $MaxNewTokens | ConvertTo-Json -Compress -Depth 5
        exit 0
    }
}
