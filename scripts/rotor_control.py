#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Contrôleur Rotor Yaesu G-2800DXC — ON5AM"""

import tkinter as tk
import threading, math, time, queue, os, configparser
import urllib.request
import xml.etree.ElementTree as ET

try:
    import serial
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

try:
    from PIL import Image, ImageDraw, ImageTk
    import numpy as np
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ── Config ────────────────────────────────────────────────────────────────────
# Réglages locaux hors du code : rotor_config.ini à côté de ce script
# (modèle : rotor_config.example.ini). Variables d'environnement prioritaires :
# ROTOR_PORT, ROTOR_QRZ_USER, ROTOR_QRZ_PASS, ROTOR_QRZ_KEY.
_DIR       = os.path.dirname(os.path.abspath(__file__))
CONFIG_INI = os.path.join(_DIR, "rotor_config.ini")
_cfg = configparser.ConfigParser(interpolation=None)
_cfg.read(CONFIG_INI, encoding="utf-8")

def _conf(section, key, env=None, default=""):
    # Variable d'environnement, sinon fichier ; valeur absente ou vide → default
    return ((env and os.environ.get(env)) or _cfg.get(section, key, fallback="").strip()
            or default)

# Pas de port par défaut : sans réglage, aucune connexion (évite d'écrire sur un autre appareil)
COM_PORT  = _conf("serie", "port", "ROTOR_PORT")
BAUD      = int(_conf("serie", "baud", default="9600"))
# Station : par défaut le centre du carré JO20SP (coordonnées exactes dans rotor_config.ini)
QTH_LAT   = float(_conf("station", "lat", default="50.6458"))
QTH_LON   = float(_conf("station", "lon", default="5.5417"))
QRZ_USER  = _conf("qrz", "user", "ROTOR_QRZ_USER")
QRZ_PASS  = _conf("qrz", "password", "ROTOR_QRZ_PASS")
QRZ_KEY   = _conf("qrz", "key", "ROTOR_QRZ_KEY")

POLL_MS   = 250
RESIZE_MS = 150   # Redessin de la carte quand la taille ne bouge plus depuis ce délai

START_W   = 1100  # Largeur de la fenêtre au démarrage (px)

MAP_W     = 720   # Taille d'origine de world_map.png
MAP_H     = 348
# Projection de world_map.png : Miller cylindrique, recalée le 2026-10-22 sur les côtes
# Natural Earth 1:50 M (recouvrement 91 %). x = MAP_X0 + MAP_KX·lon ; y = MAP_Y0 − MAP_KY·Miller(lat)
MAP_X0    = 349.88  # colonne du méridien 0°
MAP_KX    = 1.9300  # px par degré de longitude (la carte couvre ≈ 373° : bord droit au-delà de 180° E)
MAP_Y0    = 219.11  # ligne de l'équateur
MAP_KY    = 1.9063  # px par degré de l'ordonnée de Miller
MAP_CACHE = os.path.join(_DIR, "map_cache.png")
WORLD_PNG = os.path.join(_DIR, "world_map.png")

# ── Palette ───────────────────────────────────────────────────────────────────
C_BG    = "#0d1117"
C_PANEL = "#161b22"
C_FG    = "#e6edf3"
C_DIM   = "#8b949e"
C_GREEN = "#3fb950"
C_RED   = "#f85149"
C_BTN   = "#21262d"
C_LINE  = "#ff3333"
C_QTH   = "#ffaa00"

PIL_OCEAN = ( 10,  30,  48)
PIL_LAND  = ( 42,  74,  42)
PIL_LOUT  = ( 58, 106,  58)
PIL_GRID  = ( 18,  32,  48)
PIL_EQ    = ( 26,  64,  96)
PIL_BDR   = (180, 210, 180)

