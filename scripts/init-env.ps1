$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $repositoryRoot '.env'
# 已存在配置可能包含个人密码，因此初始化脚本不会覆盖它。
if (Test-Path -LiteralPath $envFile) {
    Write-Host '.env already exists; no values were changed.'
    exit 0
}

function New-LocalPassword {
    # 使用系统密码学随机数生成器创建数据库密码。
    $bytes = New-Object byte[] 32
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) }
    finally { $generator.Dispose() }
    return [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
}

$template = [System.IO.File]::ReadAllText((Join-Path $repositoryRoot '.env.example'))
# 生成本地数据库凭据和认证签名密钥；模型服务密钥待对应功能接入时配置。
$template = $template -replace '(?m)^MYSQL_PASSWORD=.*$', ('MYSQL_PASSWORD=' + (New-LocalPassword))
$template = $template -replace '(?m)^MYSQL_ROOT_PASSWORD=.*$', ('MYSQL_ROOT_PASSWORD=' + (New-LocalPassword))
$template = $template -replace '(?m)^AUTH_SECRET_KEY=.*$', ('AUTH_SECRET_KEY=' + (New-LocalPassword))
[System.IO.File]::WriteAllText($envFile, $template, [System.Text.UTF8Encoding]::new($false))
Write-Host 'Created ignored .env with random database passwords and an authentication signing key.'
