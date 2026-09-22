# One-command deployment of a new version to the race-meet Pi.
#
#   ./deploy/deploy.ps1                        # build+push everything, deploy, verify
#   ./deploy/deploy.ps1 -Services react,api    # only what changed (much faster)
#   ./deploy/deploy.ps1 -SkipBuild             # just pull+restart on the Pi
#   ./deploy/deploy.ps1 -VerifyOnly            # health check, change nothing
#   ./deploy/deploy.ps1 -Layer1 gpio -Services gpio   # fall back to GPIO sensors
#
# Why this exists: a deployment is otherwise ~20 separate commands. Beyond the
# typing, each one is a separate approval prompt when driven by an agent.
#
# See deploy/race-network-setup.md for the network this deploys onto.

[CmdletBinding()]
param(
    # gpio is excluded from the default list to match -Layer1: a normal deploy
    # builds ble. Deploying a gpio change needs -Services gpio -Layer1 gpio.
    [ValidateSet('react', 'api', 'lapdata', 'gpio', 'dbwriter', 'ble')]
    [string[]]$Services = @('react', 'api', 'lapdata', 'ble', 'dbwriter'),

    # Which Layer 1 publishes car_timestamp. Exactly one may run - two of them
    # double-counts every lap. ble is the default; gpio is the fallback to the
    # physical finish-line sensors if the powerbase misbehaves at a meet.
    [ValidateSet('ble', 'gpio')]
    [string]$Layer1 = 'ble',

    [switch]$SkipBuild,
    [switch]$VerifyOnly
)

$ErrorActionPreference = 'Stop'

$PI       = 'greg@192.168.8.3'
$PUCK     = 'root@192.168.8.1'
$API_URL  = 'http://192.168.8.3:8000'
$APP_URL  = 'http://192.168.8.3:8087'
$REPO     = Split-Path $PSScriptRoot -Parent

# Build scripts live beside the code they build, not in deploy/.
$BuildScripts = @{
    react    = 'react\build-and-push-react.ps1'
    api      = 'api\build-and-push-api.ps1'
    lapdata  = 'lapdata\build-and-push-lapdata.ps1'
    gpio     = 'gpio\build-and-push-gpio.ps1'
    dbwriter = 'dbwriter\build-and-push-dbwriter.ps1'
    ble      = 'ble\build-and-push-ble.ps1'
}

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "    OK  $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "    !!  $msg" -ForegroundColor Yellow }

# ---------------------------------------------------------------- preflight
Step 'Preflight'

if (-not $VerifyOnly -and -not $SkipBuild) {
    docker info --format '{{.ServerVersion}}' *>$null
    if ($LASTEXITCODE -ne 0) { throw 'Docker engine is not running. Start Docker Desktop first.' }
    Ok 'docker engine up'

    # The puck must be in BUILD mode or DNS resolves every name to the router
    # itself, and `docker push` fails with "lookup registry-1.docker.io: no such
    # host". Plugging the WAN cable in switches automatically (~5s).
    $mode = ssh -o BatchMode=yes $PUCK 'portal-mode status' 2>$null
    if ($LASTEXITCODE -eq 0) {
        if ($mode -match 'race') {
            throw "Puck is in RACE mode - DNS is hijacked and pushes will fail.`n" +
                  "Plug the WAN cable in (auto-switches in ~5s), or: ssh $PUCK 'portal-mode off'"
        }
        Ok "puck: $mode"
    } else {
        Warn 'puck unreachable - skipping mode check (fine if building off-site)'
    }
}

ssh -o BatchMode=yes -o ConnectTimeout=8 $PI 'true' 2>$null
if ($LASTEXITCODE -ne 0) { throw "Cannot reach the Pi at $PI." }
Ok 'pi reachable'

# ---------------------------------------------------------------- build
if (-not $VerifyOnly -and -not $SkipBuild) {
    foreach ($svc in $Services) {
        Step "Building + pushing: $svc"
        $script = Join-Path $REPO $BuildScripts[$svc]
        Push-Location (Split-Path $script -Parent)
        try {
            & $script
            if ($LASTEXITCODE -ne 0) { throw "$svc build failed (exit $LASTEXITCODE)" }
            Ok "$svc pushed"
        } finally { Pop-Location }
    }
}

