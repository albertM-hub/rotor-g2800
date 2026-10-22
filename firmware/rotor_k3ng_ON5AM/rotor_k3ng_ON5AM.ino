// Contrôleur Rotor Yaesu G-2800DXC — ON5AM
// Protocole GS-232A | Arduino Nano
// Broches : D2=CW, D3=CCW, A0=Azimut potentiomètre
// Calibration : table de points ADC → degrés (voir CAL_ADC / CAL_DEG)
// Commandes : R=CW, L=CCW, A=arrêt azimut, S=arrêt total, C=azimut, M xxx=aller à xxx°,
//             W aaa eee=aller à aaa° (élévation ignorée)
// Extension ON5AM (hors GS-232A) : \R = valeur brute de l'ADC, pour l'étalonnage
//                                  \B = référence interne 1,1 V (diagnostic)
// M / W : rotation, puis vérification au repos et impulsions de correction (voir updateMove)
// Sécurités : interlock CW/CCW, pause à l'inversion de sens, timeout relais,
//             limite logicielle 0–360°

// ── Broches ──────────────────────────────────────────────────────────────────
#define PIN_CW    2   // Rotation horaire (CW)
#define PIN_CCW   3   // Rotation anti-horaire (CCW)
#define PIN_AZ    A0  // Potentiomètre azimut

// ── Calibration ADC ──────────────────────────────────────────────────────────
// Points relevés (ADC croissant) ; interpolation linéaire entre deux points voisins
// Relevé du 2026-10-22 à l'aiguille du boîtier : nouveau Nano (USB), bobines sur 5 V séparé.
// 390° = zone de recouvrement (30 sur l'échelle) : sert à détecter le dépassement de 360°.
const int CAL_ADC[] = { 17, 198, 389, 587, 777, 840 };
const int CAL_DEG[] = {  0,  90, 180, 270, 360, 390 };
#define CAL_POINTS ((int)(sizeof(CAL_ADC) / sizeof(CAL_ADC[0])))

// ── Paramètres ───────────────────────────────────────────────────────────────
#define AZ_TOLERANCE      2         // Tolérance d'arrêt en degrés
#define AZ_MIN_DEG        0         // Limite logicielle CCW
#define AZ_MAX_DEG        360       // Limite logicielle CW (recouvrement 360–450° non utilisé)
#define DIR_CHANGE_MS     1000UL    // Pause relais relâchés avant une inversion de sens
#define RELAY_TIMEOUT_MS  300000UL  // Coupure si aucune commande de mouvement depuis 300 s
#define SETTLE_MS         1500UL    // M : attente relais relâchés avant la lecture au repos
#define MS_PER_DEG        400UL     // M : durée d'impulsion par degré (≈ 2,5°/s en commande ext.)
#define COARSE_DEG        20        // M : au-delà de cet écart, rotation guidée ; sinon impulsion
#define MAX_ATTEMPTS      5         // M : nombre maximal de phases de rotation par cible
#define PERSIST_MS        400UL     // Durée minimale d'une condition d'arrêt (pics de ~0,2 s ignorés)
#define STALL_MS          5000UL    // Blocage : relais collé sans mouvement pendant ce temps…
#define STALL_DEG         2         // …de moins de ce nombre de degrés → arrêt (butée, givre, boîtier éteint)
#define ADC_SAMPLES       9         // Nombre de lectures moyennées
#define SERIAL_BAUD       9600

// ── Variables d'état ─────────────────────────────────────────────────────────
enum Direction { DIR_STOP, DIR_CW, DIR_CCW };

Direction activeDir    = DIR_STOP;  // Sens réellement appliqué aux relais
Direction requestedDir = DIR_STOP;  // Sens demandé (peut attendre la fin de la pause)
Direction lastDir      = DIR_STOP;  // Dernier sens appliqué, pour détecter une inversion
unsigned long stopTime    = 0;      // Instant de la dernière coupure des relais
unsigned long lastMoveCmd = 0;      // Instant de la dernière commande de mouvement
int  targetAzimuth  = -1;
char serialBuf[32];
int  bufIdx         = 0;

