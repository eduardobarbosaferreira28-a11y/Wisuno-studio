# Removes a finished task worktree and its local branch, only after the branch is merged.
# Usage (from the main checkout): .\scripts\end-task.ps1 -Id 001
# Merged means: the branch tip is an ancestor of origin/main, or (for squash merges)
# GitHub reports its PR as MERGED via the gh CLI. Otherwise nothing is removed.
param(
    [Parameter(Mandatory)][ValidatePattern('^\d{3}$')][string]$Id
)
$ErrorActionPreference = "Stop"

$repoRoot = (git -C $PSScriptRoot rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0) { Write-Host "Not inside a git repository." -ForegroundColor Red; exit 1 }
$target = [System.IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $repoRoot) "wisuno-$Id"))

if ([System.IO.Path]::GetFullPath($repoRoot) -eq $target) {
    Write-Host "Run this from another checkout, not from inside wisuno-$Id." -ForegroundColor Red
    exit 1
}

# Find the worktree and its branch.
$branch = $null
$current = $null
foreach ($line in (git -C $repoRoot worktree list --porcelain)) {
    if ($line -like "worktree *") { $current = [System.IO.Path]::GetFullPath($line.Substring(9)) }
    elseif ($line -like "branch refs/heads/*" -and $current -eq $target) { $branch = $line.Substring(18) }
}
if (-not $branch) {
    Write-Host "No worktree with a branch found at $target" -ForegroundColor Red
    exit 1
}
Write-Host "Worktree: $target  [$branch]"

Write-Host "==> git fetch origin --prune" -ForegroundColor Cyan
git -C $repoRoot fetch origin --prune
if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: git fetch" -ForegroundColor Red; exit 1 }

$merged = $false
git -C $repoRoot merge-base --is-ancestor $branch origin/main
if ($LASTEXITCODE -eq 0) {
    $merged = $true
    Write-Host "Branch is contained in origin/main." -ForegroundColor Green
} elseif (Get-Command gh -ErrorAction SilentlyContinue) {
    # Continue so gh's stderr (e.g. "no pull requests found") does not throw under Stop.
    $ErrorActionPreference = "Continue"
    Push-Location $repoRoot
    try {
        $state = (gh pr view $branch --json state --jq .state 2>$null)
        $ghExit = $LASTEXITCODE
    } finally {
        Pop-Location
        $ErrorActionPreference = "Stop"
    }
    if ($ghExit -eq 0 -and "$state".Trim() -eq "MERGED") {
        $merged = $true
        Write-Host "GitHub reports the PR for $branch as MERGED (squash/rebase merge)." -ForegroundColor Green
    }
}

if (-not $merged) {
    Write-Host "Cannot confirm $branch is merged into origin/main. Nothing removed." -ForegroundColor Red
    exit 1
}

Write-Host "==> git worktree remove $target" -ForegroundColor Cyan
git -C $repoRoot worktree remove $target
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAILED: worktree has uncommitted or untracked changes; clean it up first." -ForegroundColor Red
    exit 1
}

# -D because squash-merged branches are not ancestors of main; merge was confirmed above.
Write-Host "==> git branch -D $branch" -ForegroundColor Cyan
git -C $repoRoot branch -D $branch
if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: git branch -D" -ForegroundColor Red; exit 1 }

Write-Host "Task $Id cleaned up. Remote branch left as is." -ForegroundColor Green
exit 0
