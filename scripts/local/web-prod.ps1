<#
  Serves the PRODUCTION web build on 127.0.0.1:3300 (a reverse proxy or Tailscale serve may
  forward a remote host name to 127.0.0.1:3300). Caddy container "plane-web-prod" on the
  plane_dev_env network: static files + gzip/zstd, /api, /auth, /static proxied
  to the api container, /uploads proxied to MinIO (the API runs with USE_MINIO=1, so
  presigned upload/download URLs use this origin), /live to the host live server, so
  the app, images and attachments work from any device (same origin).

  Usage:
    scripts\local\web-prod.ps1            # rebuild apps/web, then (re)start the server
    scripts\local\web-prod.ps1 -NoBuild   # just (re)start the server with the last build

  The build reads apps/web/.env.production.local (never committed); it is created from
  scripts\local\web-prod\env.production.example when missing.
  -PublicHost (default $env:PLANE_PUBLIC_HOST) only adds the remote URL to the summary.

  The web Vite DEV server must not hold port 3300; this script stops it first.
  Touches only the plane-web-prod container and web dev servers from this repo.
#>
param([switch]$NoBuild, [string]$PublicHost = $env:PLANE_PUBLIC_HOST)
$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repo

# Stop a web dev server bound to 3300 (only a node process from this repo).
Get-NetTCPConnection -State Listen -LocalPort 3300 -LocalAddress 127.0.0.1 -ErrorAction SilentlyContinue | ForEach-Object {
  $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)"
  if ($proc.Name -eq 'node.exe' -and $proc.CommandLine -match 'react-router') {
    Write-Host "Stopping web dev server (pid $($proc.ProcessId))"
    taskkill /PID $proc.ProcessId /T /F | Out-Null
  }
}

if (-not $NoBuild) {
  Write-Host 'Building apps/web (production, same-origin API/live)...'
  # apps/web/.env.production.local blanks VITE_API/WEB/LIVE_BASE_URL so the bundle
  # calls whatever origin it was opened from (localhost or a remote host name).
  $override = Join-Path $repo 'apps\web\.env.production.local'
  if (-not (Test-Path $override)) {
    Copy-Item (Join-Path $repo 'scripts\local\web-prod\env.production.example') $override
    Write-Host "Created $override from scripts\local\web-prod\env.production.example"
  }
  New-Item -ItemType Directory -Force (Join-Path $repo '.devlogs') | Out-Null
  $env:PLANE_WEB_ENV_OVERRIDE = '.env.production.local'
  pnpm --filter web build *> .devlogs\web-build.log
  Remove-Item Env:\PLANE_WEB_ENV_OVERRIDE -ErrorAction SilentlyContinue
  if ($LASTEXITCODE -ne 0) { Write-Host 'Build failed, see .devlogs\web-build.log'; exit 1 }
}

docker rm -f plane-web-prod 2>$null | Out-Null
$client = Join-Path $repo 'apps\web\build\client'
$caddyfile = Join-Path $repo 'scripts\local\web-prod\Caddyfile'
docker run -d --name plane-web-prod --restart unless-stopped --network plane_dev_env `
  -p 127.0.0.1:3300:80 `
  -v "${client}:/srv:ro" -v "${caddyfile}:/etc/caddy/Caddyfile:ro" `
  caddy:2.11.4-alpine | Out-Null
Write-Host 'Web (production) on http://localhost:3300'
if ($PublicHost) { Write-Host "  remote: http://${PublicHost}:3300" }
