param([string]$InputDirectory)
$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
if (-not $InputDirectory) {
    $InputDirectory = Join-Path (Split-Path -Parent $repositoryRoot) '镜像'
}
$InputDirectory = [System.IO.Path]::GetFullPath($InputDirectory)
$manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $InputDirectory '镜像清单.json') | ConvertFrom-Json
if ($manifest.schemaVersion -ne 1 -or [System.IO.Path]::GetFileName($manifest.archive) -ne $manifest.archive) {
    throw 'Unsupported image manifest or invalid archive name.'
}
$archivePath = Join-Path $InputDirectory $manifest.archive
$actualHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -cne $manifest.sha256) { throw 'Archive SHA256 does not match the manifest.' }
docker image load --input $archivePath
if ($LASTEXITCODE -ne 0) { throw 'Image import failed.' }
foreach ($image in $manifest.images) {
    $actualId = docker image inspect $image.reference --format '{{.Id}}'
    if ($LASTEXITCODE -ne 0 -or $actualId -cne $image.id) { throw "Image verification failed: $($image.reference)" }
}
Write-Host "Imported and verified $($manifest.images.Count) images. Initialize .env and run docker compose up -d --no-build --pull never."