// Aller à une cible (M / W) en deux temps :
//   MV_MOVE   : rotation guidée par la lecture en mouvement, arrêt dès la cible atteinte
//   MV_SETTLE : relais relâchés, attente, puis lecture au repos (seule lecture juste)
//   MV_PULSE  : petit écart restant → impulsion chronométrée, puis nouvelle vérification
enum MoveState { MV_IDLE, MV_MOVE, MV_SETTLE, MV_PULSE };
MoveState moveState  = MV_IDLE;
Direction moveDir    = DIR_STOP;    // Sens de la phase en cours
unsigned long stateTime  = 0;       // Début de l'attente (MV_SETTLE)
unsigned long pulseStart = 0;       // Collage effectif du relais (MV_PULSE), 0 = pas encore
unsigned long pulseMs    = 0;       // Durée de l'impulsion
int  moveAttempts   = 0;            // Phases MOVE/PULSE déjà faites pour cette cible
unsigned long reachedSince = 0;     // MV_MOVE : cible vue atteinte depuis (0 = non)
unsigned long limitSince   = 0;     // Limite logicielle vue atteinte depuis (0 = non)
Direction stallDir    = DIR_STOP;   // Blocage : sens surveillé
unsigned long stallStart = 0;       // Blocage : début de la fenêtre de surveillance
int  stallAz        = 0;            // Blocage : azimut au début de la fenêtre

// Vrai si cond est vraie sans interruption depuis PERSIST_MS ; since mémorise le début
bool persistent(bool cond, unsigned long &since) {
  if (!cond) {
    since = 0;
    return false;
  }
  if (since == 0) since = millis();
  return millis() - since >= PERSIST_MS;
}

// ── Fonctions utilitaires ────────────────────────────────────────────────────

int readAzimuthADC() {
  long sum = 0;
  for (int i = 0; i < ADC_SAMPLES; i++) {
    sum += analogRead(PIN_AZ);
    delayMicroseconds(200);
  }
  return (int)(sum / ADC_SAMPLES);
}

int adcToDegrees(int adc) {
  if (adc <= CAL_ADC[0]) return CAL_DEG[0];
  for (int i = 1; i < CAL_POINTS; i++) {
    if (adc <= CAL_ADC[i]) {
      return CAL_DEG[i - 1] + (int)((long)(adc - CAL_ADC[i - 1]) * (CAL_DEG[i] - CAL_DEG[i - 1])
                                    / (CAL_ADC[i] - CAL_ADC[i - 1]));
    }
  }
  return CAL_DEG[CAL_POINTS - 1];
}

// Référence interne 1,1 V lue avec AVcc comme référence : la valeur monte quand le 5 V baisse.
// Diagnostic seulement (\B). Le 5 V du Nano chute d'environ 3 % quand une bobine de relais
// est alimentée (4,68 → 4,54 V), et le retour de masse décale aussi A0 : la lecture pendant
// la rotation est fausse de ±5–10°. D'où l'arrêt de M en deux temps, vérifié au repos.
int readBandgap() {
  ADMUX = _BV(REFS0) | _BV(MUX3) | _BV(MUX2) | _BV(MUX1);  // AVcc, canal 1,1 V interne
  delay(1);                                                // stabilisation de la référence
  long sum = 0;
  for (int i = 0; i < 16; i++) {
    ADCSRA |= _BV(ADSC);
    while (bit_is_set(ADCSRA, ADSC));
    sum += ADC;
  }
  analogRead(PIN_AZ);  // conversion jetée : remet le multiplexeur sur A0
  return (int)(sum / 16);
}

int currentAzimuth() {
  return adcToDegrees(readAzimuthADC());
}

// ── Commande des relais ──────────────────────────────────────────────────────

// Relâche les deux relais et mémorise le sens qui vient d'être coupé
void relaysOff() {
  digitalWrite(PIN_CW,  LOW);
  digitalWrite(PIN_CCW, LOW);
  if (activeDir != DIR_STOP) {
    lastDir  = activeDir;
    stopTime = millis();
  }
  activeDir = DIR_STOP;
}

// Seul point d'activation des relais.
// Interlock : les deux relais sont toujours coupés avant d'en activer un.
// Inversion de sens : le nouveau relais n'est activé qu'après DIR_CHANGE_MS
// relais relâchés ; sinon la demande reste en attente et loop() la réapplique.
void applyDirection(Direction d) {
  if (d == activeDir) return;
  relaysOff();
  if (d == DIR_STOP) return;
  if (lastDir != DIR_STOP && d != lastDir && millis() - stopTime < DIR_CHANGE_MS) return;
  digitalWrite(d == DIR_CW ? PIN_CW : PIN_CCW, HIGH);
  activeDir = d;
}

