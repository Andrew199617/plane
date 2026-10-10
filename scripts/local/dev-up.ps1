<#
.SYNOPSIS
  Start the local Plane dev stack (backend in Docker, frontends on the Windows host), detached.

.DESCRIPTION
  Idempotent: anything already running is left alone.
    - Docker compose project "plane" (docker-compose-local.yml): api :8300, postgres :55432,
      redis :56379, minio :9300 (console :9390), rabbitmq (no host port), worker, beat-worker, migrator.
    - Host dev servers, each started fully detached (survives the calling shell) via Win32_Process.Create:
        packages  turbo "dev" for ./packages/* (tsdown --watch, rebuilds dist/ on edit)
        web-dev   http://localhost:3310 (Vite dev server with HMR; NEVER on 3300)
        admin     http://localhost:3301/god-mode/
        space     http://localhost:3302/spaces/
        live      http://localhost:3400/live/
  Logs: .devlogs\<name>.log   PIDs: .devlogs\pids\<name>.pid
    - Production web build on http://localhost:3300: Caddy container "plane-web-prod" (scripts\local\web-prod.ps1),
      optionally exposed to other devices via Tailscale serve or any reverse proxy (see -PublicHost). If the
      container is missing or stopped it is (re)started from the LAST build (web-prod.ps1 -NoBuild; a first build
      if none exists). It is a snapshot: rebuild with  powershell -ExecutionPolicy Bypass -File scripts\local\web-prod.ps1

  Only touches the compose project "plane", the plane-web-prod container and Plane's own dev servers; the
  host ports are chosen to avoid the common defaults (3000, 4200, 5432, 6379, 8000, 9000).

.PARAMETER Build
  Rebuild the backend images (docker compose up --build).
.PARAMETER BackendOnly
  Only start the docker compose stack.
.PARAMETER FrontendOnly
  Only start the host dev servers.
.PARAMETER RecoverDocker
  If Docker Desktop is not responding, apply the Docker Desktop stale-socket recovery (stop Docker processes,
  rename %LOCALAPPDATA%\Docker\run and %LOCALAPPDATA%\docker-secrets-engine to *.stale-<timestamp>, relaunch).
.PARAMETER PublicHost
  Host name under which other devices reach the production web build on port 3300 (e.g. a Tailscale or LAN
  name); only used for the summary. Defaults to $env:PLANE_PUBLIC_HOST (no default otherwise).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\local\dev-up.ps1
#>
[CmdletBinding()]
param(
  [switch]$Build,
  [switch]$BackendOnly,
  [switch]$FrontendOnly,
  [switch]$RecoverDocker,
  [string]$PublicHost = $env:PLANE_PUBLIC_HOST
)

# 'Continue' (not 'Stop'): under Windows PowerShell 5.1, stderr from native tools (docker, pnpm) can surface as
# terminating NativeCommandErrors. Failures are checked explicitly via $LASTEXITCODE and throw.
$ErrorActionPreference = 'Continue'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$LogDir = Join-Path $Root '.devlogs'
$PidDir = Join-Path $LogDir 'pids'
$Compose = Join-Path $Root 'docker-compose-local.yml'
New-Item -ItemType Directory -Force $LogDir, $PidDir | Out-Null

function Write-Step([string]$msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

function Test-PortListening([int]$Port) {
  $c = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
  return [bool]$c
}

function Test-DockerUp {
  $p = Start-Process -FilePath 'docker' -ArgumentList 'info', '--format', '{{.ServerVersion}}' -NoNewWindow -PassThru `
    -RedirectStandardOutput (Join-Path $LogDir 'docker-info.out') -RedirectStandardError (Join-Path $LogDir 'docker-info.err')
  $null = $p.Handle  # cache the handle, otherwise ExitCode is $null on Windows PowerShell 5.1
  if (-not $p.WaitForExit(20000)) { try { $p.Kill() } catch {} ; return $false }
  $p.WaitForExit()
  return ($p.ExitCode -eq 0)
}

function Repair-DockerDesktop {
  Write-Step 'Docker is not responding - applying stale-socket recovery'
  Get-Process -Name 'Docker Desktop', 'com.docker.backend', 'com.docker.build', 'com.docker.dev-envs', 'docker-sandbox', 'com.docker.proxy' -ErrorAction SilentlyContinue |
    Stop-Process -Force -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 3
  $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
  foreach ($d in @((Join-Path $env:LOCALAPPDATA 'Docker\run'), (Join-Path $env:LOCALAPPDATA 'docker-secrets-engine'))) {
    if (Test-Path $d) { Rename-Item -Path $d -NewName ((Split-Path $d -Leaf) + ".stale-$stamp") -ErrorAction Stop }
  }
  Start-Process -FilePath 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
  $deadline = (Get-Date).AddMinutes(4)
  while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 5
    if (Test-DockerUp) { Write-Host 'Docker is back.'; return }
  }
  throw 'Docker Desktop did not come back within 4 minutes.'
}

function Get-PidFile([string]$Name) { Join-Path $PidDir "$Name.pid" }

function Test-Tracked([string]$Name) {
  $f = Get-PidFile $Name
  if (-not (Test-Path $f)) { return $false }
  $procId = [int](Get-Content $f -Raw).Trim()
  return [bool](Get-Process -Id $procId -ErrorAction SilentlyContinue)
}

# Start a command fully detached from this shell (and from any job object it runs in) via WMI.
function Start-Detached([string]$Name, [string]$WorkDir, [string]$CommandLine) {
  $log = Join-Path $LogDir "$Name.log"
  Add-Content -Path $log -Value ("`r`n===== {0} starting: {1} =====" -f (Get-Date -Format s), $CommandLine)
  $full = 'cmd.exe /d /s /c "' + $CommandLine + ' >> "' + $log + '" 2>&1"'
  # Pass this shell's environment explicitly so PATH (node, pnpm) matches the caller.
  $envBlock = @(Get-ChildItem Env: | Where-Object { $_.Name -notmatch '^=' } | ForEach-Object { "$($_.Name)=$($_.Value)" })
  $startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow = [uint16]0; EnvironmentVariables = [string[]]$envBlock }
  $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = $full; CurrentDirectory = $WorkDir; ProcessStartupInformation = $startup
  }
  if ($r.ReturnValue -ne 0) { throw "Failed to start $Name (Win32_Process.Create returned $($r.ReturnValue))" }
  Set-Content -Path (Get-PidFile $Name) -Value $r.ProcessId
  Write-Host ("    started {0} (pid {1}) -> {2}" -f $Name, $r.ProcessId, $log)
}

function Wait-Http([string]$Url, [int]$TimeoutSec) {
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5 -MaximumRedirection 0 -ErrorAction Stop
      return $resp.StatusCode
    } catch {
      if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
    }
    Start-Sleep -Seconds 2
  }
  return 0
}

# ---------------------------------------------------------------- preflight
foreach ($f in @('.env', 'apps\api\.env', 'apps\web\.env', 'apps\admin\.env', 'apps\space\.env', 'apps\live\.env')) {
  if (-not (Test-Path (Join-Path $Root $f))) { throw "Missing $f - create it from the matching .env.example first (see setup.sh)." }
}

# ---------------------------------------------------------------- backend
if (-not $FrontendOnly) {
  Write-Step 'Checking Docker'
  if (-not (Test-DockerUp)) {
    if ($RecoverDocker) { Repair-DockerDesktop } else { throw 'Docker is not responding. Start Docker Desktop, or re-run with -RecoverDocker.' }
  }
  Write-Step 'Starting backend (docker compose project "plane")'
  $composeArgs = @('compose', '-p', 'plane', '-f', $Compose, 'up', '-d')
  if ($Build) { $composeArgs += '--build' }
  & docker @composeArgs
  if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed' }
  Write-Step 'Waiting for api on http://localhost:8300 ...'
  $code = Wait-Http 'http://localhost:8300/api/instances/' 180
  if ($code -eq 0) { Write-Warning 'api did not answer within 180s - check: docker logs plane-api-1' } else { Write-Host "    api answered HTTP $code" }
}

# ---------------------------------------------------------------- frontends
if (-not $BackendOnly) {
  if (-not (Test-Path (Join-Path $Root 'node_modules'))) {
    Write-Step 'pnpm install'
    Push-Location $Root; try { & pnpm install; if ($LASTEXITCODE -ne 0) { throw 'pnpm install failed' } } finally { Pop-Location }
  }
  $env:TURBO_TELEMETRY_DISABLED = '1'
  $env:DO_NOT_TRACK = '1'
  # web-dev serves the app same-origin: it proxies /api, /auth, /static, /live and /uploads (MinIO :9300) and the
  # client uses relative URLs (apps/web/vite.config.ts; only read by the web dev server, never by builds).
  $env:PLANE_WEB_DEV_PROXY = '1'
  $env:PLANE_WEB_UPLOADS_PROXY_TARGET = 'http://127.0.0.1:9300'
  if (-not (Test-Path (Join-Path $Root 'packages\utils\dist'))) {
    Write-Step 'Building workspace packages (first run)'
    Push-Location $Root; try { & pnpm turbo run build --filter=./packages/*; if ($LASTEXITCODE -ne 0) { throw 'package build failed' } } finally { Pop-Location }
  }

  Write-Step 'Starting host dev servers'
  if (Test-Tracked 'packages') { Write-Host '    packages watcher already running' }
  else { Start-Detached 'packages' $Root 'pnpm turbo run dev --filter=./packages/* --concurrency=20 --ui=stream'; Start-Sleep -Seconds 8 }

  $apps = @(
    # Port 3300 belongs to the production build (plane-web-prod); the dev server lives on 3310.
    @{ Name = 'web-dev'; Port = 3310; Dir = 'apps\web'; Cmd = 'pnpm exec react-router dev --port 3310 --strictPort' },
    @{ Name = 'admin'; Port = 3301; Dir = 'apps\admin'; Cmd = 'pnpm exec react-router dev --port 3301 --strictPort' },
    @{ Name = 'space'; Port = 3302; Dir = 'apps\space'; Cmd = 'pnpm exec react-router dev --port 3302 --strictPort' },
    # live reads PORT=3400 from apps/live/.env (node --env-file=.env)
    @{ Name = 'live';  Port = 3400; Dir = 'apps\live';  Cmd = 'pnpm run dev' }
  )
  foreach ($a in $apps) {
    if ((Test-PortListening $a.Port) -or (Test-Tracked $a.Name)) { Write-Host ("    {0} already running (:{1})" -f $a.Name, $a.Port); continue }
    Start-Detached $a.Name (Join-Path $Root $a.Dir) $a.Cmd
  }

  Write-Step 'Production web (plane-web-prod on :3300)'
  $webProd = Join-Path $PSScriptRoot 'web-prod.ps1'
  $running = (& docker inspect -f '{{.State.Running}}' plane-web-prod 2>$null)
  if ($running -eq 'true') { Write-Host '    plane-web-prod already running (:3300)' }
  elseif (Test-Path (Join-Path $Root 'apps\web\build\client\index.html')) {
    Write-Host '    starting plane-web-prod from the last build (web-prod.ps1 -NoBuild)'
    & powershell -NoProfile -ExecutionPolicy Bypass -File $webProd -NoBuild
  } else {
    Write-Host '    no production build yet - building it (web-prod.ps1, ~1 min)'
    & powershell -NoProfile -ExecutionPolicy Bypass -File $webProd
  }

  Write-Step 'Waiting for web servers'
  foreach ($u in @('http://localhost:3300/', 'http://localhost:3310/', 'http://localhost:3301/god-mode/', 'http://localhost:3302/spaces/', 'http://localhost:3400/live/health')) {
    $c = Wait-Http $u 180
    Write-Host ("    {0} -> {1}" -f $u, $(if ($c -eq 0) { 'no answer yet (see .devlogs)' } else { "HTTP $c" }))
  }
}

Write-Host ''
Write-Host 'Plane local dev:' -ForegroundColor Green
Write-Host '  web    http://localhost:3300  (production snapshot)'
if ($PublicHost) { Write-Host "         http://${PublicHost}:3300  (remote)" }
Write-Host '  dev    http://localhost:3310  (Vite dev server, HMR)'
Write-Host '  admin  http://localhost:3301/god-mode/'
Write-Host '  space  http://localhost:3302/spaces/'
Write-Host '  live   http://localhost:3400/live/'
Write-Host '  api    http://localhost:8300'
Write-Host "  logs   $LogDir"
