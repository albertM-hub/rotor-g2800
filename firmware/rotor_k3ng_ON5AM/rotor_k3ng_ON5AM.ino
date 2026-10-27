// Yaesu G-2800DXC rotator controller — ON5AM
// GS-232A protocol | Arduino Nano
// Pins: D2=CW, D3=CCW, A0=azimuth potentiometer voltage
// Calibration: table of ADC → degrees points (see CAL_ADC / CAL_DEG)
// Commands: R=CW, L=CCW, A=stop azimuth, S=stop all, C=azimuth, M xxx=go to xxx°,
//           W aaa eee=go to aaa° (elevation ignored)
// ON5AM extension (not GS-232A): \R = raw ADC value, for calibration
//                                \B = internal 1.1 V reference (diagnostic)
// M / W: rotation, then check at rest and corrective pulses (see updateMove)
// Safety: CW/CCW interlock, pause on direction reversal, relay timeout,
//         software limit 0–360°

// ── Pins ─────────────────────────────────────────────────────────────────────
#define PIN_CW    2   // Clockwise rotation (CW)
#define PIN_CCW   3   // Counter-clockwise rotation (CCW)
#define PIN_AZ    A0  // Azimuth potentiometer

// ── ADC calibration ──────────────────────────────────────────────────────────
// Measured points (increasing ADC); linear interpolation between two neighbouring points
// Measured 2026-10-22 against the control box needle: new Nano (USB), relay coils on separate 5 V.
// 390° = overlap zone (30 on the dial): used to detect going past 360°.
const int CAL_ADC[] = { 17, 198, 389, 587, 777, 840 };
const int CAL_DEG[] = {  0,  90, 180, 270, 360, 390 };
#define CAL_POINTS ((int)(sizeof(CAL_ADC) / sizeof(CAL_ADC[0])))

// ── Parameters ───────────────────────────────────────────────────────────────
#define AZ_TOLERANCE      2         // Stop tolerance in degrees
#define AZ_MIN_DEG        0         // CCW software limit
#define AZ_MAX_DEG        360       // CW software limit (360–450° overlap not used)
#define DIR_CHANGE_MS     1000UL    // Pause with relays released before a direction reversal
#define RELAY_TIMEOUT_MS  300000UL  // Cut-off if no movement command for 300 s
#define SETTLE_MS         1500UL    // M: wait with relays released before the reading at rest
#define MS_PER_DEG        400UL     // M: pulse duration per degree (≈ 2.5°/s under external control)
#define COARSE_DEG        20        // M: above this error, guided rotation; otherwise a timed pulse
#define MAX_ATTEMPTS      5         // M: maximum number of rotation phases per target
#define PERSIST_MS        400UL     // Minimum duration of a stop condition (~0.2 s spikes ignored)
#define STALL_MS          5000UL    // Stall: relay energised without movement for this long…
#define STALL_DEG         2         // …of less than this many degrees → stop (end stop, ice, box switched off)
#define ADC_SAMPLES       9         // Number of averaged readings
#define SERIAL_BAUD       9600

// ── State variables ──────────────────────────────────────────────────────────
enum Direction { DIR_STOP, DIR_CW, DIR_CCW };

Direction activeDir    = DIR_STOP;  // Direction actually applied to the relays
Direction requestedDir = DIR_STOP;  // Requested direction (may wait for the end of the pause)
Direction lastDir      = DIR_STOP;  // Last applied direction, to detect a reversal
unsigned long stopTime    = 0;      // Time the relays were last released
unsigned long lastMoveCmd = 0;      // Time of the last movement command
int  targetAzimuth  = -1;
char serialBuf[32];
int  bufIdx         = 0;

// Going to a target (M / W) in two stages:
//   MV_MOVE   : rotation guided by the reading while moving, stops once the target is reached
//   MV_SETTLE : relays released, wait, then reading at rest (the only accurate reading)
//   MV_PULSE  : small remaining error → timed pulse, then a new check
enum MoveState { MV_IDLE, MV_MOVE, MV_SETTLE, MV_PULSE };
MoveState moveState  = MV_IDLE;
Direction moveDir    = DIR_STOP;    // Direction of the current phase
unsigned long stateTime  = 0;       // Start of the wait (MV_SETTLE)
unsigned long pulseStart = 0;       // Moment the relay actually closed (MV_PULSE), 0 = not yet
unsigned long pulseMs    = 0;       // Pulse duration
int  moveAttempts   = 0;            // MOVE/PULSE phases already done for this target
unsigned long reachedSince = 0;     // MV_MOVE: target seen reached since (0 = no)
unsigned long limitSince   = 0;     // Software limit seen reached since (0 = no)
Direction stallDir    = DIR_STOP;   // Stall: direction being watched
unsigned long stallStart = 0;       // Stall: start of the watch window
int  stallAz        = 0;            // Stall: azimuth at the start of the window

