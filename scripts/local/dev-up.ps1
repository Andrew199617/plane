<#
.SYNOPSIS
  Start the DEBUG Plane stack (backend in Docker, frontends on the Windows host), detached.

.DESCRIPTION
  DEBUG stack only: a disposable copy that runs this working tree. See AGENTS.md "Local environment" before
  touching Docker, ports or env files. RELEASE (compose project "plane", plane-release-* containers, the owner's
  real data on http://localhost:3300 and the phone link) is NEVER started, stopped or changed by this script;
  it is driven only by scripts\local\release.ps1.

  Idempotent: anything already running is left alone.
    - Docker compose project "plane-dev" (docker-compose-local.yml, volumes plane-dev_*), all bound to 127.0.0.1:
        api       http://127.0.0.1:8310   (runserver, plane.settings.local, source bind-mounted)
        postgres  127.0.0.1:55433
        redis     127.0.0.1:56380
        minio     127.0.0.1:9310 (console 9391)
        rabbitmq  no host port;  worker (concurrency 2), beat-worker, migrator
    - Host dev servers, each started fully detached (survives the calling shell) via Win32_Process.Create:
        packages  turbo "dev" for ./packages/* (tsdown --watch, rebuilds dist/ on edit)
        web-dev   http://127.0.0.1:3310 (Vite dev server with HMR; NEVER on 3300, which is RELEASE)
        admin     http://127.0.0.1:3301/god-mode/
        space     http://127.0.0.1:3302/spaces/
        live      http://127.0.0.1:3400/live/
  Logs: .devlogs\<name>.log   PIDs: .devlogs\pids\<name>.pid
  Open debug on 127.0.0.1 (release on localhost) so the two stacks' browser cookies do not clash.
  Empty debug database? Seed it from release with scripts\local\dev-refresh.ps1.

  Preflight refuses to start while the debug env files still carry release values (CORS/WEB_URL on :3300,
  API URLs on the retired :8300, or no SESSION_COOKIE_NAME in apps\api\.env); see AGENTS.md.

.PARAMETER Build
  Rebuild the backend images (docker compose up --build).
.PARAMETER BackendOnly
  Only start the docker compose stack.
.PARAMETER FrontendOnly
  Only start the host dev servers.
.PARAMETER RecoverDocker
  If Docker Desktop is not responding, apply the Docker Desktop stale-socket recovery (stop Docker processes,
  rename %LOCALAPPDATA%\Docker\run and %LOCALAPPDATA%\docker-secrets-engine to *.stale-<timestamp>, relaunch).
  Runs before the debug env preflight, so it also works while the debug env files would be refused.
.PARAMETER PublicHost
  Host name under which other devices (the phone) reach RELEASE on port 3300 (e.g. a Tailscale name); only
  printed in the summary as the release phone URL - this script never touches release. Defaults to
  $env:PLANE_PUBLIC_HOST (no default otherwise).

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

# KEY=VALUE lines of a dotenv file as a hashtable (surrounding quotes stripped). Values are never printed.
function Read-DotEnv([string]$Path) {
  $h = @{}
  if (-not (Test-Path $Path)) { return $h }
  foreach ($line in Get-Content -Path $Path) {
    $t = $line.Trim()
    if (-not $t -or $t.StartsWith('#')) { continue }
    if ($t.StartsWith('export ')) { $t = $t.Substring(7).TrimStart() }
    $i = $t.IndexOf('=')
    if ($i -lt 1) { continue }
    $v = $t.Substring($i + 1).Trim()
    if ($v.Length -ge 2 -and (($v.StartsWith('"') -and $v.EndsWith('"')) -or ($v.StartsWith("'") -and $v.EndsWith("'")))) { $v = $v.Substring(1, $v.Length - 2) }
    $h[$t.Substring(0, $i).Trim()] = $v
  }
  return $h
}

# ---------------------------------------------------------------- docker recovery (before the env preflight)
# Recovering Docker Desktop does not depend on the debug env files, and release recovery (AGENTS.md, release.ps1)
# points here: never let a debug env problem block it.
if ($RecoverDocker -and -not (Test-DockerUp)) { Repair-DockerDesktop }

# ---------------------------------------------------------------- preflight
foreach ($f in @('.env', 'apps\api\.env', 'apps\web\.env', 'apps\admin\.env', 'apps\space\.env', 'apps\live\.env')) {
  if (-not (Test-Path (Join-Path $Root $f))) { throw "Missing $f - create it from the matching .env.example first (see setup.sh)." }
}
# The debug env files must not carry RELEASE values (:3300) or the retired pre-split ports, otherwise debug
# would authenticate/redirect against release or talk to the wrong services. Only key names are reported.
$retiredPorts = ':(3300|8300|55432|56379|9300|9390)(?!\d)'
$envProblems = @()
$apiEnv = Read-DotEnv (Join-Path $Root 'apps\api\.env')
if ([string]$apiEnv['CORS_ALLOWED_ORIGINS'] -match ':3300(?!\d)') { $envProblems += 'apps\api\.env: CORS_ALLOWED_ORIGINS lists :3300 (release) origins' }
foreach ($k in 'WEB_URL', 'APP_BASE_URL') {
  if ([string]$apiEnv[$k] -match ':3300/?$') { $envProblems += "apps\api\.env: $k points at :3300 (release)" }
}
if (-not $apiEnv.ContainsKey('SESSION_COOKIE_NAME') -or -not $apiEnv['SESSION_COOKIE_NAME']) {
  $envProblems += 'apps\api\.env: SESSION_COOKIE_NAME is missing (debug must not share the release session-id cookie)'
}
foreach ($app in 'web', 'admin', 'space', 'live') {
  $appEnv = Read-DotEnv (Join-Path $Root "apps\$app\.env")
  # The keys each app really reads in dev: VITE_*_URL for the Vite apps; live ignores its WEB_/LIVE_BASE_URL.
  if ($app -eq 'live') { $keys = @('API_BASE_URL', 'REDIS_URL') }
  else { $keys = @($appEnv.Keys | Where-Object { $_ -match '^VITE_\w*_URL$' } | Sort-Object) }
  foreach ($k in $keys) {
    if ([string]$appEnv[$k] -match $retiredPorts) { $envProblems += "apps\$app\.env: $k points at release (:3300) or a retired port (:8300/:55432/:56379/:9300/:9390)" }
  }
  if ($app -eq 'live' -and [string]$appEnv['REDIS_PORT'] -eq '56379') { $envProblems += 'apps\live\.env: REDIS_PORT is the retired 56379 (debug redis is 56380)' }
}
if ($envProblems.Count -gt 0) {
  Write-Host 'Refusing to start the DEBUG stack - its env files still hold release / pre-split values:' -ForegroundColor Red
  $envProblems | ForEach-Object { Write-Host "  - $_" }
  throw ('Point the debug env files at the debug ports (API 127.0.0.1:8310, web 3310, admin 3301, space 3302, live 3400, ' +
    'redis 56380) and set SESSION_COOKIE_NAME=plane-dev-session-id in apps\api\.env. See AGENTS.md "Local environment".')
}

# ---------------------------------------------------------------- backend
if (-not $FrontendOnly) {
  Write-Step 'Checking Docker'
  if (-not (Test-DockerUp)) {
    if ($RecoverDocker) { Repair-DockerDesktop } else { throw 'Docker is not responding. Start Docker Desktop, or re-run with -RecoverDocker.' }
  }
  Write-Step 'Starting backend (docker compose project "plane-dev")'
  $composeArgs = @('compose', '-p', 'plane-dev', '-f', $Compose, 'up', '-d')
  if ($Build) { $composeArgs += '--build' }
  & docker @composeArgs
  if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed' }
  Write-Step 'Waiting for api on http://127.0.0.1:8310 ...'
  $code = Wait-Http 'http://127.0.0.1:8310/api/instances/' 180
  if ($code -eq 0) { Write-Warning 'api did not answer within 180s - check: docker logs plane-dev-api-1' } else { Write-Host "    api answered HTTP $code" }
  # An empty debug database is almost always unintended: seed it from release.
  $wsCount = ('select count(*) from workspaces;' | & docker exec -i plane-dev-plane-db-1 sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -At' 2>$null)
  if ("$wsCount".Trim() -eq '0') {
    Write-Host '    the debug database has no workspaces - run: powershell -ExecutionPolicy Bypass -File scripts\local\dev-refresh.ps1' -ForegroundColor Yellow
  }
}

# ---------------------------------------------------------------- frontends
if (-not $BackendOnly) {
  if (-not (Test-Path (Join-Path $Root 'node_modules'))) {
    Write-Step 'pnpm install'
    Push-Location $Root; try { & pnpm install; if ($LASTEXITCODE -ne 0) { throw 'pnpm install failed' } } finally { Pop-Location }
  }
  $env:TURBO_TELEMETRY_DISABLED = '1'
  $env:DO_NOT_TRACK = '1'
  # web-dev serves the app same-origin: it proxies /api, /auth, /static, /live and /uploads (debug MinIO :9310) and
  # the client uses relative URLs (apps/web/vite.config.ts; only read by the web dev server, never by builds).
  $env:PLANE_WEB_DEV_PROXY = '1'
  $env:PLANE_WEB_UPLOADS_PROXY_TARGET = 'http://127.0.0.1:9310'
  if (-not (Test-Path (Join-Path $Root 'packages\utils\dist'))) {
    Write-Step 'Building workspace packages (first run)'
    Push-Location $Root; try { & pnpm turbo run build --filter=./packages/*; if ($LASTEXITCODE -ne 0) { throw 'package build failed' } } finally { Pop-Location }
  }

  Write-Step 'Starting host dev servers'
  if (Test-Tracked 'packages') { Write-Host '    packages watcher already running' }
  else {
    Start-Detached 'packages' $Root 'pnpm turbo run dev --filter=./packages/* --concurrency=20 --ui=stream'
    # The watcher's first pass rebuilds every package's dist/ from scratch (tsdown cleans it first). Apps started
    # before that finishes cache "Cannot find module '@plane/...'" (Vite) or exit (live), so wait until every
    # watched package's exported .js entry exists again and nothing changed for a few seconds.
    $entries = @()
    foreach ($pj in Get-ChildItem (Join-Path $Root 'packages\*\package.json')) {
      $pkg = Get-Content $pj.FullName -Raw | ConvertFrom-Json
      if (-not $pkg.scripts -or -not $pkg.scripts.dev) { continue }
      $targets = @()
      if ($pkg.exports) { $pkg.exports.PSObject.Properties | ForEach-Object { if ($_.Value -is [string]) { $targets += $_.Value } elseif ($_.Value.import) { $targets += [string]$_.Value.import } } }
      if ($pkg.main) { $targets += [string]$pkg.main }
      $entries += $targets | Where-Object { $_ -match '^\./dist/.*\.(m?js)$' } | ForEach-Object { Join-Path $pj.DirectoryName ($_ -replace '^\./', '') }
    }
    $deadline = (Get-Date).AddSeconds(240); $stableSince = $null
    while ((Get-Date) -lt $deadline) {
      $missing = @($entries | Where-Object { -not (Test-Path $_) })
      if ($missing.Count -eq 0) {
        if (-not $stableSince) { $stableSince = Get-Date }
        elseif (((Get-Date) - $stableSince).TotalSeconds -ge 5) { break }
      } else { $stableSince = $null }
      Start-Sleep -Seconds 2
    }
    if ($missing.Count -gt 0) { Write-Warning ("packages watcher: {0} dist entries still missing after 240s (see .devlogs\packages.log)" -f $missing.Count) }
    else { Write-Host ("    packages built ({0} dist entries present)" -f $entries.Count) }
  }

  $apps = @(
    # Port 3300 belongs to RELEASE (plane-release-proxy, scripts\local\release.ps1); the dev server lives on 3310.
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

  Write-Step 'Waiting for web servers'
  foreach ($u in @('http://127.0.0.1:3310/', 'http://127.0.0.1:3301/god-mode/', 'http://127.0.0.1:3302/spaces/', 'http://127.0.0.1:3400/live/health')) {
    $c = Wait-Http $u 180
    Write-Host ("    {0} -> {1}" -f $u, $(if ($c -eq 0) { 'no answer yet (see .devlogs)' } else { "HTTP $c" }))
  }
}

Write-Host ''
Write-Host 'Plane DEBUG stack (compose project plane-dev; open it on 127.0.0.1):' -ForegroundColor Green
Write-Host '  web    http://127.0.0.1:3310  (Vite dev server, HMR)'
Write-Host '  admin  http://127.0.0.1:3301/god-mode/'
Write-Host '  space  http://127.0.0.1:3302/spaces/'
Write-Host '  live   http://127.0.0.1:3400/live/'
Write-Host '  api    http://127.0.0.1:8310'
Write-Host '  infra  postgres 127.0.0.1:55433, redis 127.0.0.1:56380, minio 127.0.0.1:9310 (console 9391)'
Write-Host "  logs   $LogDir"
Write-Host 'RELEASE (not managed by this script; scripts\local\release.ps1, see AGENTS.md):'
Write-Host '  web    http://localhost:3300'
if ($PublicHost) { Write-Host "  phone  http://${PublicHost}:3300" }
