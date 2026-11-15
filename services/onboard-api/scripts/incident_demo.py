"""Scripted outage demo (docs/demo-outage.md). Stdlib only; any Python 3.12 works.

    python incident_demo.py reset            # idempotent: link up, scenario incidents gone (onboard + ground)
    python incident_demo.py run              # beats 1-4; waits for the crew to press Acknowledge
    python incident_demo.py run --auto-ack   # headless: the script acknowledges for the crew
    python incident_demo.py run --step       # presenter presses Enter before beats 2 and 4
    python incident_demo.py drop | restore   # Earth link pause / resume only

Everything uses the scenario-only astronaut `scn-01`, so the live simulator (ast-*)
can keep running. The reading is posted with source `simulated:scenario` and both
consoles label it as simulated. The urgent message is scripted, as typed by the crew.
Needs the demo controls on (docker compose turns them on; natively set
ONBOARD_DEMO_CONTROLS_ENABLED=true and GROUND_DEMO_CONTROLS_ENABLED=true).
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

ASTRONAUT = "scn-01"
ASTRONAUT_NAME = "Scenario crew (scripted)"
SOURCE = "simulated:scenario"
MESSAGE = "SOS. Scripted demo: I can't breathe, my oxygen reading dropped."


def call(method: str, url: str, body: dict | None = None, ok: tuple[int, ...] = ()) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        detail = error.read().decode()
        if error.code in ok:
            return error.code, detail
        sys.exit(f"{method} {url} -> HTTP {error.code}: {detail}")
    except urllib.error.URLError as error:
        sys.exit(f"{method} {url}: not reachable ({error.reason}). Is the service running?")


def stamp(start: float, text: str) -> None:
    print(f"[{time.monotonic() - start:5.1f} s] {text}", flush=True)


def link(onboard: str, action: str) -> None:
    code, body = call("POST", f"{onboard}/telemetry/{action}", ok=(409,))
    if code == 409:
        sys.exit(f"Cannot {action} the Earth link: {body}")


def reset(onboard: str, ground: str) -> None:
    link(onboard, "resume")
    q = urllib.parse.urlencode({"astronaut_id": ASTRONAUT})
    _, on = call("DELETE", f"{onboard}/demo/incidents?{q}")
    _, gr = call("DELETE", f"{ground}/demo/incidents?{q}")
    call("POST", f"{onboard}/astronauts", {"id": ASTRONAUT, "display_name": ASTRONAUT_NAME}, ok=(409,))
    print(f"Reset: Earth link up; {ASTRONAUT} incidents deleted onboard ({on['deleted']}) "
          f"and on ground ({gr['deleted']}). Readings are kept.")


def wait_for(what: str, check, timeout: float, every: float = 0.5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = check()
        if found:
            return found
        time.sleep(every)
    sys.exit(f"Timed out after {timeout:.0f} s waiting for {what}.")


def run(onboard: str, ground: str, auto_ack: bool, ack_by: str, timeout: float, step: bool = False) -> float:
    start = time.monotonic()
    now = datetime.now(UTC).isoformat()
    call("POST", f"{onboard}/readings", {
        "astronaut_id": ASTRONAUT, "kind": "spo2", "value": 84, "unit": "%",
        "recorded_at": now, "quality": "good", "source": SOURCE,
    })
    stamp(start, f"Beat 1: scripted SpO2 84 % for {ASTRONAUT} (source {SOURCE}).")

    if step:
        input("Press Enter to drop the Earth link (beat 2) ")
    link(onboard, "pause")
    stamp(start, "Beat 2: Earth link paused. Onboard work continues; telemetry queues.")
    _, reply = call("POST", f"{onboard}/assistant/messages", {
        "astronaut_id": ASTRONAUT, "reported_by": ASTRONAUT, "message": MESSAGE,
    })
    incident = (reply.get("incident") or {}).get("id")
    if reply["urgency"] != "immediate" or not incident:
        sys.exit(f"Expected an immediate incident, got urgency {reply['urgency']}: {reply.get('incident')}")
    stamp(start, f"        Incident {incident[:8]} open onboard, ground delivery queued.")

    if auto_ack:
        call("POST", f"{onboard}/incidents/{incident}/acknowledgments", {"acknowledged_by": ack_by})
        stamp(start, f"Beat 3: acknowledged onboard by {ack_by} (scripted).")
    else:
        stamp(start, "Beat 3: waiting for the crew to press Acknowledge in the spaceship console...")
        acks = wait_for("the crew acknowledgment",
                        lambda: call("GET", f"{onboard}/incidents/{incident}")[1]["acknowledgments"], timeout)
        stamp(start, f"        Acknowledged onboard by {acks[0]['acknowledged_by']}.")

    if step:
        input("Press Enter to restore the Earth link (beat 4) ")
    link(onboard, "resume")
    stamp(start, "Beat 4: Earth link restored; waiting for ground...")

    def on_ground():
        code, body = call("GET", f"{ground}/incidents/{incident}", ok=(404,))
        types = sorted(u["type"] for u in body["updates"]) if code == 200 else []
        return body if types == ["acknowledged", "created"] else None

    got = wait_for("ground to show the incident and the acknowledgment", on_ground, timeout)
    for u in got["updates"]:
        if datetime.fromisoformat(u["received_at"]) < datetime.fromisoformat(u["occurred_at"]):
            sys.exit(f"received_at before occurred_at: {u}")
        print(f"        {u['type']:<12} onboard {u['occurred_at']}  received on ground {u['received_at']}")
    elapsed = time.monotonic() - start
    stamp(start, f"Done: ground shows incident {incident[:8]} once, created + acknowledged.")
    return elapsed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["reset", "run", "drop", "restore"])
    parser.add_argument("--onboard", default="http://127.0.0.1:8000")
    parser.add_argument("--ground", default="http://127.0.0.1:8001")
    parser.add_argument("--auto-ack", action="store_true", help="acknowledge from the script (headless run)")
    parser.add_argument("--ack-by", default=ASTRONAUT, help="crew id for --auto-ack")
    parser.add_argument("--step", action="store_true", help="wait for Enter before beats 2 and 4")
    parser.add_argument("--timeout", type=float, default=120, help="max wait per step, seconds")
    args = parser.parse_args()
    onboard, ground = args.onboard.rstrip("/"), args.ground.rstrip("/")
    if args.command == "reset":
        reset(onboard, ground)
    elif args.command == "run":
        run(onboard, ground, args.auto_ack, args.ack_by, args.timeout, args.step)
    else:
        link(onboard, "pause" if args.command == "drop" else "resume")
        print("Earth link paused." if args.command == "drop" else "Earth link restored.")


if __name__ == "__main__":
    main()
