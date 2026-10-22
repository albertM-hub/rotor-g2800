#!/usr/bin/env python3
# Petit pas réel : R 4 s → L direct (pause d'inversion 1 s dans le firmware) → L 5 s → S
# Relevé C et \B en continu ; S immédiat si l'azimut s'écarte de plus de 20° du départ.
# Journal détaillé : pas_rotor.log
import serial, time

PORT = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
p = serial.Serial(PORT, 9600, timeout=0.5)
time.sleep(2.5)  # l'ouverture du port redémarre le Nano (DTR)
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
    # Lecture de départ suspecte (boîtier éteint, fil orange/brun débranché) : aucun mouvement
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
