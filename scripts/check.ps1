param([switch]$SkipInstall)
# 默认安装锁定依赖后执行检查；-SkipInstall 适用于依赖已安装的快速复查。
$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    # PowerShell 不会自动因外部程序返回非零码而停止，因此显式检查退出码。
    if ($LASTEXITCODE -ne 0) { throw "Check failed: $Executable $($Arguments -join ' ')" }
}

Push-Location $repositoryRoot
try {
    if (-not $SkipInstall) {
        # Python 和前端依照各自锁文件安装，保证依赖版本可复现。
        Invoke-Checked -Executable uv -Arguments @('sync', '--project', 'api', '--locked')
        Invoke-Checked -Executable npm -Arguments @('--prefix', 'web', 'ci')
    }
    # 后端依次检查代码规范、格式和自动化测试。
    Push-Location api
    try {
        Invoke-Checked -Executable uv -Arguments @('run', '--locked', '--no-sync', 'ruff', 'check', '.')
        Invoke-Checked -Executable uv -Arguments @('run', '--locked', '--no-sync', 'ruff', 'format', '--check', '.')
        Invoke-Checked -Executable uv -Arguments @('run', '--locked', '--no-sync', 'pytest', '-q')
    }
    finally { Pop-Location }
    # 前端执行静态规范、TypeScript 检查和生产构建。
    Invoke-Checked -Executable npm -Arguments @('--prefix', 'web', 'run', 'lint')
    Invoke-Checked -Executable npm -Arguments @('--prefix', 'web', 'run', 'typecheck')
    Invoke-Checked -Executable npm -Arguments @('--prefix', 'web', 'run', 'build')
    Write-Host 'Local checks passed. Run scripts/smoke.ps1 against the Compose stack next.'
}
finally { Pop-Location }
