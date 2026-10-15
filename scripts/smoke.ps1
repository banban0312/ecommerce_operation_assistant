$ErrorActionPreference = 'Stop'
# 从 Compose 读取实际映射端口，支持用户自定义 WEB_PORT 和 API_PORT。
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $apiAddress = docker compose port api 8000
    if ($LASTEXITCODE -ne 0) { throw 'API container is not running.' }
    $webAddress = docker compose port web 3000
    if ($LASTEXITCODE -ne 0) { throw 'Web container is not running.' }
    $apiBase = 'http://' + ($apiAddress | Select-Object -First 1).Trim()
    $webBase = 'http://' + ($webAddress | Select-Object -First 1).Trim()
    # HTTP 探针验证本机到 Web/API 的访问及服务间健康状态。
    foreach ($endpoint in @("$apiBase/health/live", "$apiBase/health/ready", "$webBase/health", "$webBase/api/health")) {
        $result = Invoke-RestMethod -Uri $endpoint -TimeoutSec 15
        if ($result.status -ne 'ok') { throw "Health check failed: $endpoint" }
        Write-Host "PASS $endpoint"
    }
    $page = Invoke-WebRequest -Uri $webBase -TimeoutSec 15 -UseBasicParsing
    if (-not $page.Content.Contains('运营大盘')) { throw 'Dashboard HTML was not returned.' }
    Write-Host 'PASS dashboard HTML'
    # 容器内验证数据库迁移版本和 Worker 往返执行任务。
    docker compose exec -T api python -m app.smoke
    if ($LASTEXITCODE -ne 0) { throw 'Migration or worker round-trip probe failed.' }
    Write-Host 'Foundation smoke checks passed.'
}
finally { Pop-Location }
