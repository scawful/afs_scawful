function Afs-Status {
    & "D:\afs_training\scripts\afs_status.cmd"
}

function Afs-Logs {
    param(
        [string]$Path = ""
    )
    if ([string]::IsNullOrWhiteSpace($Path)) {
        & "D:\afs_training\scripts\afs_logs.cmd"
    } else {
        & "D:\afs_training\scripts\afs_logs.cmd" $Path
    }
}

function Afs-Tail {
    param(
        [string]$Path = "D:\afs_training\logs\training_autocomplete.log",
        [int]$Tail = 80
    )
    & "D:\afs_training\scripts\afs_tail.ps1" -Path $Path -Tail $Tail
}

Set-Alias afs-status Afs-Status
Set-Alias afs-logs Afs-Logs
Set-Alias afs-tail Afs-Tail