# ---------------------------------------------------------------- deploy
if (-not $VerifyOnly) {
    Step "Deploying to the Pi (Layer 1: $Layer1)"

    # The Layer 1 we are NOT using has to be stopped explicitly, and it has to
    # happen AFTER `up -d`, not before:
    #   - ble is unprofiled, so `--profile gpio up -d` starts it too; stopping it
    #     first would just see it come straight back.
    #   - gpio is profiled out on a ble deploy, but compose leaves an already-running
    #     profiled-out service RUNNING rather than removing it.
    # Either way the failure mode is two publishers on car_timestamp and every lap
    # counted twice. The brief overlap during `up -d` is harmless - no race is live
    # mid-deploy - and the verify step below confirms the end state.
    $profileArg = if ($Layer1 -eq 'gpio') { '--profile gpio ' } else { '' }
    $stale      = if ($Layer1 -eq 'gpio') { 'ble' } else { 'gpio-1 gpio-2' }

    # `pull` is REQUIRED: compose uses pull_policy:missing and every service is
    # pinned to :latest, so `up -d` alone silently keeps the old images.
    ssh -o BatchMode=yes $PI "cd /opt/lapcounter && docker compose ${profileArg}pull && docker compose ${profileArg}up -d && (docker stop $stale 2>/dev/null || true)"
    if ($LASTEXITCODE -ne 0) { throw 'Deployment failed on the Pi.' }
    Ok "pull + up -d complete (layer 1: $Layer1, stopped: $stale)"
    Start-Sleep -Seconds 30
}

# ---------------------------------------------------------------- verify
Step 'Verifying'
$failed = @()

# $profileArg matters here too: without it `ps` omits the gpio services entirely on a
# -Layer1 gpio deploy, so a dead gpio-1 would sail through this check.
$profileArg = if ($Layer1 -eq 'gpio') { '--profile gpio ' } else { '' }
$state = ssh -o BatchMode=yes $PI "docker compose -f /opt/lapcounter/compose.yaml ${profileArg}ps --format '{{.Name}} {{.State}}'"
$down  = $state | Where-Object { $_ -notmatch 'running' }
if ($down) { $failed += "containers not running: $down" } else { Ok "all containers running" }

# Exactly one Layer 1, and the one we asked for. Two publishers on car_timestamp
# double-counts every lap, and the symptom at a meet looks like a timing fault
# rather than a deploy fault - so fail the deploy here instead.
$expected = if ($Layer1 -eq 'gpio') { @('gpio-1', 'gpio-2') } else { @('ble') }
$running  = @(ssh -o BatchMode=yes $PI "docker ps --filter name='^ble$' --filter name='^gpio-1$' --filter name='^gpio-2$' --format '{{.Names}}'") |
            Where-Object { $_ }
if (Compare-Object $running $expected) {
    $failed += "Layer 1 mismatch: expected '$expected' running, found '$running'"
} else {
    Ok "layer 1: $Layer1 ($running)"
}

# "running" is NOT the same as "can count a lap". A ble container that never finds
# the powerbase sits there retrying forever and still reports as running, so without
# this the script cheerfully prints "Deployment verified." for a stack that cannot
# time a single lap. A WARNING not a failure: deploying from the workshop with the
# powerbase switched off is entirely normal.
if ($Layer1 -eq 'ble' -and $running -contains 'ble') {
    $bleLog = ssh -o BatchMode=yes $PI 'docker logs --tail 50 ble 2>&1'
    if ($bleLog -match 'Connected to Scalextric ARC powerbase') {
        Ok 'ble: connected to the powerbase'
    } else {
        Warn 'ble is running but has NOT connected to a powerbase. Fine if it is powered'
        Warn 'off; if not, check it is in range and awake - there will be no lap timing.'
        Warn 'Last line: ' + ($bleLog | Select-Object -Last 1)
    }
}

try {
    $routes = (Invoke-RestMethod "$API_URL/openapi.json" -TimeoutSec 30).paths.PSObject.Properties.Name.Count
    if ($routes -lt 30) { $failed += "API only exposes $routes routes - stale image?" }
    else { Ok "api: $routes routes" }
} catch { $failed += "api unreachable: $_" }

try {
    $app = (Invoke-WebRequest "$APP_URL/currentrace" -TimeoutSec 30 -SkipHttpErrorCheck).StatusCode
    if ($app -ne 200) { $failed += "app returned $app" } else { Ok 'react serving /currentrace' }
} catch { $failed += "app unreachable: $_" }

if (-not (Test-NetConnection 192.168.8.3 -Port 8080 -InformationLevel Quiet -WarningAction SilentlyContinue)) {
    $failed += 'MQTT websocket 8080 not reachable'
} else { Ok 'mqtt websocket 8080 open' }

Write-Host ''
if ($failed) {
    Write-Host 'DEPLOY FAILED VERIFICATION:' -ForegroundColor Red
    $failed | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}

Write-Host 'Deployment verified.' -ForegroundColor Green
Write-Host ''
Write-Host 'Before the meet:' -ForegroundColor Yellow
Write-Host '  1. Unplug the WAN cable (puck switches to race mode in ~5s)'
Write-Host "  2. Open $APP_URL/ on the laptop and SYNC THE CLOCK - there is no"
Write-Host '     NTP offline and the Pi has no RTC, so lap timestamps depend on it'
