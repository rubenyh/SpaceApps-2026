# One command for the full demo on Windows. From the repo root:
#   .\run.ps1          start Docker stack (onboard, ollama, demo-init, simulator, ground) + both consoles
#   .\run.ps1 -NoApps  start only the Docker stack
#   .\run.ps1 -UrineDevice  also read ast-01's urine pH/salinity/temperature from the ESP32 on USB
#                         (firmware/serial_bridge.py in its own window; needs uv; combine with -NoApps)
#   .\run.ps1 -Down    stop the Docker stack (keeps data, index and models)
# Needs Docker Desktop running; for the consoles also Node.js and the Rust toolchain.
param([switch]$NoApps, [switch]$Down, [switch]$UrineDevice)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if ($Down) { docker compose down; exit $LASTEXITCODE }

# Docker Desktop cannot reach USB serial ports, so the ESP32 bridge runs on the host; the simulator
# stops faking the three urine values the board measures.
if ($UrineDevice) { $env:SIMULATOR_ARGS = "$env:SIMULATOR_ARGS --real-urine ast-01".Trim() }
docker compose up --build -d
if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed (is Docker Desktop running?)' }

Write-Host 'Waiting for onboard-api (8000) and ground-api (8001)...'
foreach ($url in 'http://127.0.0.1:8000/', 'http://127.0.0.1:8001/') {
    $deadline = (Get-Date).AddMinutes(3)
    while ($true) {
        try { Invoke-RestMethod $url -TimeoutSec 2 | Out-Null; Write-Host "  $url ok"; break }
        catch { if ((Get-Date) -gt $deadline) { throw "$url not up after 3 min: docker compose logs" }; Start-Sleep 2 }
    }
}

if ($UrineDevice) {
    $dir = Join-Path $PSScriptRoot 'services\onboard-api'
    # PYTHONUTF8: the bridge log prints the degree sign and accents.
    Start-Process powershell -WorkingDirectory $dir -ArgumentList '-NoExit', '-Command',
        "`$host.UI.RawUI.WindowTitle='esp32-urine'; `$env:PYTHONUTF8='1'; uv run --with pyserial python ..\..\firmware\serial_bridge.py"
    Write-Host 'ESP32 urine bridge: own window (plug the board in first; it asks for the COM port if it cannot find it).'
}

if (-not $NoApps) {
    foreach ($app in 'spaceship-app', 'base-app') {
        $dir = Join-Path $PSScriptRoot "apps\$app"
        # Own window per console so each one's log stays readable; close the window to stop it.
        # npm.cmd, not npm: npm.ps1 is blocked under the default execution policy (PSSecurityException).
        Start-Process powershell -WorkingDirectory $dir -ArgumentList '-NoExit', '-Command',
            "`$host.UI.RawUI.WindowTitle='$app'; if (-not (Test-Path node_modules)) { npm.cmd install; if (`$LASTEXITCODE -ne 0) { Write-Host 'npm install failed for $app; not launching.' -ForegroundColor Red; return } }; npm.cmd run tauri dev"
    }
}

Write-Host @'

Stack is up. Guides and models keep loading in the background (first run: several minutes):
  docker compose logs -f demo-init     setup progress, ends with exit 0
  docker compose logs -f simulator     readings posted every 5 s
Stop: .\run.ps1 -Down  (and close the console windows)
'@
