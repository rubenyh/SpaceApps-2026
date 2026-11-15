"""Bridge from the ESP32-S3 urine analyser (USB serial) to onboard-api.

The board prints one line per sample: "temperature;pH;salinity;", e.g. "26.1;6.94;0;"
(°C, pH, mg/L). Every --every seconds the latest sample goes to `POST /readings`
as urine_temperature, urine_ph and urine_salinity, source "serial:urine-analyser".
Run the simulator with --real-urine <id> so it stops simulating those three.

    uv run --with pyserial python firmware/serial_bridge.py               # ast-01, auto port
    uv run --with pyserial python firmware/serial_bridge.py --port /dev/cu.usbmodem1101
"""

import argparse
import time
from datetime import UTC, datetime

from simulator import Uplink, log, reading

BAUD = 115200
SOURCE = "serial:urine-analyser"


def parse_line(linea: str, astronauta: str, when: datetime) -> list[dict]:
    """'26.1;6.94;0;' -> three readings. Anything else (garbage, partial line) -> []."""
    try:
        temperatura, ph, salinidad = (float(x) for x in linea.strip().rstrip(";").split(";"))
    except ValueError:
        return []
    # Same sample_validity range as the console (32-38 °C): outside it the probe is not in a fresh sample.
    temp_quality = "good" if 32 <= temperatura <= 38 else "suspect"
    return [
        reading(astronauta, "urine_temperature", "°C", when, value=temperatura, quality=temp_quality, source=SOURCE),
        reading(astronauta, "urine_ph", "pH", when, value=ph, source=SOURCE),
        reading(astronauta, "urine_salinity", "mg/L", when, value=salinidad, source=SOURCE),
    ]


def buscar_puerto():
    import serial.tools.list_ports

    puertos = list(serial.tools.list_ports.comports())
    # 0x303A es el VID de Espressif (USB nativo de la ESP32-S3)
    for p in puertos:
        if p.vid == 0x303A:
            return p.device
    if not puertos:
        return None
    for i, p in enumerate(puertos):
        print(i, p.device, p.description)
    return puertos[int(input("Elige puerto: "))].device


def abrir(puerto: str):
    import serial

    ser = serial.Serial()
    ser.port = puerto
    ser.baudrate = BAUD
    ser.timeout = 1
    ser.dtr = False  # evita que abrir el puerto resetee la placa
    ser.rts = False
    ser.open()
    return ser


def main() -> None:
    import serial  # imported here so parse_line is testable without pyserial

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="onboard-api base URL")
    parser.add_argument("--port", help="serial port (default: first Espressif board, else ask)")
    parser.add_argument("--astronaut", default="ast-01", help="astronaut the samples belong to")
    parser.add_argument("--every", type=float, default=5, help="seconds between uploads (latest sample wins)")
    args = parser.parse_args()

    puerto = args.port or buscar_puerto()
    if puerto is None:
        print("No hay puertos disponibles")
        raise SystemExit(1)

    uplink = Uplink(args.url)
    while not uplink.register_crew():
        time.sleep(5)

    ser = None
    latest: list[dict] = []
    next_upload = 0.0
    try:
        while True:
            if ser is None:
                try:
                    ser = abrir(puerto)
                    log(f"conectado a {puerto}")
                except serial.SerialException as error:
                    log(f"no se pudo abrir {puerto} ({error}), reintento en 5 s")
                    time.sleep(5)
                    continue
            try:
                linea = ser.readline().decode("utf-8", errors="replace")
            except serial.SerialException as error:
                log(f"puerto perdido ({error}), reconectando")
                ser.close()
                ser = None
                continue
            if linea.strip():
                parsed = parse_line(linea, args.astronaut, datetime.now(UTC))
                if parsed:
                    latest = parsed
                else:
                    log(f"línea ignorada: {linea.strip()!r}")
            if latest and time.monotonic() >= next_upload:
                t, ph, sal = (r["value"] for r in latest)
                log(f"{args.astronaut} {t} °C, pH {ph}, {sal} mg/L | sent {uplink.flush(latest)}, buffered {len(uplink.buffer)}")
                latest = []
                next_upload = time.monotonic() + args.every
    except KeyboardInterrupt:
        log("shutdown")
    finally:
        if ser is not None:
            ser.close()


if __name__ == "__main__":
    main()
