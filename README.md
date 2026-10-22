# Contrôleur DIY pour rotor Yaesu G-2800DXC (ON5AM)

Pilotage du rotor d'azimut **Yaesu G-2800DXC** depuis un PC, avec un Arduino Nano et deux relais branchés sur la prise de commande externe du boîtier de contrôle. Le Nano lit l'azimut sur la sortie analogique du boîtier et répond au protocole **Yaesu GS-232A** (sous-ensemble), ce qui le rend compatible avec les logiciels de suivi qui parlent ce protocole. Une interface graphique en Python (carte du monde, recherche d'indicatif QRZ, ligne de cap) est fournie.

Article de présentation : [hamanalyst.org — *titre de l'article à compléter*](https://hamanalyst.org/) <!-- TODO : lien définitif -->

> ⚠️ Montage amateur, testé sur un seul rotor (G-2800DXC). Lisez la section **Sécurité** avant le premier essai.

## Contenu du dépôt

| Dossier / fichier | Rôle |
|---|---|
| `firmware/rotor_k3ng_ON5AM/rotor_k3ng_ON5AM.ino` | Firmware du Nano (GS-232A, sécurités, étalonnage) |
| `scripts/rotor_control.py` | Interface graphique (Tkinter) |
| `scripts/world_map.png` | Fond de carte de l'interface (projection de Miller) |
| `scripts/test_comm.py` | Test de communication (bannière + 15 lectures d'azimut) |
| `scripts/calib_read.py` | Relevé d'un point d'étalonnage (20 lectures brutes de l'ADC) |
| `scripts/relay_test.py` | Test des relais |
| `scripts/pas_rotor.py` | Petit pas R → L avec garde ±20° |
| `scripts/m_test.py` | Essai `M <cible>` chronométré, avec gardes |
| `scripts/goto_test.py` | Essai de positionnement |
| `docs/schema_rotor_g2800.svg` / `.png` | Schéma électrique |
| `docs/plan_plaque_rotor_g2800.svg` | Plan de pose sur plaque à pastilles |
| `docs/guide_plaque_rotor_g2800.md` | Guide de montage de la plaque, liste des fils, contrôles |
| `rotor_config.example.ini` | Modèle de configuration locale |

## Matériel

| Qté | Composant | Remarque |
|---|---|---|
| 1 | Arduino Nano (ATmega328P, CH340) | Alimenté par l'USB du PC ; son 5 V sert de référence à l'ADC |
| 2 | Relais **SRD-05VDC-SL-C** (bobine 5 V, ≈ 70 mA) | RL1 = rotation R (CW), RL2 = rotation L (CCW) |
| 2 | Transistor **2N2222** | Commande des bobines (D2 / D3 à HIGH → relais collé) |
| 2 | Diode 1N4007 | Roue libre sur chaque bobine |
| 2 | Résistance 1 kΩ | Base des transistors |
| 3 | Résistance 10 kΩ | Rappel des bases à la masse ; entrée A0 |
| 2 | Condensateur 100 nF | Filtre A0 ; découplage des bobines |
| 1 | Condensateur 470 µF / 10 V | Réserve sur le 5 V des bobines |
| 1 | **Alimentation 5 V séparée** (≥ 500 mA) | Uniquement pour les bobines ; **jamais reliée au 5 V du Nano** |
| 1 | Plaque à pastilles 34 × 26 trous, borniers 2 et 4 points | Voir `docs/` |

**Pourquoi une alimentation séparée pour les bobines ?** Le 5 V USB du Nano est aussi la référence de mesure de l'azimut. Bobines alimentées par le Nano : chute de 3 % à chaque collage et lecture fausse de 5 à 10° pendant la rotation. Avec le 5 V séparé et la masse en étoile : chute de 0,8 % et écart de 2 à 4°.

## Câblage

### Câble de commande du rotor (prise externe du boîtier G-2800)

Câblage **vérifié sur le rotor** (aiguille du boîtier) : le relais RL1, commandé par la commande R, doit faire **monter** l'azimut.

| Fil du câble | Rôle | Branché sur | Bornier J1 |
|---|---|---|---|
| **Brun** | Masse du boîtier | Bus de masse (et fil A vers le GND du Nano, voir plus bas) | AG18 |
| **Orange** | Tension d'azimut (≈ 0,09 V à 0°, ≈ 3,4 V à 360°) | 10 kΩ → A0, 100 nF vers la masse | AG24 |
| **Rouge** | Rotation **R / CW** (azimut ↑) quand il est mis à la masse | Contact NO de **RL1** (commandé par **D2**) | AG20 |
| **Noir** | Rotation **L / CCW** (azimut ↓) quand il est mis à la masse | Contact NO de **RL2** (commandé par **D3**) | AG22 |
| Vert, jaune | — | **Non branchés** | — |

Les contacts COM des deux relais vont à la masse. La broche de vitesse du boîtier n'est pas utilisée : en commande externe, le rotor tourne à environ **2,0 à 2,5°/s** (≈ 4,5°/s depuis la face avant).

> Ne vous fiez pas aux brochages trouvés sur le Web ni aux couleurs supposées : contrôlez le sens à l'aiguille du boîtier. **Si R fait descendre l'aiguille, croisez ROUGE et NOIR** sur le bornier.

### Arduino Nano

| Broche | Liaison |
|---|---|
| D2 | 1 kΩ → base Q1 (2N2222) → bobine RL1 |
| D3 | 1 kΩ → base Q2 (2N2222) → bobine RL2 |
| A0 | Fil orange via 10 kΩ, 100 nF vers la masse du fil A |
| GND (fil A) | Brun du rotor + 100 nF de A0 : masse de mesure, rien d'autre |
| GND (fil B) | Bus de masse puissance : émetteurs, COM des relais, − de l'alim 5 V |
| +5V | **Non utilisée** |

Les deux masses se rejoignent uniquement au GND du Nano (masse en étoile). Détails, liste des fils et contrôles avant mise sous tension : `docs/guide_plaque_rotor_g2800.md`.

## Installation

### Firmware

1. Ouvrir `firmware/rotor_k3ng_ON5AM/rotor_k3ng_ON5AM.ino` dans l'IDE Arduino.
2. Carte : **Arduino Nano**. Processeur : **ATmega328P (Old Bootloader)** pour les clones CH340 courants (téléversement à 57600 bauds).
3. Téléverser. **Boîtier du rotor éteint pendant le téléversement**, ou bornier du rotor débranché.

Au démarrage, le Nano envoie `K3NG Rotor ON5AM v1.0` sur le port série à 9600 bauds.

### Interface et scripts

```bash
python3 -m pip install pyserial pillow numpy   # tkinter : paquet python3-tk sous Debian/Ubuntu
cp rotor_config.example.ini scripts/rotor_config.ini
# éditer scripts/rotor_config.ini (port série, station, QRZ)
python3 scripts/rotor_control.py
```

Sous Linux, l'utilisateur doit être membre du groupe `dialout` pour accéder au port série.

## Configuration : `scripts/rotor_config.ini`

`rotor_config.ini` se place **à côté de `rotor_control.py`**. Il est exclu du dépôt par `.gitignore` : vos identifiants ne doivent figurer nulle part ailleurs.

```ini
[serie]
port = /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
baud = 9600

[station]
lat = 50.6458
lon = 5.5417

[qrz]
user = VOTRE_INDICATIF
password = VOTRE_MOT_DE_PASSE
key =
```

- **Port série** : sous Linux, préférez le chemin stable `/dev/serial/by-id/…` (`ls -l /dev/serial/by-id/`) au nom `/dev/ttyUSBx`, qui peut changer. Sans port configuré, l'interface ne se connecte à rien.
- **Station** : coordonnées de votre antenne (degrés décimaux, Est et Nord positifs). Elles servent au calcul des caps et au tracé.
- **QRZ** : identifiants QRZ.com. La recherche d'indicatif utilise l'API XML de QRZ, qui demande un abonnement XML.
- Les variables d'environnement `ROTOR_PORT`, `ROTOR_QRZ_USER`, `ROTOR_QRZ_PASS` et `ROTOR_QRZ_KEY` ont priorité sur le fichier.
- Les scripts de test (`test_comm.py`, `calib_read.py`, etc.) ont leur port en constante `PORT` en tête de fichier : adaptez-la si besoin.

## Utilisation

| Commande série (9600 bauds, fin de ligne `\r`) | Effet |
|---|---|
| `C` | Azimut courant, réponse `+0XXX` |
| `M xxx` / `W aaa eee` | Aller à l'azimut xxx (élévation ignorée) |
| `R` / `L` | Rotation continue CW / CCW |
| `A` / `S` | Arrêt (`S` répond `OK`) |
| `\R` | Valeur brute de l'ADC (étalonnage) |
| `\B` | Référence interne 1,1 V (diagnostic du 5 V) |

Dans l'interface : **GO** envoie `M`, les boutons **◄ CCW / ■ / CW ►** envoient `L`, `S`, `R`. Une recherche QRZ ou un clic sur la carte remplit le champ de cap **sans lancer la rotation** : il faut appuyer sur GO. La ligne rouge va jusqu'à la cible, le pointillé vert suit le cap réel de l'antenne. F11 : plein écran, Échap pour en sortir. La fermeture de la fenêtre envoie `S`.

## Étalonnage 6 points

La conversion ADC → degrés est une table de 6 points écrite dans le firmware (`CAL_ADC` / `CAL_DEG`), avec interpolation linéaire entre les points.

1. Placer le rotor **avec les boutons de la face avant** sur chaque repère de l'aiguille : **butée 0°, 90°, 180°, 270°, 360°, puis 30 du recouvrement (= 390°)**.
2. À chaque point, l'aiguille arrêtée : `python3 scripts/calib_read.py "180 (aiguille 180)"` (20 lectures de `\R`, moyenne enregistrée dans `scripts/calib_releves.txt`).
3. Reporter les moyennes arrondies dans le firmware, par exemple :
   ```c
   const int CAL_ADC[] = { 17, 198, 389, 587, 777, 840 };
   const int CAL_DEG[] = {  0,  90, 180, 270, 360, 390 };
   ```
   Associer la butée à **0°** (et non 1°) : la limite logicielle refuse alors L en butée.
4. Téléverser, puis contrôler au repos avec `C` à deux ou trois repères.

L'étalonnage dépend du 5 V du Nano. **À refaire après tout changement** de Nano, de câble USB, de hub ou de PC, ou si l'écart à l'aiguille dépasse 2°.

## Sécurité

- **Premiers essais par petits pas** (±5 à 10°), l'œil sur l'aiguille, la commande `S` (ou le bouton ■) à portée de main.
- **Tester les relais rotor débranché** avant tout (`docs/guide_plaque_rotor_g2800.md`, contrôles 1 à 4) : un seul relais à la fois, jamais les deux.
- **Contrôler le sens** (R = azimut qui monte) avant d'utiliser `M` : avec un sens inversé, la limite logicielle et `M` agissent à l'envers.
- **Ne jamais relier les fils vert et brun à la masse du Nano** : sur le montage d'essai, cela a fait tourner le rotor sans arrêt.
- Sécurités du firmware :
  - interlock : les deux relais ne sont jamais collés ensemble ; **pause de 1 s** relais relâchés à chaque inversion de sens ;
  - **limite logicielle 0–360°** (le recouvrement 360–450° n'est pas utilisé) ;
  - **détection de blocage** : relais collé sans variation de 2° en 5 s → arrêt (butée mécanique, givre, boîtier éteint) ;
  - **timeout de 300 s** sans nouvelle commande de mouvement → arrêt. Une course complète 0 → 360° dure environ 150 à 180 s en commande externe ;
  - aucun relais collé au démarrage du Nano.
- Les **butées mécaniques** du rotor restent la dernière protection : la limite logicielle dépend d'une lecture d'azimut correcte. Un boîtier éteint ou un fil d'azimut débranché donne une lecture de 0°.

## Licence

Ce projet est distribué sous **GNU General Public License v3.0** : voir le fichier [`LICENSE`](LICENSE).

Le firmware est une écriture originale qui implémente le protocole GS-232A. Il ne reprend pas le code du [contrôleur de rotor K3NG](https://github.com/k3ng/k3ng_rotator_controller), lui aussi sous GPL-3.0, dont il garde seulement le nom dans sa bannière.

---
73 de ON5AM
