#!/usr/bin/env python3
# Relay test for the ON5AM rotator controller (GS-232A: R / L / A / S)
#
# Usage:
#   relay_test.py R [max_duration_s]       RL1 (CW) energised, then S
#   relay_test.py L [max_duration_s]       RL2 (CCW) energised, then S
#   relay_test.py R --arret A              RL1 energised, stopped with A instead of S
#   relay_test.py interlock                R, then L 2 s later: CW must drop ~1 s before CCW closes
#   relay_test.py timeout                  R then no more commands: cut-off expected at 200 s
#
# Early stop: create a file named STOP next to the script.
# Whatever happens (error, Ctrl-C, SIGTERM), S is sent at the end (try/finally).
import os, signal, sys, time
import serial

PORT = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
STOPFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "STOP")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def send(p, cmd, reponse=False):
    p.write(cmd.encode() + b"\r")
    if reponse:
        r = p.readline().decode(errors="replace")
        log(f"{cmd} -> {r!r}")
        return r
    log(f"{cmd} envoyé")


def attendre(tmax):
    t0 = time.time()
    while time.time() - t0 < tmax and not os.path.exists(STOPFILE):
        time.sleep(0.2)
    return time.time() - t0


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__ or "usage : relay_test.py R|L|interlock|timeout [durée] [--arret A]")
    mode = args[0].upper()
    arret = "S"
    if "--arret" in args:
        arret = args[args.index("--arret") + 1].upper()
        args = args[:args.index("--arret")]
    tmax = float(args[1]) if len(args) > 1 else 120

    if os.path.exists(STOPFILE):
        os.remove(STOPFILE)
    # Turn SIGTERM into KeyboardInterrupt so the finally block still sends S
    signal.signal(signal.SIGTERM, lambda *a: (_ for _ in ()).throw(KeyboardInterrupt()))

    p = serial.Serial(PORT, 9600, timeout=1)
    try:
        time.sleep(2.5)  # opening the port resets the Nano (DTR)
        log(f"Bannière : {p.read(p.in_waiting or 1).decode(errors='replace')!r}")
        p.reset_input_buffer()
        send(p, "S", reponse=True)

        if mode in ("R", "L"):
            send(p, mode)
            log(f"relais {'RL1 (CW)' if mode == 'R' else 'RL2 (CCW)'} censé être collé")
            log(f"fin après {attendre(tmax):.1f} s")
            send(p, arret, reponse=(arret == "S"))
            if arret != "S":
                log("le relais doit retomber MAINTENANT ; S de sécurité dans 5 s")
                time.sleep(5)

        elif mode == "INTERLOCK":
            send(p, "R")
            log("RL1 (CW) censé être collé ; L dans 2 s")
            time.sleep(2)
            send(p, "L")
            log("attendu : RL1 retombe tout de suite, RL2 colle ~1 s plus tard")
            log(f"fin après {attendre(tmax):.1f} s")

        elif mode == "TIMEOUT":
            send(p, "R")
            log("RL1 (CW) censé être collé ; plus aucune commande, coupure attendue vers 200 s")
            log(f"fin après {attendre(tmax if len(args) > 1 else 220):.1f} s")

        else:
            sys.exit(f"mode inconnu : {mode}")
    finally:
        for _ in range(3):
            if "OK" in send(p, "S", reponse=True):
                break
        p.close()


if __name__ == "__main__":
    main()