// Arrêt complet : relais relâchés, demande et cible effacées
void stopMotor() {
  targetAzimuth = -1;
  moveState     = MV_IDLE;
  requestedDir  = DIR_STOP;
  relaysOff();
}

// M : relais relâchés, la cible est gardée ; lecture au repos après SETTLE_MS
void startSettle() {
  requestedDir = DIR_STOP;
  relaysOff();
  moveState = MV_SETTLE;
  stateTime = millis();
}

// M : avance d'un pas l'automate MV_MOVE / MV_SETTLE / MV_PULSE (appelé par loop)
void updateMove() {
  if (moveState == MV_IDLE || targetAzimuth < 0) return;

  if (moveState == MV_SETTLE) {
    if (millis() - stateTime < SETTLE_MS) return;
    int diff = targetAzimuth - currentAzimuth();  // lecture au repos : la seule juste
    if (abs(diff) <= AZ_TOLERANCE || moveAttempts >= MAX_ATTEMPTS) {
      stopMotor();
      return;
    }
    moveAttempts++;
    moveDir      = diff > 0 ? DIR_CW : DIR_CCW;
    requestedDir = moveDir;
    if (abs(diff) > COARSE_DEG) {
      moveState    = MV_MOVE;
      reachedSince = 0;
    } else {
      moveState  = MV_PULSE;
      pulseStart = 0;
      pulseMs    = (unsigned long)abs(diff) * MS_PER_DEG;
    }
    return;
  }

  if (moveState == MV_MOVE) {
    // Lecture en mouvement (décalée de quelques degrés) : sert seulement à s'approcher
    int az = currentAzimuth();
    bool reached = (moveDir == DIR_CW) ? az >= targetAzimuth - AZ_TOLERANCE
                                       : az <= targetAzimuth + AZ_TOLERANCE;
    if (persistent(reached, reachedSince)) startSettle();
    return;
  }

  // MV_PULSE : la durée compte à partir du collage effectif (après une éventuelle pause d'inversion)
  if (pulseStart == 0) {
    if (activeDir == moveDir) pulseStart = millis();
    return;
  }
  if (millis() - pulseStart >= pulseMs) startSettle();
}

// Limite logicielle : faux si le sens demandé pousse au-delà de AZ_MIN_DEG / AZ_MAX_DEG
bool directionAllowed(Direction d) {
  if (d == DIR_CW)  return currentAzimuth() < AZ_MAX_DEG;
  if (d == DIR_CCW) return currentAzimuth() > AZ_MIN_DEG;
  return true;
}

// Rotation manuelle continue (R / L) ; refusée (arrêt) si déjà en limite
void startManual(Direction d) {
  if (!directionAllowed(d)) {
    stopMotor();
    return;
  }
  targetAzimuth = -1;
  moveState     = MV_IDLE;
  requestedDir  = d;
  lastMoveCmd   = millis();
  applyDirection(d);
}

// ── Réponse GS-232A ──────────────────────────────────────────────────────────
// Format : "+0XXX" (3 chiffres, 0-paddés)
void sendAzimuth(int az) {
  char buf[16];
  snprintf(buf, sizeof(buf), "+0%03d\r\n", az);
  Serial.print(buf);
}

