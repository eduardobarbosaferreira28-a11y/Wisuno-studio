# Runs the full quality gate: lint, format check, tests. Stops at the first failure.
# Usage (venv active): .\scripts\verify.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$steps = @(
    @{ Name = "ruff check";           Args = @("-m", "ruff", "check", ".") },
    @{ Name = "ruff format --check";  Args = @("-m", "ruff", "format", "--check", ".") },
    @{ Name = "pytest -ra";           Args = @("-m", "pytest", "-ra") }
)

foreach ($step in $steps) {
    Write-Host "==> $($step.Name)" -ForegroundColor Cyan
    & python @($step.Args)
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $($step.Name)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Write-Host "verify: all checks passed" -ForegroundColor Green
exit 0