// True if cond has been true without interruption for PERSIST_MS; since stores the start time
bool persistent(bool cond, unsigned long &since) {
  if (!cond) {
    since = 0;
    return false;
  }
  if (since == 0) since = millis();
  return millis() - since >= PERSIST_MS;
}

// ── Helper functions ─────────────────────────────────────────────────────────

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

// Internal 1.1 V reference read against AVcc: the value rises when the 5 V supply drops.
// Diagnostic only (\B). The Nano's 5 V drops by about 3 % when a relay coil is powered
// from it (4.68 → 4.54 V), and the ground return also shifts A0: the reading while rotating
// is off by ±5–10°. Hence the two-stage M stop, checked at rest.
int readBandgap() {
  ADMUX = _BV(REFS0) | _BV(MUX3) | _BV(MUX2) | _BV(MUX1);  // AVcc reference, internal 1.1 V channel
  delay(1);                                                // let the reference settle
  long sum = 0;
  for (int i = 0; i < 16; i++) {
    ADCSRA |= _BV(ADSC);
    while (bit_is_set(ADCSRA, ADSC));
    sum += ADC;
  }
  analogRead(PIN_AZ);  // discarded conversion: switches the multiplexer back to A0
  return (int)(sum / 16);
}

int currentAzimuth() {
  return adcToDegrees(readAzimuthADC());
}

// ── Relay control ────────────────────────────────────────────────────────────

// Releases both relays and remembers the direction that was just cut
void relaysOff() {
  digitalWrite(PIN_CW,  LOW);
  digitalWrite(PIN_CCW, LOW);
  if (activeDir != DIR_STOP) {
    lastDir  = activeDir;
    stopTime = millis();
  }
  activeDir = DIR_STOP;
}

// The only place where a relay is energised.
// Interlock: both relays are always released before one is energised.
// Direction reversal: the new relay is only energised after DIR_CHANGE_MS with
// relays released; until then the request stays pending and loop() re-applies it.
void applyDirection(Direction d) {
  if (d == activeDir) return;
  relaysOff();
  if (d == DIR_STOP) return;
  if (lastDir != DIR_STOP && d != lastDir && millis() - stopTime < DIR_CHANGE_MS) return;
  digitalWrite(d == DIR_CW ? PIN_CW : PIN_CCW, HIGH);
  activeDir = d;
}

// Full stop: relays released, request and target cleared
void stopMotor() {
  targetAzimuth = -1;
  moveState     = MV_IDLE;
  requestedDir  = DIR_STOP;
  relaysOff();
}

// M: relays released, target kept; reading at rest after SETTLE_MS
void startSettle() {
  requestedDir = DIR_STOP;
  relaysOff();
  moveState = MV_SETTLE;
  stateTime = millis();
}

// M: advances the MV_MOVE / MV_SETTLE / MV_PULSE state machine by one step (called by loop)
void updateMove() {
  if (moveState == MV_IDLE || targetAzimuth < 0) return;

  if (moveState == MV_SETTLE) {
    if (millis() - stateTime < SETTLE_MS) return;
    int diff = targetAzimuth - currentAzimuth();  // reading at rest: the only accurate one
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
    // Reading while moving (off by a few degrees): only used to get close
    int az = currentAzimuth();
    bool reached = (moveDir == DIR_CW) ? az >= targetAzimuth - AZ_TOLERANCE
                                       : az <= targetAzimuth + AZ_TOLERANCE;
    if (persistent(reached, reachedSince)) startSettle();
    return;
  }

  // MV_PULSE: the duration counts from the moment the relay actually closes (after any reversal pause)
  if (pulseStart == 0) {
    if (activeDir == moveDir) pulseStart = millis();
    return;
  }
  if (millis() - pulseStart >= pulseMs) startSettle();
}

// Software limit: false if the requested direction pushes beyond AZ_MIN_DEG / AZ_MAX_DEG
bool directionAllowed(Direction d) {
  if (d == DIR_CW)  return currentAzimuth() < AZ_MAX_DEG;
  if (d == DIR_CCW) return currentAzimuth() > AZ_MIN_DEG;
  return true;
}