// ── Parser commandes GS-232A ─────────────────────────────────────────────────
void parseCommand(char *cmd) {
  // Retirer espaces/CR/LF en tête
  while (*cmd == ' ' || *cmd == '\r' || *cmd == '\n') cmd++;

  if (cmd[0] == 'C' || cmd[0] == 'c') {
    // C  → azimut courant
    sendAzimuth(currentAzimuth());

  } else if (cmd[0] == 'M' || cmd[0] == 'm' || cmd[0] == 'W' || cmd[0] == 'w') {
    // M xxx     → aller à l'azimut xxx
    // W aaa eee → aller à l'azimut aaa (élévation eee ignorée : atoi s'arrête à l'espace)
    int az = atoi(cmd + 1);
    az = constrain(az, 0, 360);
    // Départ par une lecture au repos : immédiate si tout est déjà arrêté
    bool wasStopped = (activeDir == DIR_STOP && requestedDir == DIR_STOP);
    startSettle();
    if (wasStopped) stateTime = millis() - SETTLE_MS;
    targetAzimuth = az;
    moveAttempts  = 0;
    lastMoveCmd   = millis();

  } else if (cmd[0] == 'R' || cmd[0] == 'r') {
    // R → rotation CW continue
    startManual(DIR_CW);

  } else if (cmd[0] == 'L' || cmd[0] == 'l') {
    // L → rotation CCW continue
    startManual(DIR_CCW);

  } else if (cmd[0] == 'A' || cmd[0] == 'a') {
    // A → arrêt azimut (pas d'élévation sur ce contrôleur)
    stopMotor();

  } else if (cmd[0] == 'S' || cmd[0] == 's') {
    // S → arrêt total
    stopMotor();
    Serial.println("OK");

  } else if (cmd[0] == '\\' && (cmd[1] == 'R' || cmd[1] == 'r')) {
    // \R → valeur brute de l'ADC (extension ON5AM, hors GS-232A)
    char buf[16];
    snprintf(buf, sizeof(buf), "ADC=%04d\r\n", readAzimuthADC());
    Serial.print(buf);

  } else if (cmd[0] == '\\' && (cmd[1] == 'B' || cmd[1] == 'b')) {
    // \B → référence 1,1 V (extension ON5AM, diagnostic)
    char buf[16];
    snprintf(buf, sizeof(buf), "BG=%04d\r\n", readBandgap());
    Serial.print(buf);
  }
}

// ── Setup ────────────────────────────────────────────────────────────────────
void setup() {
  // Niveau bas écrit avant le passage en sortie : aucun relais ne colle au démarrage
  digitalWrite(PIN_CW,  LOW);
  digitalWrite(PIN_CCW, LOW);
  pinMode(PIN_CW,  OUTPUT);
  pinMode(PIN_CCW, OUTPUT);
  stopMotor();

  Serial.begin(SERIAL_BAUD);
  Serial.println("K3NG Rotor ON5AM v1.0");
}

// ── Loop ─────────────────────────────────────────────────────────────────────
void loop() {
  // Lecture série non-bloquante
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r' || c == '\n') {
      if (bufIdx > 0) {
        serialBuf[bufIdx] = '\0';
        parseCommand(serialBuf);
        bufIdx = 0;
      }
    } else if (bufIdx < (int)sizeof(serialBuf) - 1) {
      serialBuf[bufIdx++] = c;
    }
  }

  // Rotation vers une cible (M / W)
  updateMove();

  // Limite logicielle 0–360° : arrêt dès qu'elle est atteinte (pendant PERSIST_MS),
  // quelle que soit la commande ; pendant M, vérification au repos plutôt qu'abandon
  if (persistent(requestedDir != DIR_STOP && !directionAllowed(requestedDir), limitSince)) {
    if (moveState == MV_MOVE || moveState == MV_PULSE) startSettle();
    else stopMotor();
  }

  // Blocage : relais collé mais azimut immobile → arrêt (la lecture en mouvement étant
  // décalée, la limite logicielle peut ne jamais se déclencher contre une butée mécanique)
  if (activeDir == DIR_STOP) {
    stallDir = DIR_STOP;
  } else if (activeDir != stallDir) {
    stallDir   = activeDir;
    stallStart = millis();
    stallAz    = currentAzimuth();
  } else if (millis() - stallStart >= STALL_MS) {
    int az = currentAzimuth();
    if (abs(az - stallAz) < STALL_DEG) {
      // Pendant M : vérification au repos (tentatives limitées par MAX_ATTEMPTS) ; sinon arrêt
      if (moveState == MV_MOVE || moveState == MV_PULSE) startSettle();
      else stopMotor();
    } else {
      stallStart = millis();
      stallAz    = az;
    }
  }

  // Timeout : aucune commande de mouvement depuis RELAY_TIMEOUT_MS → tout couper
  if (requestedDir != DIR_STOP && millis() - lastMoveCmd > RELAY_TIMEOUT_MS) {
    stopMotor();
  }

  // Applique la demande (y compris celle en attente après une inversion)
  applyDirection(requestedDir);
}
