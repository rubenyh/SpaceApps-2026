#!/usr/bin/env bash
# One command for the full demo on macOS (run.ps1 is the Windows version). From the repo root:
#   ./run.sh                 Docker stack + both consoles + the watch app in the watchOS simulator
#   ./run.sh --no-apps       only the Docker stack
#   ./run.sh --watch-device  as the default, but onboard-api also listens on the LAN and the
#                            watch project opens in Xcode to install on your real watch
#   ./run.sh --urine-device  also read ast-01's urine pH/salinity/temperature from the ESP32 on USB
#                            (firmware/serial_bridge.py, own Terminal window; combine with the others)
#   ./run.sh --down          stop the Docker stack (keeps data, index and models)
# Needs Docker Desktop running; the consoles need Node.js and Rust; the watch needs Xcode
# with a watchOS simulator runtime (xcodebuild -downloadPlatform watchOS).
set -euo pipefail
cd "$(dirname "$0")"
ROOT=$PWD

no_apps=false
device=false
urine=false
for arg in "$@"; do
  case $arg in
    --down) exec docker compose down ;;
    --no-apps) no_apps=true ;;
    --watch-device) device=true ;;
    --urine-device) urine=true ;;
    *) echo "unknown option: $arg (see the top of run.sh)" >&2; exit 2 ;;
  esac
done

# A real watch reaches onboard-api over Wi-Fi, so it must listen on the LAN, not only on 127.0.0.1.
# The real watch wears ast-01, so the simulator stops faking ast-01's pulse and SpO2.
if $device; then export ONBOARD_API_HOST=0.0.0.0 SIMULATOR_ARGS="--real-vitals ast-01"; fi
# Docker Desktop cannot reach USB serial on macOS, so the ESP32 bridge runs on the host; the simulator
# stops faking the three urine values the board measures.
if $urine; then export SIMULATOR_ARGS="${SIMULATOR_ARGS:-} --real-urine ast-01"; fi
docker compose up --build -d || { echo 'docker compose up failed (is Docker Desktop running?)' >&2; exit 1; }

echo 'Waiting for onboard-api (8000) and ground-api (8001)...'
for url in http://127.0.0.1:8000/ http://127.0.0.1:8001/; do
  deadline=$((SECONDS + 180))
  until curl -fsS -m 2 "$url" >/dev/null 2>&1; do
    if ((SECONDS > deadline)); then echo "$url not up after 3 min: docker compose logs" >&2; exit 1; fi
    sleep 2
  done
  echo "  $url ok"
done

if $urine; then
  osascript -e "tell application \"Terminal\" to do script \"cd '$ROOT/services/onboard-api' && uv run --with pyserial python ../../firmware/serial_bridge.py\"" >/dev/null
  echo 'ESP32 urine bridge: own Terminal window (plug the board in first; it asks for the port if it cannot find it).'
fi

if ! $no_apps; then
  for app in spaceship-app base-app; do
    # Own Terminal window per console so each log stays readable; close the window to stop it.
    osascript -e "tell application \"Terminal\" to do script \"cd '$ROOT/apps/$app' && { [ -d node_modules ] || npm install; } && npm run tauri dev\"" >/dev/null
  done

  watch=apps/watch-app
  bundle=com.example.spaceapps.watch
  if [ ! -d "$watch" ]; then
    echo "Watch skipped: $watch is not in this checkout."
  elif $device; then
    ip=$(ipconfig getifaddr en0 || ipconfig getifaddr en1 || echo '<Mac IP>')
    open "$watch/WatchApp.xcodeproj"
    echo "Watch: in Xcode pick your watch and press Run, then enter http://$ip:8000 and pick Demo Uno (ast-01)."
    echo "       Signing and Developer Mode: $watch/README.md"
  else
    echo 'Building the watch app for the simulator...'
    xcodebuild -project "$watch/WatchApp.xcodeproj" -target WatchApp -configuration Debug \
      -sdk watchsimulator ONLY_ACTIVE_ARCH=NO build -quiet
    sims=$(xcrun simctl list devices available | grep 'Apple Watch' || true)
    line=$(grep -m1 Booted <<<"$sims" || head -n1 <<<"$sims")
    dev=$(grep -oE '[0-9A-F-]{36}' <<<"$line" || true)
    if [ -z "$dev" ]; then
      echo 'Watch skipped: no watchOS simulator. Install one: xcodebuild -downloadPlatform watchOS' >&2
    else
      xcrun simctl boot "$dev" 2>/dev/null || true # already booted is fine
      open -a Simulator 2>/dev/null || open -a DeviceHub || true # Xcode 27 renamed Simulator to DeviceHub
      xcrun simctl install "$dev" "$watch/build/Debug-watchsimulator/WatchApp.app"
      xcrun simctl spawn "$dev" defaults write "$bundle" baseURL http://127.0.0.1:8000
      xcrun simctl spawn "$dev" defaults write "$bundle" astronautID ast-01
      xcrun simctl launch "$dev" "$bundle" >/dev/null
      echo "Watch: running in the simulator as ast-01 (change it in the Ajustes tab)."
    fi
  fi
fi

cat <<'EOF'

Stack is up. Guides and models keep loading in the background (first run: several minutes):
  docker compose logs -f demo-init     setup progress, ends with exit 0
  docker compose logs -f simulator     readings posted every 5 s
Stop: ./run.sh --down  (and close the console windows)
EOF
