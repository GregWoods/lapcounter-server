# One-command deployment of a new version to the race-meet Pi.
#
#   ./deploy/deploy.ps1                        # build+push everything, deploy, verify
#   ./deploy/deploy.ps1 -Services react,api    # only what changed (much faster)
#   ./deploy/deploy.ps1 -SkipBuild             # just pull+restart on the Pi
#   ./deploy/deploy.ps1 -VerifyOnly            # health check, change nothing
#
# Why this exists: a deployment is otherwise ~20 separate commands. Beyond the
# typing, each one is a separate approval prompt when driven by an agent.
#
# See deploy/race-network-setup.md for the network this deploys onto.

[CmdletBinding()]
param(
    # ble is deliberately excluded from the default list below: it's an
    # unapproved alternative to gpio (see deploy/compose.race.yaml), not part
    # of a normal full deploy. Select it explicitly with -Services ble.
    [ValidateSet('react', 'api', 'lapdata', 'gpio', 'dbwriter', 'ble')]
    [string[]]$Services = @('react', 'api', 'lapdata', 'gpio', 'dbwriter'),
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
    Step 'Deploying to the Pi'
    # `pull` is REQUIRED: compose uses pull_policy:missing and every service is
    # pinned to :latest, so `up -d` alone silently keeps the old images.
    ssh -o BatchMode=yes $PI 'cd /opt/lapcounter && docker compose pull && docker compose up -d'
    if ($LASTEXITCODE -ne 0) { throw 'Deployment failed on the Pi.' }
    Ok 'pull + up -d complete'
    Start-Sleep -Seconds 30
}

# ---------------------------------------------------------------- verify
Step 'Verifying'
$failed = @()

$state = ssh -o BatchMode=yes $PI 'docker compose -f /opt/lapcounter/compose.yaml ps --format "{{.Name}} {{.State}}"'
$down  = $state | Where-Object { $_ -notmatch 'running' }
if ($down) { $failed += "containers not running: $down" } else { Ok "all containers running" }

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
