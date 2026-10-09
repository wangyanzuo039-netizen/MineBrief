# Maintainer-only acceptance: an isolated Docker daemon with no project images or layers.
# The helper has no network and no host Docker socket; only this delivery folder is mounted.
[CmdletBinding()]
param([string]$PackagePath = '', [string]$HelperImage = 'docker.m.daocloud.io/library/docker:29-dind@sha256:1e08cdb63405ca788aea94ef35b792d1e299607c667d33d7bcbcae1fd2611ced')

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
if (-not $PackagePath) { $PackagePath = Join-Path $taskRoot 'dist\mining-brief-offline.zip' }
$taskRun = 'offline-cold-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 6)
$taskScratch = Join-Path (Join-Path $taskRoot 'tmp') $taskRun
$taskOutput = Join-Path (Join-Path $taskRoot 'outputs') $taskRun
$taskHelper = 'mining-brief-' + $taskRun.ToLowerInvariant()
$taskRecord = [ordered]@{
    tested_at = [DateTime]::UtcNow.ToString('o')
    test_kind = 'fresh isolated Docker daemon with empty image and layer storage'
    network = 'none'
    helper_image = $HelperImage
    prerequisites = 'Docker installed/running; delivery ZIP and test helper already on this machine'
    unzip_seconds = 0
    engine_setup_seconds = 0
    verification_seconds = 0
    image_import_seconds = 0
    report_seconds = 0
    total_seconds = 0
    exit_code = 1
}
$taskCreated = $false
$taskWatch = [Diagnostics.Stopwatch]::StartNew()
$taskPhase = [Diagnostics.Stopwatch]::StartNew()

function Invoke-TaskDocker {
    param([string[]]$DockerArguments)
    $taskLines = @(& docker @DockerArguments)
    if ($LASTEXITCODE -ne 0) { throw ('Docker command failed: ' + ($DockerArguments -join ' ')) }
    return $taskLines
}

