#!/usr/bin/env python3
# Small real step: R 4 s → straight to L (1 s reversal pause in the firmware) → L 5 s → S
# C and \B logged continuously; immediate S if the azimuth drifts more than 20° from the start.
# Detailed log: pas_rotor.log
import serial, time

PORT = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
p = serial.Serial(PORT, 9600, timeout=0.5)
time.sleep(2.5)  # opening the port resets the Nano (DTR)
p.reset_input_buffer()
log = []
t0 = time.time()


def q(c):
    p.write(c)
    return p.readline().decode(errors="replace").strip()


def az():
    r = q(b"C\r")
    return int(r.lstrip("+")) if r.startswith("+") else None


def send(c):
    p.write(c + b"\r")
    if c == b"S":
        p.readline()
    log.append((time.time() - t0, "CMD", c.decode(), ""))


class Abort(Exception):
    pass


bad = 0


def watch(dur, start):
    global bad
    end = time.time() + dur
    while time.time() < end:
        a = az()
        b = q(b"\\B\r")
        log.append((time.time() - t0, "   ", a, b))
        bad = bad + 1 if a is None or abs(a - start) > 20 else 0
        if bad >= 2:
            raise Abort(f"azimut hors plage : {a}")
        time.sleep(0.03)


try:
    p.write(b"S\r")
    p.readline()
    a0 = [az() for _ in range(5)]
    start = round(sum(a0) / 5)
    print("départ C =", a0)
    # Suspicious starting reading (control box off, orange/brown wire unplugged): no movement
    if None in a0 or max(a0) - min(a0) > 1 or start < 5:
        raise Abort("lecture de départ incohérente, essai annulé avant tout mouvement")
    watch(1.0, start)
    send(b"R"); watch(4.0, start)
    send(b"L"); watch(5.0, start)
    send(b"S"); watch(2.5, start)
    print("arrivée C =", [az() for _ in range(5)], "ADC", q(b"\\R\r"))
except Abort as e:
    p.write(b"S\r")
    print("ABANDON :", e)
except BaseException as e:
    p.write(b"S\r")
    print("ARRÊT :", repr(e))
finally:
    p.write(b"S\r")
    time.sleep(0.2)
    print("S final :", p.read(64))
    p.close()
    with open("pas_rotor.log", "w") as f:
        for t, k, a, b in log:
            f.write(f"{t:6.2f} {k} {a} {b}\n")
