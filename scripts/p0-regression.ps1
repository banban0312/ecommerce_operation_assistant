param(
    [pscredential]$Credential,
    [string]$ReportPath = ""
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$results = [System.Collections.Generic.List[object]]::new()

function Add-Result {
    param([string]$Name, [bool]$Passed, [string]$Detail)
    $results.Add([ordered]@{ name = $Name; passed = $Passed; detail = $Detail })
    if ($Passed) { Write-Host "PASS $Name" } else { Write-Host "FAIL $Name - $Detail" }
}

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments, [string]$Name)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { Add-Result $Name $false "退出码 $LASTEXITCODE"; throw "P0 regression failed: $Name" }
    Add-Result $Name $true "命令执行成功"
}

Push-Location $repositoryRoot
try {
    $apiAddress = (docker compose port api 8000 | Select-Object -First 1).Trim()
    $webAddress = (docker compose port web 3000 | Select-Object -First 1).Trim()
    if (-not $apiAddress -or -not $webAddress) { throw 'API/Web 容器未运行，请先执行 docker compose up -d --build --wait。' }
    $apiBase = "http://$apiAddress"
    $webBase = "http://$webAddress"

    foreach ($endpoint in @("$apiBase/health/live", "$apiBase/health/ready", "$webBase/health", "$webBase/api/health")) {
        $response = Invoke-WebRequest -Uri $endpoint -TimeoutSec 15 -UseBasicParsing
        if ($response.StatusCode -ne 200) { throw "健康检查失败: $endpoint" }
        Add-Result "健康检查 $endpoint" $true "HTTP $($response.StatusCode)"
    }

    $anonymousStatus = 0
    try {
        $anonymous = Invoke-WebRequest -Uri "$webBase/" -TimeoutSec 15 -UseBasicParsing -MaximumRedirection 0
        $anonymousStatus = [int]$anonymous.StatusCode
    } catch {
        if ($_.Exception.Response) { $anonymousStatus = [int]$_.Exception.Response.StatusCode.value__ } else { throw }
    }
    if ($anonymousStatus -notin @(302, 307, 401)) { throw '匿名访问未被登录保护。' }
    Add-Result '匿名访问保护' $true "HTTP $anonymousStatus"

    if (-not $Credential) {
        Write-Warning '未提供管理员凭据，跳过登录后的 P0 页面回归。'
    } else {
        $loginBody = @{ email = $Credential.UserName; password = $Credential.GetNetworkCredential().Password } | ConvertTo-Json -Compress
        $login = Invoke-WebRequest -Uri "$webBase/api/auth/login" -Method Post -ContentType 'application/json' -Body $loginBody -SessionVariable authSession -TimeoutSec 15 -UseBasicParsing
        if ($login.StatusCode -ne 200) { throw '管理员登录失败。' }
        Add-Result '管理员登录' $true 'HTTP 200；凭据未写入报告'

        foreach ($page in @(
            @{ path = '/'; marker = 'WORKSPACE OVERVIEW'; name = '运营大盘' },
            @{ path = '/products'; marker = '商品工作台'; name = '商品工作台' },
            @{ path = '/settings'; marker = '系统设置'; name = '模型与系统配置' },
            @{ path = '/imports'; marker = '批量导入中心'; name = '批量导入中心' }
        )) {
            $pageResponse = Invoke-WebRequest -Uri "$webBase$($page.path)" -WebSession $authSession -TimeoutSec 15 -UseBasicParsing
            if ($pageResponse.StatusCode -ne 200 -or -not $pageResponse.Content.Contains($page.marker)) { throw "页面回归失败: $($page.path)" }
            Add-Result "页面 $($page.name)" $true 'HTTP 200 且包含页面标识'
        }
        $logout = Invoke-WebRequest -Uri "$webBase/api/auth/logout" -Method Post -WebSession $authSession -TimeoutSec 15 -UseBasicParsing
        if ($logout.StatusCode -ne 200) { throw '退出登录失败。' }
        Add-Result '退出登录' $true 'HTTP 200'
    }

    Invoke-Checked docker @('compose', 'exec', '-T', 'api', 'python', '-m', 'app.smoke') '迁移与 Worker 往返'
    Add-Result 'P0 回归' $true '基础健康、鉴权、页面和异步链路已完成'
}
catch {
    Add-Result 'P0 回归' $false $_.Exception.Message
    throw
}
finally {
    if ($ReportPath) {
        $report = [ordered]@{
            generatedAt = (Get-Date).ToUniversalTime().ToString('o')
            credentialProvided = [bool]$Credential
            results = $results
        }
        $reportFullPath = [System.IO.Path]::GetFullPath($ReportPath)
        New-Item -ItemType Directory -Path (Split-Path -Parent $reportFullPath) -Force | Out-Null
        [System.IO.File]::WriteAllText($reportFullPath, ($report | ConvertTo-Json -Depth 8), [System.Text.UTF8Encoding]::new($false))
        Write-Host "Regression report: $reportFullPath"
    }
    Pop-Location
}
