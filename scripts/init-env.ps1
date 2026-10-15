$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $repositoryRoot '.env'
if (Test-Path -LiteralPath $envFile) {
    Write-Host '.env already exists; no values were changed.'
    exit 0
}

function New-LocalPassword {
    $bytes = New-Object byte[] 32
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) }
    finally { $generator.Dispose() }
    return [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
}

$template = [System.IO.File]::ReadAllText((Join-Path $repositoryRoot '.env.example'))
$template = $template -replace '(?m)^MYSQL_PASSWORD=.*$', ('MYSQL_PASSWORD=' + (New-LocalPassword))
$template = $template -replace '(?m)^MYSQL_ROOT_PASSWORD=.*$', ('MYSQL_ROOT_PASSWORD=' + (New-LocalPassword))
[System.IO.File]::WriteAllText($envFile, $template, [System.Text.UTF8Encoding]::new($false))
Write-Host 'Created ignored .env with random local database passwords. No model credentials are required.'