# ── Contours continents (lon, lat) ────────────────────────────────────────────
CONTINENTS = [
    [(-168,71),(-160,70),(-141,71),(-135,57),(-130,54),(-125,50),
     (-124,49),(-124,37),(-117,32),(-97,26),(-90,30),(-85,30),
     (-80,25),(-80,31),(-75,35),(-67,45),(-60,47),(-53,47),
     (-55,51),(-64,63),(-83,63),(-95,60),(-110,60),(-135,57),
     (-140,60),(-155,60),(-168,62),(-168,71)],
    [(-52,82),(-20,83),(-18,77),(-18,70),(-25,65),(-44,65),(-52,70),(-52,82)],
    [(-80,10),(-77,8),(-75,0),(-75,-5),(-72,-10),(-72,-18),
     (-65,-22),(-58,-35),(-62,-51),(-68,-55),(-75,-50),(-80,-40),
     (-80,-25),(-73,-15),(-72,-5),(-80,10)],
    [(-9,36),(-9,44),(-8,44),(-1,44),(2,43),(5,44),(2,48),(2,51),
     (5,52),(8,55),(10,55),(12,56),(18,57),(24,58),(25,65),(28,70),
     (20,70),(15,58),(10,57),(8,55),(10,54),(14,54),(18,55),(24,55),
     (27,56),(30,60),(35,62),(40,65),(30,70),(20,72),(18,70),(10,55),
     (8,50),(6,49),(2,49),(0,46),(-2,44),(-5,44),(-9,44),(-9,36)],
    [(-5,50),(-3,52),(0,52),(2,54),(0,58),(-5,58),(-6,54),(-5,50)],
    [(-10,52),(-6,52),(-5,54),(-8,56),(-10,52)],
    [(5,58),(8,55),(11,55),(30,57),(30,70),(16,68),(14,65),(5,58)],
    [(-24,64),(-13,64),(-13,66),(-24,66),(-24,64)],
    [(-17,15),(-15,12),(-15,10),(-17,5),(-10,5),(-5,5),(0,5),(5,5),
     (10,5),(15,0),(35,-5),(40,-5),(42,-12),(38,-20),(36,-25),(32,-30),
     (28,-35),(18,-35),(14,-30),(12,-22),(10,-18),(8,-5),(0,5),
     (-5,10),(-14,10),(-17,15)],
    [(44,-12),(50,-16),(50,-25),(44,-25),(44,-12)],
    [(30,42),(36,37),(36,30),(45,10),(56,12),(60,5),(80,10),(100,5),
     (105,10),(110,18),(120,20),(122,30),(130,35),(140,40),(143,45),
     (135,48),(130,55),(110,55),(100,55),(80,60),(60,70),(40,72),
     (30,70),(25,65),(30,55),(35,50),(40,45),(30,42)],
    [(36,30),(43,12),(46,10),(52,12),(56,22),(58,22),(60,24),(55,28),(43,28),(36,30)],
    [(60,24),(68,24),(80,10),(85,8),(70,8),(68,8),(60,12),(60,24)],
    [(100,22),(105,20),(104,10),(110,10),(115,5),(105,0),(100,5),(96,16),(100,22)],
    [(96,6),(108,0),(106,-6),(100,-4),(96,2),(96,6)],
    [(109,2),(118,4),(118,0),(114,-4),(109,-2),(109,2)],
    [(114,-22),(122,-18),(130,-12),(136,-12),(138,-16),(140,-18),
     (148,-20),(154,-28),(152,-36),(146,-40),(140,-40),(132,-32),
     (124,-28),(114,-26),(114,-22)],
    [(132,-2),(140,-4),(148,-8),(146,-6),(140,-4),(132,-2)],
    [(130,33),(131,34),(134,35),(140,36),(141,40),(140,42),(136,36),(130,33)],
    [(-180,-68),(-90,-70),(0,-68),(90,-70),(180,-68),(180,-90),(-180,-90),(-180,-68)],
]

# ── Géographie ────────────────────────────────────────────────────────────────
def miller_deg(lat):
    # Ordonnée de la projection de Miller, exprimée en degrés
    return math.degrees(1.25 * math.log(math.tan(math.pi/4 + 0.4 * math.radians(lat))))

def ll_to_xy(lon, lat):
    return MAP_X0 + MAP_KX * lon, MAP_Y0 - MAP_KY * miller_deg(lat)

