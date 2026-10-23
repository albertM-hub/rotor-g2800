#!/usr/bin/env python3
# Lecture de \B pendant une rotation R : usage  b_rotation.py [durée_s]  (défaut 10 s)
import serial, sys, time
DUREE = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
with serial.Serial('/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0', 9600, timeout=1) as p:
    time.sleep(2.5); p.reset_input_buffer()          # l'ouverture redémarre le Nano (DTR)
    def q(cmd):
        p.write(cmd + b"\r"); return p.readline().decode(errors='replace').strip()
    c0 = q(b"C")
    print("Départ :", c0)
    try:
        if int(c0.lstrip('+')) > 330:
            sys.exit("Azimut > 330° : trop près de la limite pour R, essai annulé.")
    except ValueError:
        sys.exit(f"Lecture de départ incohérente ({c0!r}) : boîtier éteint ?")
    t0 = time.time()
    try:
        p.write(b"R\r")
        while time.time() - t0 < DUREE:
            bg = q(b"\\B")
            v = 1.1 * 1023 / int(bg.split('=')[1]) if '=' in bg else float('nan')
            print(f"{time.time()-t0:5.1f} s  {bg}  ≈ {v:.2f} V  az {q(b'C')}")
            time.sleep(0.5)
    finally:
        print("Arrêt :", q(b"S")); time.sleep(0.3)
        print("Fin :", q(b"C"))
