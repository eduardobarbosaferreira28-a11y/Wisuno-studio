# Creates a new task worktree next to this repo, on a fresh branch from origin/main.
# Usage: .\scripts\new-task.ps1 -Id 001 -Name auth-fail-closed -Type fix
#   -> ..\wisuno-001 on branch fix/001-auth-fail-closed, with .env copied and .venv installed.
param(
    [Parameter(Mandatory)][ValidatePattern('^\d{3}$')][string]$Id,
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9]+(-[a-z0-9]+)*$')][string]$Name,
    [Parameter(Mandatory)][ValidateSet('fix', 'feat', 'chore')][string]$Type
)
$ErrorActionPreference = "Stop"

function Invoke-Native {
    param([string]$What, [scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $What (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

$repoRoot = (git -C $PSScriptRoot rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0) { Write-Host "Not inside a git repository." -ForegroundColor Red; exit 1 }
$repoRoot = [System.IO.Path]::GetFullPath($repoRoot)
$target = Join-Path (Split-Path -Parent $repoRoot) "wisuno-$Id"
$branch = "$Type/$Id-$Name"

if (Test-Path $target) {
    Write-Host "Target folder already exists: $target" -ForegroundColor Red
    exit 1
}

Write-Host "==> git fetch origin" -ForegroundColor Cyan
Invoke-Native "git fetch origin" { git -C $repoRoot fetch origin }

git -C $repoRoot show-ref --verify --quiet "refs/heads/$branch"
if ($LASTEXITCODE -eq 0) { Write-Host "Local branch already exists: $branch" -ForegroundColor Red; exit 1 }
git -C $repoRoot show-ref --verify --quiet "refs/remotes/origin/$branch"
if ($LASTEXITCODE -eq 0) { Write-Host "Remote branch already exists: origin/$branch" -ForegroundColor Red; exit 1 }

Write-Host "==> git worktree add $target -b $branch origin/main" -ForegroundColor Cyan
Invoke-Native "git worktree add" { git -C $repoRoot worktree add --no-track $target -b $branch origin/main }

# Copy .env without reading or printing it. It must hold dev keys only (wisuno-studio-dev).
$envSource = Join-Path $repoRoot ".env"
if (Test-Path $envSource) {
    Copy-Item -LiteralPath $envSource -Destination (Join-Path $target ".env")
    Write-Host "==> copied .env (dev keys only)" -ForegroundColor Cyan
} else {
    Write-Host "WARNING: no .env in $repoRoot; create $target\.env from .env.example (dev project)." -ForegroundColor Yellow
}

Write-Host "==> python -m venv .venv" -ForegroundColor Cyan
Invoke-Native "python -m venv" { python -m venv (Join-Path $target ".venv") }

$venvPython = Join-Path $target ".venv\Scripts\python.exe"
Push-Location $target
try {
    Write-Host "==> pip install requirements" -ForegroundColor Cyan
    Invoke-Native "pip install" {
        & $venvPython -m pip install -r requirements-dev.txt -r studio/backend/requirements_studio.txt
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Task $Id ready: $target  [$branch]" -ForegroundColor Green
Write-Host "Next steps:"
Write-Host "  1. cd $target"
Write-Host "  2. .venv\Scripts\Activate.ps1"
Write-Host "  3. Write or review tasks\$Id-$Name.md, then open Claude Code in this folder"
Write-Host "  4. .\scripts\verify.ps1 before opening the PR"
Write-Host "  5. After the PR is merged: .\scripts\end-task.ps1 -Id $Id  (run from the main checkout)"
exit 0