def xy_to_ll(x, y):
    # Inverse de ll_to_xy (coordonnées de la carte de base MAP_W × MAP_H)
    lon = (x - MAP_X0) / MAP_KX
    if lon >  180: lon -= 360   # bord droit de la carte : au-delà de 180° E
    if lon < -180: lon += 360
    ym  = math.radians((MAP_Y0 - y) / MAP_KY)
    lat = math.degrees(2.5 * math.atan(math.exp(0.8 * ym)) - 0.625 * math.pi)
    return lon, lat

def central_angle(lat1, lon1, lat2, lon2):
    # Distance angulaire sur le grand cercle (degrés), formule de haversine
    la1, la2 = math.radians(lat1), math.radians(lat2)
    dla, dlo = la2 - la1, math.radians(lon2 - lon1)
    a = math.sin(dla/2)**2 + math.cos(la1)*math.cos(la2)*math.sin(dlo/2)**2
    return math.degrees(2 * math.asin(min(1.0, math.sqrt(a))))

def bearing(lat1, lon1, lat2, lon2):
    la1, la2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(la2)
    y = math.cos(la1)*math.sin(la2) - math.sin(la1)*math.cos(la2)*math.cos(dl)
    return math.degrees(math.atan2(x, y)) % 360

def great_circle_pts(lat1, lon1, az_deg, n=180, dist_deg=180.0):
    # n + 1 points de 0 à dist_deg (degrés d'arc) le long du cap az_deg
    pts = []
    la1r = math.radians(lat1)
    lo1r = math.radians(lon1)
    azr  = math.radians(az_deg)
    for i in range(n + 1):
        d    = math.radians(i * dist_deg / n)
        lat2 = math.asin(math.sin(la1r)*math.cos(d) +
                         math.cos(la1r)*math.sin(d)*math.cos(azr))
        dlon = math.atan2(math.sin(azr)*math.sin(d)*math.cos(la1r),
                          math.cos(d) - math.sin(la1r)*math.sin(lat2))
        pts.append((math.degrees(lat2), math.degrees(lo1r + dlon)))
    return pts

# ── Génération carte ──────────────────────────────────────────────────────────
def _draw_base(w, h):
    img  = Image.new("RGB", (w, h), PIL_OCEAN)
    draw = ImageDraw.Draw(img)
    sx, sy = w / MAP_W, h / MAP_H   # même projection que world_map.png
    for lon in range(-180, 181, 30):
        x = int(ll_to_xy(lon, 0)[0] * sx)
        draw.line([(x,0),(x,h)], fill=PIL_GRID)
    for lat in range(-60, 61, 30):
        y = int(ll_to_xy(0, lat)[1] * sy)
        draw.line([(0,y),(w,y)], fill=PIL_EQ if lat == 0 else PIL_GRID)
    for poly in CONTINENTS:
        dense = []
        for i in range(len(poly)):
            lo1, la1 = poly[i]
            lo2, la2 = poly[(i+1) % len(poly)]
            n = max(1, int(math.hypot(lo2-lo1, la2-la1) / 3))
            for j in range(n):
                dense.append((lo1+j*(lo2-lo1)/n, la1+j*(la2-la1)/n))
        pts = []
        for lo, la in dense:
            x, y = ll_to_xy(lo, max(-85, min(85, la)))
            pts.append((int(x * sx), int(y * sy)))
        if len(pts) >= 3:
            draw.polygon(pts, fill=PIL_LAND, outline=PIL_LOUT)
    return np.array(img)



def _colorize_bw_map(path):
    """Convertit une carte N/B ou palette+transparence en carte colorée."""
    # Fond blanc = océan ; on colle l'image par-dessus avec son alpha
    raw = Image.open(path).convert("RGBA")
    bg  = Image.new("RGBA", raw.size, (255, 255, 255, 255))
    bg.paste(raw, mask=raw.split()[3])
    arr = np.array(bg.convert("L").resize((MAP_W, MAP_H), Image.LANCZOS))
    out = np.zeros((MAP_H, MAP_W, 3), dtype=np.uint8)
    land_mask = arr < 128
    out[ land_mask] = PIL_LAND
    out[~land_mask] = PIL_OCEAN
    # Grille
    img = Image.fromarray(out)
    draw = ImageDraw.Draw(img)
    for lon in range(-180, 181, 30):
        x = int(ll_to_xy(lon, 0)[0])
        draw.line([(x, 0), (x, MAP_H)], fill=PIL_GRID)
    for lat in range(-60, 61, 30):
        y = int(ll_to_xy(0, lat)[1])
        draw.line([(0, y), (MAP_W, y)], fill=PIL_EQ if lat == 0 else PIL_GRID)
    return img

