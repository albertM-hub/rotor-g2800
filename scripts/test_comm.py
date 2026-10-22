#!/usr/bin/env python3
# Test de communication : bannière + 15 lectures « C » (azimut)
import serial, time
with serial.Serial('/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0', 9600, timeout=1) as p:
    time.sleep(2.5)                      # l'ouverture du port redémarre le Nano (DTR)
    print("Bannière :", repr(p.read(p.in_waiting or 1).decode(errors='replace')))
    p.reset_input_buffer()
    vals = []
    for i in range(15):
        p.write(b"C\r")
        r = p.readline().decode(errors='replace')
        print(f"C #{i+1:2d} -> {r!r}")
        try: vals.append(int(r.strip().lstrip('+')))
        except ValueError: pass
        time.sleep(0.3)
    if vals:
        print(f"min={min(vals)} max={max(vals)} écart={max(vals)-min(vals)}°")
