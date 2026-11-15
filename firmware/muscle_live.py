"""Live muscle demo feed: a phone slider drives a simulated 0-5 kg muscle reading.

Run from the repo root:  python firmware/muscle_live.py  [--port 8765]

Open the printed LAN URL on a phone on the same Wi-Fi. Once per second the server
takes a sample = setpoint + uniform(-0.10, 0.10) kg, clamped to 0-5 kg, and keeps
the last 60. The phone page and the spaceship console both read GET /samples.
This feed is a demo only: it never touches onboard-api, the assistant or telemetry.

Stdlib only. Self-check: python firmware/muscle_live.py --check
"""

import argparse
import json
import random
import socket
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MIN_KG, MAX_KG, JITTER_KG = 0.0, 5.0, 0.10
WINDOW = 60  # samples kept, one per second

_lock = threading.Lock()
_setpoint = 2.5
_samples: deque = deque(maxlen=WINDOW)


def clamp(v: float) -> float:
    return min(MAX_KG, max(MIN_KG, v))


def make_sample(setpoint: float) -> float:
    # Always from the setpoint, never from the previous sample, so the value cannot drift.
    return round(clamp(setpoint + random.uniform(-JITTER_KG, JITTER_KG)), 3)


def sampler() -> None:
    next_tick = time.monotonic()
    while True:
        with _lock:
            _samples.append({"t": int(time.time() * 1000), "v": make_sample(_setpoint)})
        next_tick += 1.0
        time.sleep(max(0.0, next_tick - time.monotonic()))


def lan_ip() -> str:
    # UDP "connect" sends no packet; it only asks the OS which interface routes outward.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>Muscle live</title>
<style>
  :root { color-scheme: dark; --fg:#e8edf2; --muted:#8a96a3; --accent:#4fb3ff; --bad:#ff7a6b; }
  html, body { height:100%; margin:0; background:#0d1117; color:var(--fg);
    font-family: system-ui, sans-serif; touch-action: manipulation; overscroll-behavior:none; }
  main { height:100%; display:flex; flex-direction:column; justify-content:center; gap:28px; padding:0 24px; box-sizing:border-box; }
  h1 { margin:0; font-size:15px; font-weight:600; color:var(--muted); letter-spacing:.08em; text-transform:uppercase; }
  .value { font-size:72px; font-weight:700; font-variant-numeric:tabular-nums; }
  .value small { font-size:28px; color:var(--muted); margin-left:6px; }
  .set { color:var(--muted); font-size:15px; }
  input[type=range] { width:100%; height:56px; margin:0; accent-color:var(--accent); touch-action:none; }
  input[type=range]::-webkit-slider-thumb { width:44px; height:44px; }
  input[type=range]::-moz-range-thumb { width:44px; height:44px; }
  .ends { display:flex; justify-content:space-between; font-size:18px; font-weight:600; }
  #status { font-size:14px; color:var(--muted); }
  #status.bad { color:var(--bad); }
</style></head>
<body><main>
  <h1>Muscle reading · Simulated</h1>
  <div class="value"><span id="value">--</span><small>kg</small></div>
  <div>
    <input id="slider" type="range" min="0" max="5" step="0.01" value="2.5" aria-label="Muscle setpoint in kg">
    <div class="ends"><span>0 kg</span><span>5 kg</span></div>
  </div>
  <div class="set">Setpoint: <span id="setpoint">2.50</span> kg</div>
  <div id="status">Connecting…</div>
</main>
<script>
const slider = document.getElementById("slider");
const valueEl = document.getElementById("value");
const setEl = document.getElementById("setpoint");
const statusEl = document.getElementById("status");
let setpoint = null;   // what the user selected; only user input changes it
let dirty = false;     // setpoint not yet sent
let dragging = false;

function select() {
  setpoint = Number(slider.value);
  dirty = true;
  setEl.textContent = setpoint.toFixed(2);
  valueEl.textContent = setpoint.toFixed(2);
}
slider.addEventListener("pointerdown", () => { dragging = true; });
slider.addEventListener("input", () => { dragging = true; select(); });
for (const ev of ["pointerup", "pointercancel", "change"]) {
  slider.addEventListener(ev, () => { dragging = false; });
}

async function tick() {
  try {
    if (dirty && setpoint !== null) {
      dirty = false;
      await fetch("/setpoint", { method: "POST", body: JSON.stringify({ kg: setpoint }) });
    }
    const state = await (await fetch("/samples")).json();
    if (setpoint === null) {
      setpoint = state.setpoint;
      setEl.textContent = setpoint.toFixed(2);
    }
    const last = state.samples[state.samples.length - 1];
    if (last && !dragging) {
      slider.value = last.v;
      valueEl.textContent = last.v.toFixed(2);
    }
    statusEl.textContent = "Live · 1 sample per second";
    statusEl.className = "";
  } catch {
    dirty = setpoint !== null;  // resend after the server comes back
    statusEl.textContent = "Disconnected, retrying…";
    statusEl.className = "bad";
  }
}
tick();
setInterval(tick, 1000);
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")  # console runs on another origin
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self) -> None:
        if self.path == "/":
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        elif self.path == "/samples":
            with _lock:
                self._json({"source": "simulated", "unit": "kg", "setpoint": _setpoint, "samples": list(_samples)})
        else:
            self._json({"detail": "not found"}, 404)

    def do_POST(self) -> None:
        global _setpoint
        if self.path != "/setpoint":
            return self._json({"detail": "not found"}, 404)
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            kg = float(body["kg"])
            if kg != kg:  # NaN
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return self._json({"detail": "body must be {\"kg\": number}"}, 422)
        with _lock:
            _setpoint = clamp(kg)
        self._json({"setpoint": _setpoint})

    def log_message(self, *args) -> None:
        pass  # one request per second per client; keep the terminal readable


def check() -> None:
    for sp in (0.0, 0.05, 2.5, 4.95, 5.0, -3, 9):
        for _ in range(2000):
            v = make_sample(clamp(sp))
            assert MIN_KG <= v <= MAX_KG, (sp, v)
            assert abs(v - clamp(sp)) <= JITTER_KG + 1e-9, (sp, v)
    print("muscle_live self-check ok")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--check", action="store_true", help="run the self-check and exit")
    args = p.parse_args()
    if args.check:
        return check()
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    threading.Thread(target=sampler, daemon=True).start()
    print("Muscle live feed (simulated, 0-5 kg, 1 sample/s)")
    print(f"  Phone (same Wi-Fi): http://{lan_ip()}:{args.port}/")
    print(f"  This computer:      http://127.0.0.1:{args.port}/")
    print("Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
