param([switch]$SkipInstall)
$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Check failed: $Executable $($Arguments -join ' ')" }
}

Push-Location $repositoryRoot
try {
    if (-not $SkipInstall) {
        Invoke-Checked -Executable uv -Arguments @('sync', '--project', 'api', '--locked')
        Invoke-Checked -Executable npm -Arguments @('--prefix', 'web', 'ci')
    }
    Push-Location api
    try {
        Invoke-Checked -Executable uv -Arguments @('run', '--locked', '--no-sync', 'ruff', 'check', '.')
        Invoke-Checked -Executable uv -Arguments @('run', '--locked', '--no-sync', 'ruff', 'format', '--check', '.')
        Invoke-Checked -Executable uv -Arguments @('run', '--locked', '--no-sync', 'pytest', '-q')
    }
    finally { Pop-Location }
    Invoke-Checked -Executable npm -Arguments @('--prefix', 'web', 'run', 'lint')
    Invoke-Checked -Executable npm -Arguments @('--prefix', 'web', 'run', 'typecheck')
    Invoke-Checked -Executable npm -Arguments @('--prefix', 'web', 'run', 'build')
    Write-Host 'Local checks passed. Run scripts/smoke.ps1 against the Compose stack next.'
}
finally { Pop-Location }
