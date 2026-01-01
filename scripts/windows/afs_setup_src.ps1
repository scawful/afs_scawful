param(
    [string]$Root = "D:\src",
    [switch]$Force
)

$Root = $Root.Trim("'").Trim('"')

$dirs = @(
    "hobby",
    "lab",
    "halext",
    "tools",
    "third_party",
    "docs",
    "shared",
    "ops",
    "training",
    "scripts",
    "workspaces",
    "roms"
)

if (-not (Test-Path $Root)) {
    New-Item -ItemType Directory -Path $Root -Force | Out-Null
}

foreach ($dir in $dirs) {
    $path = Join-Path $Root $dir
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
}

$readme = @"
SRC Universe (Windows)
Root: $Root

Buckets:
- hobby/   Nintendo-adjacent, ROM hacking, retro
- lab/     experiments, prototypes
- halext/  commercial work only

Notes:
- Prefer git for code sync.
- Keep .context/ local per machine.
- Training data lives in D:\afs_training.
- WSL can access this root at /mnt/d/src.
"@

$readmePath = Join-Path $Root "README.txt"
if (-not (Test-Path $readmePath) -or $Force) {
    $readme | Out-File -FilePath $readmePath -Encoding ascii
}

Write-Host "SRC root ready: $Root"
Write-Host "Buckets: $($dirs -join ', ')"