def _build_map():
    # 1. world_map.png fourni par l'utilisateur (carte N/B) → prioritaire
    if os.path.exists(WORLD_PNG):
        print("[carte] Colorisation de world_map.png…")
        return _colorize_bw_map(WORLD_PNG)

    # 2. Cache existant (généré lors d'un lancement précédent)
    if os.path.exists(MAP_CACHE):
        img = Image.open(MAP_CACHE).convert("RGB")
        if img.size != (MAP_W, MAP_H):
            img = img.resize((MAP_W, MAP_H), Image.LANCZOS)
        return img

    # 3. Fallback vectoriel intégré
    print("[carte] Fallback vectoriel utilisé")
    arr = _draw_base(MAP_W, MAP_H)
    img = Image.fromarray(arr.astype(np.uint8))
    img.save(MAP_CACHE)
    return img

def load_map_async(callback):
    threading.Thread(target=lambda: callback(_build_map()), daemon=True).start()

# ── QRZ.com ───────────────────────────────────────────────────────────────────
_qrz_session = None
_QNS = "http://xmldata.qrz.com"

def _qfind(root, tag):
    el = root.find(f'.//{{{_QNS}}}{tag}')
    if el is None:
        el = root.find(f'.//{tag}')
    return el

def _qget(url):
    return ET.fromstring(urllib.request.urlopen(url, timeout=8).read())

def qrz_lookup(callsign):
    global _qrz_session
    call = callsign.upper().strip()

    def fetch(key):
        url  = f"https://xmldata.qrz.com/xml/current/?s={key};callsign={call}"
        root = _qget(url)
        err  = _qfind(root, 'Error')
        if err is not None:
            print(f"[QRZ] erreur lookup: {err.text}")
            return None, err.text or "Erreur QRZ"
        lat_el = _qfind(root, 'lat')
        lon_el = _qfind(root, 'lon')
        if lat_el is None:
            return None, f"{call} non trouvé sur QRZ"
        cty = _qfind(root, 'country')
        return (float(lat_el.text), float(lon_el.text),
                cty.text if cty is not None else ""), None

    if not (QRZ_USER and QRZ_PASS):
        return None, "QRZ non configuré : voir rotor_config.example.ini"

    # Login si pas de session
    if not _qrz_session:
        try:
            url  = (f"https://xmldata.qrz.com/xml/current/"
                    f"?username={QRZ_USER};password={QRZ_PASS};agent=RotorON5AM")
            print(f"[QRZ] login {QRZ_USER}…")
            raw  = urllib.request.urlopen(url, timeout=8).read()
            print(f"[QRZ] réponse: {raw[:400].decode(errors='ignore')}")
            root = ET.fromstring(raw)
            key_el = _qfind(root, 'Key')
            err_el = _qfind(root, 'Error')
            sub_el = _qfind(root, 'SubExp')
            if key_el is None:
                msg = err_el.text if err_el else "pas de clé retournée"
                print(f"[QRZ] login échoué: {msg}")
                return None, f"Login QRZ: {msg}"
            _qrz_session = key_el.text
            print(f"[QRZ] session OK  abonnement: {sub_el.text if sub_el is not None else '?'}")
        except Exception as e:
            print(f"[QRZ] exception login: {e}")
            return None, f"QRZ injoignable: {e}"

    result, err = fetch(_qrz_session)
    if err and ('session' in (err or '').lower()):
        _qrz_session = None
        return qrz_lookup(callsign)
    return result, err

