[CmdletBinding()]
param([switch]$ForceImport)

$ErrorActionPreference = 'Stop'
$taskWatch = [System.Diagnostics.Stopwatch]::StartNew()
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskOutput = Join-Path $taskRoot 'outputs'
$taskRecord = [ordered]@{
    started_at = [DateTime]::UtcNow.ToString('o')
    measurement = 'script entry, archive verification, optional image import, and report generation'
    image_imported = $false
    image_existed_before = $false
    existing_layer_cache = 'not measured; see independent empty-engine acceptance record'
    verify_seconds = 0
    import_seconds = 0
    run_seconds = 0
    total_seconds = 0
    exit_code = 1
}

try {
    Set-Location -LiteralPath $taskRoot
    New-Item -ItemType Directory -Path $taskOutput -Force | Out-Null
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker is not installed. Install and start Docker Desktop, then run again.'
    }
    $taskEngine = & docker info --format '{{.OSType}}' 2>$null
    if ($LASTEXITCODE -ne 0 -or $taskEngine -ne 'linux') {
        throw 'Start Docker Desktop and select Linux containers, then run again.'
    }
    & docker compose version | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose is unavailable. Update Docker Desktop.' }

    $taskManifestPath = Join-Path $taskRoot 'offline-manifest.json'
    if (-not (Test-Path -LiteralPath $taskManifestPath)) {
        throw 'This is the source package. Extract mining-brief-offline.zip and run its start-offline.cmd.'
    }
    $taskManifest = Get-Content -LiteralPath $taskManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $taskExpectedIds = @($taskManifest.image_id, $taskManifest.image_config_id)
    $taskArchive = [IO.Path]::GetFullPath((Join-Path $taskRoot $taskManifest.image_archive))
    $taskBoundary = [IO.Path]::GetFullPath($taskRoot).TrimEnd('\') + '\'
    if (-not $taskArchive.StartsWith($taskBoundary, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'The image archive must be inside this delivery folder.'
    }
    if (-not (Test-Path -LiteralPath $taskArchive -PathType Leaf)) {
        throw 'Image archive is missing. Extract the complete offline delivery package.'
    }
    $taskPhase = [Diagnostics.Stopwatch]::StartNew()
    Write-Host '[1/3] Verifying the included runtime archive...'
    $taskHashStream = [IO.File]::OpenRead($taskArchive)
    $taskHasher = [Security.Cryptography.SHA256]::Create()
    try {
        $taskHash = [BitConverter]::ToString($taskHasher.ComputeHash($taskHashStream)).Replace('-', '').ToLowerInvariant()
    } finally {
        $taskHashStream.Dispose()
        $taskHasher.Dispose()
    }
    if ($taskHash -ne $taskManifest.image_sha256) { throw 'Image archive checksum mismatch.' }
    $taskRecord.verify_seconds = [Math]::Round($taskPhase.Elapsed.TotalSeconds, 2)

    # Listing local images avoids treating a missing image as a PowerShell native error.
    $taskExisting = @(& docker image ls --quiet --no-trunc $taskManifest.image_ref)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect local Docker images.' }
    $taskRecord.image_existed_before = ($taskExisting.Count -gt 0)
    $taskMatches = @($taskExisting | Where-Object { $taskExpectedIds -contains $_ })
    $taskMustImport = $ForceImport -or ($taskMatches.Count -eq 0)
    if ($taskMustImport) {
        $taskPhase.Restart()
        Write-Host '[2/3] Importing the runtime (no download needed)...'
        & docker image load --input $taskArchive
        if ($LASTEXITCODE -ne 0) { throw 'Image import failed. Check Docker disk space.' }
        $taskRecord.image_imported = $true
        $taskRecord.import_seconds = [Math]::Round($taskPhase.Elapsed.TotalSeconds, 2)
    } else {
        Write-Host '[2/3] The verified runtime is already installed.'
    }
    $taskLoadedId = & docker image inspect $taskManifest.image_ref --format '{{.Id}}'
    if ($LASTEXITCODE -ne 0 -or $taskExpectedIds -notcontains $taskLoadedId) {
        throw 'The loaded image ID does not match the delivery manifest.'
    }
    $taskPhase.Restart()
    Write-Host '[3/3] Generating the briefing through three MCP servers...'
    $taskRaw = @(& docker compose -f compose.offline.yaml run --rm agent)
    $taskExit = $LASTEXITCODE
    $taskRecord.run_seconds = [Math]::Round($taskPhase.Elapsed.TotalSeconds, 2)
    $taskRaw | ForEach-Object { Write-Host $_ }
    if ($taskExit -ne 0) { throw ('Agent failed with exit code ' + $taskExit) }
    $taskSummary = ($taskRaw -join [Environment]::NewLine) | ConvertFrom-Json
    if ($taskSummary.overall_status -ne 'complete' -or $taskSummary.run_id -notmatch '^[0-9TZ]+-[a-f0-9]{8}$') {
        throw 'The Agent did not return a complete briefing.'
    }
    $taskBrief = Join-Path (Join-Path $taskOutput $taskSummary.run_id) 'brief.md'
    if (-not (Test-Path -LiteralPath $taskBrief -PathType Leaf)) { throw 'The output file is missing.' }
    $taskRecord.run_id = $taskSummary.run_id
    $taskRecord.markdown = $taskBrief
    $taskRecord.exit_code = 0
    Write-Host ('Success. Open this report: ' + $taskBrief)
} catch {
    $taskRecord.error = $_.Exception.Message
    Write-Host ('Failed: ' + $_.Exception.Message) -ForegroundColor Red
} finally {
    $taskWatch.Stop()
    $taskRecord.total_seconds = [Math]::Round($taskWatch.Elapsed.TotalSeconds, 2)
    if (Test-Path -LiteralPath $taskOutput) {
        $taskJson = $taskRecord | ConvertTo-Json -Depth 5
        [IO.File]::WriteAllText((Join-Path $taskOutput 'offline-startup.json'), $taskJson, (New-Object Text.UTF8Encoding $false))
    }
    Write-Host ('Elapsed: ' + $taskRecord.total_seconds + ' seconds')
}
exit $taskRecord.exit_code
