param([string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path (Split-Path -Parent $repositoryRoot) '镜像'
}
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

Push-Location $repositoryRoot
try {
    $runtimeImages = @(docker compose config --images | Sort-Object -Unique)
    if ($LASTEXITCODE -ne 0) { throw 'Could not read Compose image references.' }
    $buildImages = @(
        foreach ($dockerfile in @('api/Dockerfile', 'web/Dockerfile')) {
            foreach ($line in Get-Content -LiteralPath $dockerfile) {
                if ($line -match '^FROM\s+([^\s]+)') { $Matches[1] }
            }
        }
    ) | Sort-Object -Unique
    $allImages = @(@($runtimeImages) + @($buildImages) | Sort-Object -Unique)
    $inventory = @(
        foreach ($image in $allImages) {
            $imageInfo = docker image inspect $image --format '{{json .}}' | ConvertFrom-Json
            if ($LASTEXITCODE -ne 0) { throw "Missing image: $image. Build or pull it before exporting." }
            [ordered]@{
                reference = $image
                purpose = if ($image -in $runtimeImages) { 'runtime' } else { 'build' }
                id = $imageInfo.Id
                repoDigests = @($imageInfo.RepoDigests)
                sizeBytes = $imageInfo.Size
                createdAt = $imageInfo.Created
            }
        }
    )
    $archiveName = 'ecommerce-operation-assistant-images.tar'
    $archivePath = Join-Path $OutputDirectory $archiveName
    $partialPath = $archivePath + '.partial'
    try {
        docker image save --output $partialPath @allImages
        if ($LASTEXITCODE -ne 0) { throw 'Image export failed.' }
        Move-Item -LiteralPath $partialPath -Destination $archivePath -Force
    }
    finally {
        if (Test-Path -LiteralPath $partialPath) { Remove-Item -LiteralPath $partialPath }
    }
    $manifest = [ordered]@{
        schemaVersion = 1
        exportedAt = (Get-Date).ToUniversalTime().ToString('o')
        archive = $archiveName
        sha256 = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
        images = $inventory
    }
    $manifestPath = Join-Path $OutputDirectory '镜像清单.json'
    [System.IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 8), [System.Text.UTF8Encoding]::new($false))
    Write-Host "Exported $($allImages.Count) required images to $archivePath"
    Write-Host "Image IDs, roles and archive SHA256 recorded in $manifestPath"
}
finally { Pop-Location }
