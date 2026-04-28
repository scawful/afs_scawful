param(
    [ValidateSet('install', 'remove', 'status')]
    [string]$Mode = 'install',
    [string]$TaskName = 'AFS_Hostd',
    [string]$ScriptPath = 'D:\afs_training\scripts\afs_hostd.ps1'
)

$ErrorActionPreference = 'Stop'

function Get-HostdTask {
    try {
        return Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    } catch {
        return $null
    }
}

switch ($Mode) {
    'install' {
        $action = New-ScheduledTaskAction `
            -Execute 'powershell.exe' `
            -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`" -Mode start"
        $trigger = New-ScheduledTaskTrigger -AtLogOn
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable

        $existing = Get-HostdTask
        if ($existing) {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        }

        Register-ScheduledTask `
            -TaskName $TaskName `
            -Action $action `
            -Trigger $trigger `
            -Settings $settings `
            -Description 'Start afs-hostd at user logon for local Windows/WSL control.'

        Write-Host "Installed scheduled task: $TaskName"
        exit 0
    }
    'remove' {
        $existing = Get-HostdTask
        if ($existing) {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
            Write-Host "Removed scheduled task: $TaskName"
        } else {
            Write-Host "Scheduled task not present: $TaskName"
        }
        exit 0
    }
    'status' {
        $task = Get-HostdTask
        if (-not $task) {
            Write-Host "Scheduled task not present: $TaskName"
            exit 1
        }
        $task | Select-Object TaskName, State, Author, Description | Format-List
        exit 0
    }
}