// Continuous manual rotation (R / L); refused (stop) if already at the limit
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

// ── GS-232A reply ────────────────────────────────────────────────────────────
// Format: "+0XXX" (3 digits, zero-padded)
void sendAzimuth(int az) {
  char buf[16];
  snprintf(buf, sizeof(buf), "+0%03d\r\n", az);
  Serial.print(buf);
}

// ── GS-232A command parser ───────────────────────────────────────────────────
void parseCommand(char *cmd) {
  // Skip leading spaces/CR/LF
  while (*cmd == ' ' || *cmd == '\r' || *cmd == '\n') cmd++;

  if (cmd[0] == 'C' || cmd[0] == 'c') {
    // C  → current azimuth
    sendAzimuth(currentAzimuth());

  } else if (cmd[0] == 'M' || cmd[0] == 'm' || cmd[0] == 'W' || cmd[0] == 'w') {
    // M xxx     → go to azimuth xxx
    // W aaa eee → go to azimuth aaa (elevation eee ignored: atoi stops at the space)
    int az = atoi(cmd + 1);
    az = constrain(az, 0, 360);
    // Start with a reading at rest: immediate if everything is already stopped
    bool wasStopped = (activeDir == DIR_STOP && requestedDir == DIR_STOP);
    startSettle();
    if (wasStopped) stateTime = millis() - SETTLE_MS;
    targetAzimuth = az;
    moveAttempts  = 0;
    lastMoveCmd   = millis();

  } else if (cmd[0] == 'R' || cmd[0] == 'r') {
    // R → continuous CW rotation
    startManual(DIR_CW);

  } else if (cmd[0] == 'L' || cmd[0] == 'l') {
    // L → continuous CCW rotation
    startManual(DIR_CCW);

  } else if (cmd[0] == 'A' || cmd[0] == 'a') {
    // A → stop azimuth (no elevation on this controller)
    stopMotor();

  } else if (cmd[0] == 'S' || cmd[0] == 's') {
    // S → stop all
    stopMotor();
    Serial.println("OK");

  } else if (cmd[0] == '\\' && (cmd[1] == 'R' || cmd[1] == 'r')) {
    // \R → raw ADC value (ON5AM extension, not GS-232A)
    char buf[16];
    snprintf(buf, sizeof(buf), "ADC=%04d\r\n", readAzimuthADC());
    Serial.print(buf);

  } else if (cmd[0] == '\\' && (cmd[1] == 'B' || cmd[1] == 'b')) {
    // \B → 1.1 V reference (ON5AM extension, diagnostic)
    char buf[16];
    snprintf(buf, sizeof(buf), "BG=%04d\r\n", readBandgap());
    Serial.print(buf);
  }
}

// ── Setup ────────────────────────────────────────────────────────────────────
void setup() {
  // LOW written before switching to output: no relay closes at power-up
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
  // Non-blocking serial read
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

  // Rotation towards a target (M / W)
  updateMove();

  // Software limit 0–360°: stop as soon as it is reached (for PERSIST_MS),
  // whatever the command; during M, check at rest instead of giving up
  if (persistent(requestedDir != DIR_STOP && !directionAllowed(requestedDir), limitSince)) {
    if (moveState == MV_MOVE || moveState == MV_PULSE) startSettle();
    else stopMotor();
  }

  // Stall: relay energised but azimuth not moving → stop (since the reading while moving
  // is offset, the software limit may never trigger against a mechanical end stop)
  if (activeDir == DIR_STOP) {
    stallDir = DIR_STOP;
  } else if (activeDir != stallDir) {
    stallDir   = activeDir;
    stallStart = millis();
    stallAz    = currentAzimuth();
  } else if (millis() - stallStart >= STALL_MS) {
    int az = currentAzimuth();
    if (abs(az - stallAz) < STALL_DEG) {
      // During M: check at rest (attempts limited by MAX_ATTEMPTS); otherwise stop
      if (moveState == MV_MOVE || moveState == MV_PULSE) startSettle();
      else stopMotor();
    } else {
      stallStart = millis();
      stallAz    = az;
    }
  }

  // Timeout: no movement command for RELAY_TIMEOUT_MS → cut everything
  if (requestedDir != DIR_STOP && millis() - lastMoveCmd > RELAY_TIMEOUT_MS) {
    stopMotor();
  }

  // Apply the request (including one pending after a reversal)
  applyDirection(requestedDir);
}
