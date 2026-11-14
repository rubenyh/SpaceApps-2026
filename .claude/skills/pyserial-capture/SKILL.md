---
name: pyserial-capture
description: Read sensor data over serial (USB/UART) with pySerial and turn it into readings. Use when adding or debugging a serial device collector.
---

# pySerial capture (planned)

Status: `pyserial` is not a dependency yet. Add with `uv add pyserial` in `services/onboard-api`; commit `uv.lock`.

## Where
- Planned: `services/onboard-api/src/onboard_api/ingestion/serial_collector.py` plus a pure parser module.

## Do
- Port, baud rate, timeout and calibration offsets come from settings. List ports: `uv run python -m serial.tools.list_ports`.
- Open with `serial.Serial(port, baudrate, timeout=1)`; read lines with `readline()`; decode with `errors="replace"`.
- Split into `parse_line(bytes) -> Reading | None` (pure, tested) and the loop (I/O).
- Bad lines: count and skip, do not crash. Port disappears: log, close, retry with backoff.
- Run the loop in a thread or `asyncio.to_thread`, started and stopped from FastAPI lifespan, so it never blocks the event loop.
- Save the reading with a timestamp from the host clock (UTC) unless the device sends a trusted one.

## Verify
- Parser tests with recorded byte samples, including garbage and partial lines.
- Without hardware: `serial.serial_for_url("loop://")` gives a loopback port for loop tests.
- With hardware: state which device/port was used. If none, say hardware checks were not run.

Docs: https://pyserial.readthedocs.io/en/latest/