try {
    New-Item -ItemType Directory -Path $taskOutput, $taskScratch -Force | Out-Null
    Expand-Archive -LiteralPath $PackagePath -DestinationPath $taskScratch
    $taskBundle = Join-Path $taskScratch 'mining-brief-offline'
    $taskRecord.unzip_seconds = [Math]::Round($taskPhase.Elapsed.TotalSeconds, 2)
    $taskPhase.Restart()
    $taskManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $taskBundle 'offline-manifest.json') | ConvertFrom-Json
    $taskMount = 'type=bind,source=' + $taskBundle + ',target=/bundle,readonly'
    Invoke-TaskDocker -DockerArguments @('run','--detach','--privileged','--network','none','--cpus','2','--memory','2g','--name',$taskHelper,'--env','DOCKER_TLS_CERTDIR=','--mount',$taskMount,$HelperImage,'--storage-driver=vfs','--iptables=false','--bridge=none','--ip-forward=false','--ip-masq=false') | Out-Null
    $taskCreated = $true
    $taskReady = $false
    for ($taskAttempt = 0; $taskAttempt -lt 40; $taskAttempt++) {
        # Poll only our newly created helper, without changing the main Docker context.
        & docker exec $taskHelper sh -c 'docker info >/dev/null 2>&1' | Out-Null
        if ($LASTEXITCODE -eq 0) { $taskReady = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $taskReady) { throw 'The isolated test daemon did not become ready.' }
    $taskRecord.engine_setup_seconds = [Math]::Round($taskPhase.Elapsed.TotalSeconds, 2)
    $taskImages = @(Invoke-TaskDocker -DockerArguments @('exec',$taskHelper,'docker','image','ls','--quiet','--all'))
    $taskRecord.images_before = $taskImages.Count
    if ($taskImages.Count -ne 0) { throw 'The test engine is not empty; this is not a valid cold test.' }

    $taskPhase.Restart()
    $taskHash = ((Invoke-TaskDocker -DockerArguments @('exec',$taskHelper,'sha256sum',('/bundle/' + $taskManifest.image_archive))) -join '').Split(' ')[0]
    if ($taskHash -ne $taskManifest.image_sha256) { throw 'Image archive checksum mismatch.' }
    $taskRecord.verification_seconds = [Math]::Round($taskPhase.Elapsed.TotalSeconds, 2)
    $taskPhase.Restart()
    Invoke-TaskDocker -DockerArguments @('exec',$taskHelper,'docker','image','load','--input',('/bundle/' + $taskManifest.image_archive)) | Out-Host
    $taskRecord.image_import_seconds = [Math]::Round($taskPhase.Elapsed.TotalSeconds, 2)
    $taskRecord.image_id = (Invoke-TaskDocker -DockerArguments @('exec',$taskHelper,'docker','image','inspect',$taskManifest.image_ref,'--format','{{.Id}}')) -join ''
    if (@($taskManifest.image_id, $taskManifest.image_config_id) -notcontains $taskRecord.image_id) {
        throw 'Imported image identity does not match the delivery manifest.'
    }
    # Engines may report an OCI index ID or its platform config ID; both are verified export identities.
    $taskRecord.expected_export_image_id = $taskManifest.image_id
    $taskPhase.Restart()
    Invoke-TaskDocker -DockerArguments @('exec',$taskHelper,'mkdir','-p','/work/outputs') | Out-Null
    Invoke-TaskDocker -DockerArguments @('exec',$taskHelper,'chown','10001:10001','/work/outputs') | Out-Null
    Invoke-TaskDocker -DockerArguments @('exec',$taskHelper,'cp','/bundle/compose.offline.yaml','/work/compose.offline.yaml') | Out-Null
    $taskRaw = Invoke-TaskDocker -DockerArguments @('exec','--workdir','/work',$taskHelper,'docker','compose','-f','compose.offline.yaml','run','--rm','agent')
    $taskSummary = ($taskRaw -join [Environment]::NewLine) | ConvertFrom-Json
    if ($taskSummary.overall_status -ne 'complete') { throw 'The offline briefing is incomplete.' }
    $taskRecord.report_seconds = [Math]::Round($taskPhase.Elapsed.TotalSeconds, 2)
    $taskRecord.run_id = $taskSummary.run_id
    $taskRecord.status = $taskSummary.overall_status
    $taskRecord.generation_mode = $taskSummary.generation_mode
    $taskWatch.Stop()
    $taskRecord.total_seconds = [Math]::Round($taskWatch.Elapsed.TotalSeconds, 2)
    $taskRecord.within_five_minutes = ($taskWatch.Elapsed.TotalSeconds -le 300)
    Invoke-TaskDocker -DockerArguments @('cp',($taskHelper + ':/work/outputs/.'),$taskOutput) | Out-Null
    if (-not $taskRecord.within_five_minutes) { throw 'The run succeeded but exceeded five minutes.' }
    $taskRecord.exit_code = 0
} catch {
    $taskWatch.Stop()
    $taskRecord.total_seconds = [Math]::Round($taskWatch.Elapsed.TotalSeconds, 2)
    $taskRecord.error = $_.Exception.Message
    Write-Host ('Cold verification failed: ' + $_.Exception.Message) -ForegroundColor Red
} finally {
    if ($taskCreated) {
        $ErrorActionPreference = 'Continue'
        & docker logs $taskHelper 2>&1 | Out-File -LiteralPath (Join-Path $taskOutput 'helper.log') -Encoding UTF8
        # This exact helper and its anonymous data volume belong only to this acceptance run.
        & docker rm --force --volumes $taskHelper | Out-Null
        $taskRecord.cleanup_exit_code = $LASTEXITCODE
    }
    $taskJson = $taskRecord | ConvertTo-Json -Depth 6
    [IO.File]::WriteAllText((Join-Path $taskOutput 'cold-startup.json'), $taskJson, (New-Object Text.UTF8Encoding $false))
    Write-Host $taskJson
}
exit $taskRecord.exit_code
