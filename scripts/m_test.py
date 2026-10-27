#!/usr/bin/env python3
# M test: sends "M <target>", follows C and \B until the end, measures duration and speed.
# Energised relay detected through \B (≥ 250; 248 at rest): the coil load pulls the Nano's
# 5 V down, which raises the bandgap reading. End: relays released for 4 s in a row.
# Safety: S if the azimuth moves more than 10° further from the target than at the start,
# if the test exceeds 150 s, on error or Ctrl-C. Log: m_test_<target>.log
# Usage: python3 m_test.py 270
import serial, sys, time

PORT = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
cible = int(sys.argv[1])
p = serial.Serial(PORT, 9600, timeout=0.5)
time.sleep(2.5)  # opening the port resets the Nano (DTR)
p.reset_input_buffer()
log = []


def q(c):
    p.write(c)
    return p.readline().decode(errors="replace").strip()


def az():
    r = q(b"C\r")
    return int(r.lstrip("+")) if r.startswith("+") else None


def bg():
    r = q(b"\\B\r")
    return int(r[3:]) if r.startswith("BG=") else None


class Abort(Exception):
    pass


try:
    p.write(b"S\r")
    p.readline()
    a0 = [az() for _ in range(5)]
    print("départ C =", a0)
    if None in a0 or max(a0) - min(a0) > 1 or a0[0] < 0:
        raise Abort("lecture de départ incohérente, essai annulé avant tout mouvement")
    depart = a0[0]
    t0 = time.time()
    p.write(f"M{cible}\r".encode())
    on_prev, off_since, impulsions = False, t0, []
    while True:
        t = time.time() - t0
        a, b = az(), bg()
        on = b is not None and b >= 250
        log.append((t, a, b, on))
        if on and not on_prev:
            impulsions.append([t, None, a])
        if not on and on_prev:
            impulsions[-1][1] = t
            off_since = time.time()
        on_prev = on
        if a is not None and abs(a - cible) > abs(depart - cible) + 10:
            raise Abort(f"azimut {a} s'éloigne de la cible {cible}")
        if t > 150:
            raise Abort("plus de 150 s")
        if impulsions and not on and time.time() - off_since > 4:
            break
        if not impulsions and t > 10:
            raise Abort("aucun relais collé en 10 s (déjà sur la cible ?)")
        time.sleep(0.05)
    p.write(b"S\r")
    p.readline()
    fin = [az() for _ in range(10)]
    print("arrivée C =", fin)
    print(f"cible {cible}, départ {depart}, arrivée {round(sum(fin) / len(fin), 1)}")
    for i, (deb, finr, a) in enumerate(impulsions, 1):
        print(f"  phase {i} : relais de {deb:6.2f} à {finr:6.2f} s ({finr - deb:5.2f} s), départ {a}°")
    d1 = impulsions[0][1] - impulsions[0][0]
    ecart = abs(log[[x[0] for x in log].index(impulsions[0][1]) - 1][1] - depart)
    print(f"  phase 1 : {ecart}° en {d1:.2f} s → {ecart / d1:.2f} °/s (lecture en mouvement)")
    print(f"  durée totale consigne → arrêt définitif : {impulsions[-1][1]:.2f} s")
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
    with open(f"m_test_{cible}.log", "w") as f:
        for t, a, b, on in log:
            f.write(f"{t:6.2f} {a} {b} {'ON' if on else '--'}\n")