# ── Thread série ──────────────────────────────────────────────────────────────
class SerialThread(threading.Thread):
    def __init__(self, port, baud, rx_q):
        super().__init__(daemon=True)
        self.port, self.baud, self.rx_q = port, baud, rx_q
        self.tx_q = queue.Queue()
        self._running = True
        self.connected = False

    def send(self, cmd): self.tx_q.put(cmd)
    def stop(self):      self._running = False

    def run(self):
        while self._running:
            try:
                ser = serial.Serial(self.port, self.baud, timeout=1)
                self.connected = True
                self.rx_q.put(("status", "ok"))
                while self._running:
                    while not self.tx_q.empty():
                        ser.write((self.tx_q.get_nowait() + "\r\n").encode())
                    if ser.in_waiting:
                        line = ser.readline().decode(errors="ignore").strip()
                        if line:
                            self.rx_q.put(("data", line))
                    time.sleep(0.05)
            except Exception as e:
                self.connected = False
                self.rx_q.put(("status", f"err:{e}"))
                time.sleep(3)
            finally:
                try: ser.close()
                except: pass
                self.connected = False

# ── Application ───────────────────────────────────────────────────────────────
class RotorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Rotor Control — ON5AM  |  G-2800DXC")
        self.configure(bg=C_BG)
        self.current_az = 0
        self.rx_q       = queue.Queue()
        self.serial_th  = None
        self._photo     = None
        self.scale      = 1.0    # Carte affichée / carte de base (MAP_W × MAP_H)
        self._base_img  = None   # Carte PIL à la taille de base
        self._resize_job = None
        self._heading   = None   # Azimut lu sur le rotor (ligne pointillée)
        self._target    = None   # Cible (az, lat, lon, nom) ; lat/lon None pour un azimut seul
        self._build_ui()
        self.update_idletasks()
        self.minsize(self.winfo_reqwidth(), self.winfo_reqheight())
        # Départ à START_W px de large ; hauteur selon les proportions de la carte
        w = min(START_W, self.winfo_screenwidth())
        h = self.winfo_reqheight() - MAP_H + round((w - 12) * MAP_H / MAP_W)
        self.geometry(f"{w}x{min(h, self.winfo_screenheight() - 60)}")
        self.bind("<F11>", lambda e: self.attributes(
            "-fullscreen", not self.attributes("-fullscreen")))
        self.bind("<Escape>", lambda e: self.attributes("-fullscreen", False))
        self._load_map()
        if HAS_SERIAL and COM_PORT:
            self._start_serial()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll()

    # ── Construction UI ───────────────────────────────────────────────────────
    def _build_ui(self):
        # La carte occupe toute la place libre ; le canvas y est centré, aux proportions de la carte
        self.map_frame = tk.Frame(self, bg=C_BG, width=MAP_W, height=MAP_H)
        self.map_frame.grid(row=0, column=0, columnspan=4, padx=6, pady=6, sticky="nsew")
        self.map_frame.bind("<Configure>", self._on_map_resize)
        self.canvas = tk.Canvas(self.map_frame, width=MAP_W, height=MAP_H,
                                bg="#0a1e30", highlightthickness=0)
        self.canvas.place(relx=0.5, rely=0.5, anchor="center")
        self.canvas.bind("<Button-1>", self._map_click)

        def panel(col):
            f = tk.Frame(self, bg=C_PANEL)
            f.grid(row=1, column=col, padx=3, pady=(0,6), sticky="nsew")
            return f

        # Azimut courant
        p0 = panel(0)
        tk.Label(p0, text="AZIMUT", bg=C_PANEL, fg=C_DIM,
                 font=("Consolas",8)).pack(pady=(8,0))
        self.lbl_az = tk.Label(p0, text="---°", bg=C_PANEL, fg=C_GREEN,
                               font=("Consolas",40,"bold"), width=5)
        self.lbl_az.pack(pady=(0,8))

        # GOTO + CW/CCW
        p1 = panel(1)
        tk.Label(p1, text="ALLER À (°)", bg=C_PANEL, fg=C_DIM,
                 font=("Consolas",8)).pack(pady=(8,4))
        ef = tk.Frame(p1, bg=C_PANEL); ef.pack()
        self.entry_az = tk.Entry(ef, width=5, bg=C_BTN, fg=C_FG,
                                  font=("Consolas",20,"bold"), justify="center",
                                  insertbackground=C_FG, relief="flat",
                                  highlightthickness=1, highlightbackground="#30363d")
        self.entry_az.insert(0, "000")
        self.entry_az.pack(side="left", padx=(0,4))
        self.entry_az.bind("<Return>", lambda e: self._goto())
        tk.Button(ef, text="GO", bg=C_GREEN, fg="#000", relief="flat", width=4,
                  font=("Consolas",12,"bold"), command=self._goto).pack(side="left")
        bf = tk.Frame(p1, bg=C_PANEL); bf.pack(pady=6)
        for txt, cmd, bg in [("◄ CCW",self._ccw,C_BTN),("■",self._stop,C_RED),("CW ►",self._cw,C_BTN)]:
            tk.Button(bf, text=txt, bg=bg, fg=C_FG, font=("Consolas",10,"bold"),
                      relief="flat", width=5, activebackground="#404040",
                      command=cmd).pack(side="left", padx=2)

        # Indicatif QRZ
        p2 = panel(2)
        tk.Label(p2, text="INDICATIF (QRZ)", bg=C_PANEL, fg=C_DIM,
                 font=("Consolas",8)).pack(pady=(8,4))
        cf = tk.Frame(p2, bg=C_PANEL); cf.pack()
        self.entry_call = tk.Entry(cf, width=9, bg=C_BTN, fg=C_QTH,
                                    font=("Consolas",14,"bold"), justify="center",
                                    insertbackground=C_QTH, relief="flat",
                                    highlightthickness=1, highlightbackground="#30363d")
        self.entry_call.pack(side="left", padx=(0,4))
        self.entry_call.bind("<Return>", lambda e: self._lookup())
        tk.Button(cf, text="⊙", bg=C_QTH, fg="#000", relief="flat", width=3,
                  font=("Consolas",14,"bold"), command=self._lookup).pack(side="left")
        self.lbl_call = tk.Label(p2, text="", bg=C_PANEL, fg=C_DIM,
                                  font=("Consolas",8), wraplength=160, justify="center")
        self.lbl_call.pack(pady=(4,6))
        self._wrap_to_panel(self.lbl_call, p2)

        # Statut
        p3 = panel(3)
        tk.Label(p3, text="STATUT", bg=C_PANEL, fg=C_DIM,
                 font=("Consolas",8)).pack(pady=(8,4))
        self.lbl_status = tk.Label(p3, text="● HORS LIGNE", bg=C_PANEL,
                                    fg=C_RED, font=("Consolas",10,"bold"))
        self.lbl_status.pack()
        lbl_port = tk.Label(p3, text=f"{COM_PORT or 'port non configuré (rotor_config.ini)'}\n{BAUD} bd", bg=C_PANEL, fg=C_DIM,
                            font=("Consolas",8), wraplength=160, justify="center")
        lbl_port.pack(pady=(4,6))
        self._wrap_to_panel(lbl_port, p3)
        if not HAS_SERIAL:
            tk.Label(p3, text="pip install pyserial", bg=C_PANEL,
                     fg=C_RED, font=("Consolas",7)).pack()
        if not HAS_PIL:
            tk.Label(p3, text="pip install Pillow numpy", bg=C_PANEL,
                     fg=C_RED, font=("Consolas",7)).pack()

        for c in range(4):
            self.columnconfigure(c, weight=1, uniform="panneaux")
        self.rowconfigure(0, weight=1)

    def _wrap_to_panel(self, label, panel):
        # Retour à la ligne à la largeur réelle du panneau (suit le redimensionnement)
        panel.bind("<Configure>",
                   lambda e: label.config(wraplength=max(60, e.width - 12)), add="+")

    # ── Carte ─────────────────────────────────────────────────────────────────
    def _xy(self, lon, lat):
        # Coordonnées à l'échelle de la carte affichée
        x, y = ll_to_xy(lon, lat)
        return x * self.scale, y * self.scale

    def _load_map(self):
        if not HAS_PIL:
            self._render_map(); return
        msg = "Chargement carte…"
        self.canvas.create_text(MAP_W//2, MAP_H//2, text=msg,
                                fill=C_DIM, font=("Consolas",12), tags="loading")
        load_map_async(lambda img: self.after(0, lambda: self._show_map(img)))

    def _show_map(self, pil_img):
        self.canvas.delete("loading")
        self._base_img = pil_img
        self._render_map()

    def _on_map_resize(self, event):
        # Redessin différé : rien pendant le glissement, une fois la taille stabilisée
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(RESIZE_MS, self._apply_scale, event.width, event.height)

    def _apply_scale(self, w, h):
        self._resize_job = None
        s = max(0.1, min(w / MAP_W, h / MAP_H))
        if abs(s - self.scale) < 0.002:
            return
        self.scale = s
        self.canvas.config(width=round(MAP_W * s), height=round(MAP_H * s))
        self.canvas.delete("loading")
        self._render_map()

    def _render_map(self):
        # Fond de carte à l'échelle courante, puis tracés par-dessus
        self.canvas.delete("mapbg")
        if self._base_img is not None:
            size = (round(MAP_W * self.scale), round(MAP_H * self.scale))
            img = self._base_img
            if img.size != size:
                img = img.resize(size, Image.LANCZOS)
            self._photo = ImageTk.PhotoImage(img)
            self.canvas.create_image(0, 0, anchor="nw", image=self._photo, tags="mapbg")
        elif not HAS_PIL:
            self._draw_fallback()
        self.canvas.tag_lower("mapbg")
        self._draw_overlays()

    def _draw_fallback(self):
        c = self.canvas
        w, h = MAP_W * self.scale, MAP_H * self.scale
        c.create_rectangle(0, 0, w, h, fill="#0a1e30", outline="", tags="mapbg")
        for lo in range(-180, 181, 30):
            x, _ = self._xy(lo, 0)
            c.create_line(x, 0, x, h, fill="#122030", tags="mapbg")
        for la in range(-90, 91, 30):
            _, y = self._xy(0, la)
            c.create_line(0, y, w, y, fill="#122030", tags="mapbg")
        for poly in CONTINENTS:
            pts = []
            for lo, la in poly:
                pts.extend(self._xy(lo, la))
            if len(pts) >= 4:
                try: c.create_polygon(pts, fill="#2a4a2a", outline="#3a6a3a", tags="mapbg")
                except: pass

    def _gc_line(self, az, dist_deg, **opts):
        # Grand cercle depuis le QTH sur dist_deg degrés d'arc, coupé à l'antiméridien
        pts_ll = great_circle_pts(QTH_LAT, QTH_LON, az,
                                  n=max(2, int(dist_deg)), dist_deg=dist_deg)
        segs, seg, prev_x = [], [], None
        for lat, lon in pts_ll:
            while lon >  180: lon -= 360
            while lon < -180: lon += 360
            x, y = self._xy(lon, lat)
            if prev_x is not None and abs(x - prev_x) > MAP_W * self.scale / 2:
                if seg: segs.append(seg)
                seg = []
            seg.append((x, y))
            prev_x = x
        if seg: segs.append(seg)
        for s in segs:
            if len(s) >= 2:
                self.canvas.create_line([c for pt in s for c in pt],
                                        smooth=True, tags="overlay", **opts)

    def _draw_overlays(self):
        # Cap du rotor (pointillé vert), cible (rouge, arrêtée au point visé), QTH par-dessus
        c = self.canvas
        c.delete("overlay")
        if self._heading is not None:
            self._gc_line(self._heading, 180.0, fill=C_GREEN, width=1, dash=(4, 3))
        if self._target is not None:
            az, lat, lon, name = self._target
            if lat is None:
                self._gc_line(az, 180.0, fill=C_LINE, width=2)
            else:
                self._gc_line(az, central_angle(QTH_LAT, QTH_LON, lat, lon),
                              fill=C_LINE, width=2)
                tx, ty = self._xy(lon, lat)
                c.create_oval(tx-6, ty-6, tx+6, ty+6, outline=C_LINE, width=2, tags="overlay")
                c.create_oval(tx-2, ty-2, tx+2, ty+2, fill="white", outline="", tags="overlay")
                if name:
                    c.create_text(tx+9, ty+9, text=name, anchor="nw", fill=C_LINE,
                                  font=("Consolas",8,"bold"), tags="overlay")
        qx, qy = self._xy(QTH_LON, QTH_LAT)
        c.create_oval(qx-5, qy-5, qx+5, qy+5,
                      fill=C_QTH, outline="white", width=1, tags="overlay")
        c.create_text(qx+8, qy-8, text="ON5AM", fill=C_QTH,
                      font=("Consolas",8,"bold"), tags="overlay")

    def _set_heading(self, az):
        if az != self._heading:
            self._heading = az
            self._draw_overlays()

    def _set_target(self, az, lat=None, lon=None, name=None):
        self._target = (az, lat, lon, name)
        self._draw_overlays()

    # ── Événements ────────────────────────────────────────────────────────────
    def _map_click(self, event):
        lon, lat = xy_to_ll(event.x / self.scale, event.y / self.scale)
        az  = bearing(QTH_LAT, QTH_LON, lat, lon)
        self.entry_az.delete(0, tk.END)
        self.entry_az.insert(0, f"{az:.0f}")
        self._set_target(az, lat, lon)

    def _goto(self):
        try:
            az = int(self.entry_az.get()) % 360
            self._send(f"M {az:03d}")
            # Une cible localisée (QRZ, clic) reste affichée si GO vise son cap
            if not (self._target and self._target[1] is not None
                    and round(self._target[0]) % 360 == az):
                self._set_target(az)
        except ValueError: pass

    def _stop(self): self._send("S")
    def _cw(self):   self._send("R")
    def _ccw(self):  self._send("L")

    def _lookup(self):
        call = self.entry_call.get().strip()
        if not call: return
        self.lbl_call.config(text="Recherche…", fg=C_DIM)
        def worker():
            result, err = qrz_lookup(call)
            if err:
                self.after(0, lambda: self.lbl_call.config(text=err, fg=C_RED))
                return
            lat, lon, country = result
            az = bearing(QTH_LAT, QTH_LON, lat, lon)
            self.after(0, lambda: self._apply_lookup(call.upper(), az, country, lat, lon))
        threading.Thread(target=worker, daemon=True).start()

    def _apply_lookup(self, call, az, country, lat, lon):
        self.entry_az.delete(0, tk.END)
        self.entry_az.insert(0, f"{az:.0f}")
        self.lbl_call.config(text=f"{country}\n→ {az:.1f}°  (GO pour tourner)", fg=C_GREEN)
        self._set_target(az, lat, lon, call)
        # Pas de M ici : la rotation ne part qu'avec GO, jamais sur une simple recherche

    # ── Série ─────────────────────────────────────────────────────────────────
    def _start_serial(self):
        self.serial_th = SerialThread(COM_PORT, BAUD, self.rx_q)
        self.serial_th.start()

    def _on_close(self):
        # S avant de quitter : aucun relais ne doit rester collé après la fermeture
        th = self.serial_th
        if th and th.connected:
            th.send("S")
            limite = time.time() + 1.0
            while not th.tx_q.empty() and time.time() < limite:
                time.sleep(0.02)
            time.sleep(0.1)  # laisse partir l'écriture en cours
            th.stop()
        self.destroy()

    def _send(self, cmd):
        if self.serial_th and self.serial_th.connected:
            self.serial_th.send(cmd)

    def _poll(self):
        while not self.rx_q.empty():
            kind, data = self.rx_q.get_nowait()
            if kind == "status":
                self.lbl_status.config(
                    text="● EN LIGNE" if data == "ok" else "● HORS LIGNE",
                    fg=C_GREEN if data == "ok" else C_RED)
            elif kind == "data":
                self._parse(data)
        if self.serial_th and self.serial_th.connected:
            self.serial_th.send("C")
        self.after(POLL_MS, self._poll)

    def _parse(self, data):
        data = data.strip()
        if data.startswith("+0") and len(data) >= 5:
            try:
                az = int(data[2:5])
                self.current_az = az
                self.lbl_az.config(text=f"{az:03d}°")
                self._set_heading(az)
            except ValueError: pass


if __name__ == "__main__":
    if not HAS_PIL:
        print("ATTENTION : pip install Pillow numpy  (carte simplifiée sans ces libs)")
    RotorApp().mainloop()