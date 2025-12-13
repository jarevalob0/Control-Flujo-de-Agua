#define BLYNK_TEMPLATE_ID "TMPL2-9qBlvBY"
#define BLYNK_TEMPLATE_NAME "Control de Riego"
#define BLYNK_AUTH_TOKEN "LrsTcscLCbu88JzNmzmm6k4DS6pdao5A"

#include <Wire.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <BlynkSimpleEsp32.h>
#include <Preferences.h>
#include <LiquidCrystal_I2C.h>

char auth[] = BLYNK_AUTH_TOKEN;
char WIFI[] = "A35";
char PASS[] = "Avlal090";

const uint8_t DATA = 4;
const uint8_t RELAY1 = 14;
const uint8_t RELAY2 = 27;
const uint8_t RELAY3 = 26;

LiquidCrystal_I2C lcd(0x27, 16, 2);

const float PULSES = 7.5;
volatile unsigned int pulse = 0;

float Lpm = 0.0;
float Lps = 0.0;
double total = 0.0;
double waterLimit = 0;
bool limitNotified = false;

unsigned long lastSave = 0;

const int RelayActive = LOW;

#define FLOWLPM V1
#define TOTALL V2
#define VALVE3 V5
#define SOURCE V6
#define LIMIT_SET V11
#define RESET_TOTAL V12

BlynkTimer timer;
Preferences prefs;

void IRAM_ATTR pulseISR() {
  pulse++;
}

void setValve(uint8_t valvePin, bool open) {
  digitalWrite(valvePin, open ? RelayActive : !RelayActive);
}

bool readValveState(uint8_t valvePin) {
  return (digitalRead(valvePin) == RelayActive);
}

BLYNK_WRITE(VALVE3) { setValve(RELAY3, param.asInt() == 1); }

BLYNK_WRITE(LIMIT_SET) {
  waterLimit = param.asDouble();
  prefs.putDouble("limit", waterLimit);
  limitNotified = false;
}

BLYNK_WRITE(RESET_TOTAL) {
  if (param.asInt() == 1) {
    total = 0.0;
    prefs.putDouble("totalL", total);
    Blynk.virtualWrite(TOTALL, total);
    lcd.setCursor(0, 1);
    lcd.print("Tot: 0.0 L     ");
    Serial.println("Total reiniciado desde Blynk");
  }
}
BLYNK_WRITE(SOURCE) {
  int option = param.asInt();

  if (option == 1) {
    setValve(RELAY1, true);
    setValve(RELAY2, false);
  }
  else if (option == 2) {
    setValve(RELAY1, false);
    setValve(RELAY2, true);
  }
}

BLYNK_CONNECTED() {
  Serial.println("Conectado a Blynk!");
  Blynk.syncAll();
  Blynk.virtualWrite(LIMIT_SET, waterLimit);
}

bool leak = false;
bool leakNotified = false;
int leakConfirmCount = 0;
const int LEAK_CONFIRM_THRESHOLD = 2;
int leakClearCount = 0;
const int LEAK_CLEAR_THRESHOLD = 2;

void measureAndPublish() {
  noInterrupts();
  unsigned int pulses = pulse;
  pulse = 0;
  interrupts();

  Lpm = ((float)pulses) / PULSES;
  Lps = Lpm / 60.0;
  total += Lps;

  if (waterLimit > 0 && total >= waterLimit && !limitNotified) {
    limitNotified = true;
    Blynk.logEvent("limite_agua", "Se superó el límite de consumo configurado");
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("LIMITE SUPERADO");
  }

  bool v3 = readValveState(RELAY3);

  if (Lps > 0.01 && !v3) {  
    leakConfirmCount++;
    leakClearCount = 0;
    if (leakConfirmCount >= LEAK_CONFIRM_THRESHOLD) leak = true;
} 
else {
    leakClearCount++;
    leakConfirmCount = 0;
    if (leakClearCount >= LEAK_CLEAR_THRESHOLD) leak = false;
}

  if (leak && !leakNotified) {
    leakNotified = true;
    Blynk.logEvent("alerta_de_fuga", "Alerta: Posible fuga detectada");
  } else if (!leak && leakNotified) {
    leakNotified = false;
    Blynk.logEvent("alerta_de_fuga", "La fuga ha cesado");
  }

  Blynk.virtualWrite(FLOWLPM, Lpm);
  Blynk.virtualWrite(TOTALL, total);

  lcd.setCursor(0, 0);
  lcd.print("Flow:");
  lcd.print(Lpm, 2);
  lcd.print(" L/m   ");
  lcd.setCursor(0, 1);
  lcd.print("Tot:");
  lcd.print(total, 1);
  lcd.print(" L    ");
}

void saveState() {
  unsigned long now = millis();
  if (now - lastSave >= 60000UL) {
    lastSave = now;
    prefs.putDouble("totalL", total);
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(DATA, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(DATA), pulseISR, RISING);

  pinMode(RELAY1, OUTPUT);
  pinMode(RELAY2, OUTPUT);
  pinMode(RELAY3, OUTPUT);
  digitalWrite(RELAY1, !RelayActive);
  digitalWrite(RELAY2, !RelayActive);
  digitalWrite(RELAY3, !RelayActive);

  Wire.begin(21, 22);
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("Iniciando...");
  lcd.setCursor(0, 1);
  lcd.print("ESP32 Riego");

  prefs.begin("waterProj", false);
  total = prefs.getDouble("totalL", 0.0);
  waterLimit = prefs.getDouble("limit", 0.0);

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Conectando WiFi");

  WiFi.begin(WIFI, PASS);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
    delay(300);
    Serial.print(".");
  }

  lcd.clear();
  if (WiFi.status() == WL_CONNECTED) lcd.print("WiFi OK");
  else lcd.print("Sin WiFi");

  WiFi.mode(WIFI_STA);

  Blynk.config(auth);
  Blynk.connect();

  timer.setInterval(1000, measureAndPublish);
  timer.setInterval(60000, saveState);

  delay(1000);
  lcd.clear();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) WiFi.begin(WIFI, PASS);
  if (!Blynk.connected()) Blynk.connect(500);

  Blynk.run();
  timer.run();
}
