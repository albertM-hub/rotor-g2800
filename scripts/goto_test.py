#!/usr/bin/env python3
# Test of M (go to an azimuth) on the ON5AM rotator controller
#
# Usage:
#   goto_test.py 300               M 300, azimuth followed until it stops
#   goto_test.py 200 --stop 3      M 200, then S after 3 s (S must cancel M)
#
# Ends when the azimuth has not moved for 4 s (longer than the firmware's settle wait),
# or after 180 s. Whatever happens, S is sent at the end (try/finally).
import sys, time
import serial

PORT = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
STABLE_S = 4.0
MAX_S = 180


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def azimut(p):
    p.write(b"C\r")
    r = p.readline().decode(errors="replace").strip()
    try:
        return int(r.lstrip("+"))
    except ValueError:
        return None


def main():
    if len(sys.argv) < 2:
        sys.exit("usage : goto_test.py <azimut> [--stop secondes]")
    cible = int(sys.argv[1])
    stop_apres = float(sys.argv[sys.argv.index("--stop") + 1]) if "--stop" in sys.argv else None

    p = serial.Serial(PORT, 9600, timeout=1)
    try:
        time.sleep(2.5)  # opening the port resets the Nano (DTR)
        p.reset_input_buffer()
        depart = azimut(p)
        log(f"départ : {depart}°  →  M {cible:03d}")
        p.write(f"M {cible:03d}\r".encode())
        t0 = time.time()
        dernier, depuis, stop_envoye = depart, time.time(), False
        while time.time() - t0 < MAX_S:
            time.sleep(0.5)
            if stop_apres is not None and not stop_envoye and time.time() - t0 >= stop_apres:
                p.write(b"S\r")
                log(f"S envoyé -> {p.readline().decode(errors='replace').strip()!r}")
                stop_envoye = True
            az = azimut(p)
            if az != dernier:
                log(f"{time.time() - t0:5.1f} s  {az}°")
                dernier, depuis = az, time.time()
            elif time.time() - depuis >= STABLE_S:
                break
        log(f"fin après {time.time() - t0:.1f} s : {dernier}° (cible {cible}°, écart {dernier - cible:+d}°)"
            if dernier is not None else "fin : pas de lecture")
    finally:
        p.write(b"S\r")
        log(f"S final -> {p.readline().decode(errors='replace').strip()!r}")
        p.close()


if __name__ == "__main__":
    main()
