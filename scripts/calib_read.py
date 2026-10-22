#!/usr/bin/env python3
# Relevé d'étalonnage : 20 lectures brutes de A0 (\R) + azimut actuel (C)
# Usage : calib_read.py [étiquette]   — ajoute la ligne au fichier calib_releves.txt
import os, sys, time
import serial

PORT = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
JOURNAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calib_releves.txt")
etiquette = " ".join(sys.argv[1:]) or "-"

with serial.Serial(PORT, 9600, timeout=1) as p:
    time.sleep(2.5)  # l'ouverture du port redémarre le Nano (DTR)
    p.reset_input_buffer()
    vals = []
    for _ in range(20):
        p.write(b"\\R\r")
        r = p.readline().decode(errors="replace").strip()
        if r.startswith("ADC="):
            vals.append(int(r[4:]))
        time.sleep(0.1)
    p.write(b"C\r")
    az = p.readline().decode(errors="replace").strip()

if not vals:
    sys.exit("aucune réponse à \\R")
moy = sum(vals) / len(vals)
ligne = (f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {etiquette:<20} ADC moy={moy:6.1f}  "
         f"min={min(vals)} max={max(vals)}  ({moy * 5 / 1023:.3f} V si Vcc=5V)  C={az}")
print(ligne)
with open(JOURNAL, "a") as f:
    f.write(ligne + "\n")
