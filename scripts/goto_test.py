#!/usr/bin/env python3
# Essai de M (aller à un azimut) sur le contrôleur rotor ON5AM
#
# Usage :
#   goto_test.py 300               M 300, suivi de l'azimut jusqu'à l'arrêt
#   goto_test.py 200 --stop 3      M 200, puis S au bout de 3 s (S doit annuler M)
#
# Fin quand l'azimut n'a pas bougé pendant 4 s (plus que l'attente au repos du firmware),
# ou au bout de 180 s. Quoi qu'il arrive, S est envoyé à la fin (try/finally).
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
        time.sleep(2.5)  # l'ouverture du port redémarre le Nano (DTR)
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
