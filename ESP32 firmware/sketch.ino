#include <WiFi.h>
#include <HTTPClient.h>
#include <LiquidCrystal_I2C.h>
#include <Wire.h>
#include <time.h>
#include <math.h>
#include <stdio.h>
#include <esp_system.h>

#include "config.h"

const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASSWORD = "";
const char* API_HOST = WOKWI_API_HOST;
const char* API_ROUTE = WOKWI_API_ROUTE;
const int WIFI_CHANNEL = 6;
const unsigned long SEND_INTERVAL_MS = WOKWI_SEND_INTERVAL_MS;
const unsigned long WIFI_RETRY_INTERVAL_MS = 5000;
const unsigned long WIFI_CONNECTION_TIMEOUT_MS = 15000;
const unsigned long DNS_RETRY_INTERVAL_MS = WOKWI_DNS_RETRY_INTERVAL_MS;
const int POTENTIOMETER_PIN = 34;
const int GREEN_LED_PIN = 18;
const int RED_LED_PIN = 19;
const int BUZZER_PIN = 23;
const int TEST_BUTTON_PIN = 27;
const float MIN_SIMULATED_CURRENT_A = 0.8f;
const float NORMAL_MAX_CURRENT_A = 4.8f;
const float MAX_SIMULATED_CURRENT_A = 12.0f;

LiquidCrystal_I2C lcd(0x27, 16, 2);

enum SimulationMode {
  POTENTIOMETER_MODE,
  TEST_NORMAL_MODE,
  TEST_ANOMALY_MODE
};

unsigned long lastSentAt = 0;
unsigned long lastWiFiAttemptAt = 0;
unsigned long lastButtonChangeAt = 0;
unsigned long nextAlertAt = 0;
float cumulativeEnergyKwh = 0.0f;
SimulationMode simulationMode = POTENTIOMETER_MODE;
int lastButtonReading = HIGH;
int stableButtonReading = HIGH;
int alertChirpsRemaining = 0;
String latestStatus = "UNKNOWN";
bool wifiConnectionPending = false;
bool wifiWasConnected = false;
bool apiHostResolved = false;
unsigned long lastDnsAttemptAt = 0;
IPAddress apiHostAddress;
float lastDisplayedVoltage = 0.0f;
float lastDisplayedCurrent = 0.0f;
float lastDisplayedPower = 0.0f;
float lastIntervalEnergyKwh = 0.0f;
String lastDisplayedStatus = "WAITING";
float lastAnomalyScore = 0.0f;
bool apiConnected = false;
int lastHttpStatus = -1;
unsigned int lcdScreen = 0;
unsigned long lastLcdScreenAt = 0;
unsigned long lastLcdUpdateAt = 0;
char API_URL[128];

bool makeTimestamp(char* buffer, size_t bufferSize, tm& currentTime) {
  time_t now = time(nullptr);
  if (now > 1700000000) {
    gmtime_r(&now, &currentTime);
    strftime(buffer, bufferSize, "%Y-%m-%dT%H:%M:%SZ", &currentTime);
    return true;
  }

  const time_t fallbackEpoch = 1792713600;
  time_t fallbackTime = fallbackEpoch + millis() / 1000;
  gmtime_r(&fallbackTime, &currentTime);
  strftime(buffer, bufferSize, "%Y-%m-%dT%H:%M:%SZ", &currentTime);
  return false;
}

float currentFromPotentiometer(int adcValue) {
  const int normalRangeEnd = 2048;
  if (adcValue <= normalRangeEnd) {
    return MIN_SIMULATED_CURRENT_A
        + (NORMAL_MAX_CURRENT_A - MIN_SIMULATED_CURRENT_A) * adcValue / normalRangeEnd;
  }
  return NORMAL_MAX_CURRENT_A
      + (MAX_SIMULATED_CURRENT_A - NORMAL_MAX_CURRENT_A)
          * (adcValue - normalRangeEnd) / (4095 - normalRangeEnd);
}

const char* modeName() {
  switch (simulationMode) {
    case TEST_NORMAL_MODE: return "TEST NORMAL";
    case TEST_ANOMALY_MODE: return "TEST ANOMALY";
    default: return "POTENTIOMETER";
  }
}

void updateTestButton() {
  int reading = digitalRead(TEST_BUTTON_PIN);
  if (reading != lastButtonReading) {
    lastButtonChangeAt = millis();
    lastButtonReading = reading;
  }

  if (millis() - lastButtonChangeAt < 50 || reading == stableButtonReading) return;
  stableButtonReading = reading;
  if (stableButtonReading != LOW) return;

  simulationMode = static_cast<SimulationMode>((simulationMode + 1) % 3);
  Serial.printf("Simulation mode changed: %s\n", modeName());
}

void updateAlertPattern() {
  if (alertChirpsRemaining == 0 || millis() < nextAlertAt) return;
  tone(BUZZER_PIN, 2200, 90);
  alertChirpsRemaining--;
  nextAlertAt = millis() + 230;
}

void setClassification(const String& status) {
  bool wasAnomaly = latestStatus == "ANOMALY";
  latestStatus = status;
  digitalWrite(GREEN_LED_PIN, status == "NORMAL" ? HIGH : LOW);
  digitalWrite(RED_LED_PIN, status == "ANOMALY" ? HIGH : LOW);
  if (status == "ANOMALY" && !wasAnomaly) {
    alertChirpsRemaining = 3;
    nextAlertAt = millis();
  }
}

void setIndicatorsOffline() {
  latestStatus = "OFFLINE";
  digitalWrite(GREEN_LED_PIN, LOW);
  digitalWrite(RED_LED_PIN, LOW);
}

void writeLcdLine(int row, const char* text) {
  char padded[17];
  snprintf(padded, sizeof(padded), "%-16s", text);
  lcd.setCursor(0, row);
  lcd.print(padded);
}

void displayScreen0() {
  char firstLine[17];
  char secondLine[17];
  snprintf(firstLine, sizeof(firstLine), "V:%.1f I:%.2fA", lastDisplayedVoltage, lastDisplayedCurrent);
  snprintf(secondLine, sizeof(secondLine), "P:%.0fW %s", lastDisplayedPower, lastDisplayedStatus.c_str());
  writeLcdLine(0, firstLine);
  writeLcdLine(1, secondLine);
}

void displayScreen1() {
  char firstLine[17];
  char secondLine[17];
  snprintf(firstLine, sizeof(firstLine), "Energy:%.3fkWh", lastIntervalEnergyKwh);
  snprintf(secondLine, sizeof(secondLine), "AI:%s", lastDisplayedStatus.c_str());
  writeLcdLine(0, firstLine);
  writeLcdLine(1, secondLine);
}

void displayScreen2() {
  char secondLine[17];
  if (lastDisplayedStatus == "WAITING" || lastDisplayedStatus == "OFFLINE") {
    snprintf(secondLine, sizeof(secondLine), "AI:%s", lastDisplayedStatus.c_str());
  } else {
    snprintf(secondLine, sizeof(secondLine), "Score:%.2e", lastAnomalyScore);
  }
  writeLcdLine(0, lastDisplayedStatus == "ANOMALY" ? "AI:ANOMALY" :
                    lastDisplayedStatus == "NORMAL" ? "AI:NORMAL" : "AI:WAITING");
  writeLcdLine(1, secondLine);
}

void displayScreen3() {
  if (apiConnected) {
    writeLcdLine(0, "API:CONNECTED");
    writeLcdLine(1, "Device:ESP32");
  } else {
    writeLcdLine(0, "API:OFFLINE");
    writeLcdLine(1, WiFi.status() == WL_CONNECTED ? "Gateway check" : "Wifi:OFFLINE");
  }
}

void displayScreen4() {
  if (apiConnected) {
    writeLcdLine(0, "API:CONNECTED");
    writeLcdLine(1, "AI system ready");
  } else if (lastHttpStatus >= 0) {
    char secondLine[17];
    snprintf(secondLine, sizeof(secondLine), "HTTP:%d", lastHttpStatus);
    writeLcdLine(0, "API:ERROR");
    writeLcdLine(1, secondLine);
  } else {
    writeLcdLine(0, "API:ERROR");
    writeLcdLine(1, WiFi.status() == WL_CONNECTED ? "Gateway/NET" : "Wifi:OFFLINE");
  }
}

void updateLcdScreen() {
  unsigned long now = millis();
  if (now - lastLcdScreenAt < 2500) return;
  lastLcdScreenAt = now;
  lcdScreen = (lcdScreen + 1) % 5;

  switch (lcdScreen) {
    case 0: displayScreen0(); break;
    case 1: displayScreen1(); break;
    case 2: displayScreen2(); break;
    case 3: displayScreen3(); break;
    default: displayScreen4(); break;
  }
}

bool findJsonValue(const String& response, const char* key, int& valueStart) {
  String marker = String("\"") + key + "\"";
  int position = response.indexOf(marker);
  if (position < 0) return false;
  position += marker.length();
  while (position < response.length() && isspace(response[position])) position++;
  if (position >= response.length() || response[position++] != ':') return false;
  while (position < response.length() && isspace(response[position])) position++;
  valueStart = position;
  return position < response.length();
}

bool parseJsonString(const String& response, const char* key, String& value) {
  int start = 0;
  if (!findJsonValue(response, key, start) || response[start] != '"') return false;
  start++;
  int end = response.indexOf('"', start);
  if (end < 0 || response.substring(start, end).indexOf('\\') >= 0) return false;
  value = response.substring(start, end);
  return true;
}

bool parseJsonNumber(const String& response, const char* key, float& value) {
  int start = 0;
  if (!findJsonValue(response, key, start)) return false;
  String remaining = response.substring(start);
  char* end = nullptr;
  float parsed = strtof(remaining.c_str(), &end);
  if (end == remaining.c_str() || !isfinite(parsed)) return false;
  while (*end && isspace(*end)) end++;
  if (*end != ',' && *end != '}') return false;
  value = parsed;
  return true;
}

bool hasValidInference(const String& response, String& status, float& score) {
  String modelVersion;
  float threshold = 0.0f;
  float readingId = 0.0f;
  if (!parseJsonString(response, "status", status) ||
      !parseJsonString(response, "model_version", modelVersion) ||
      modelVersion.length() == 0 ||
      !parseJsonNumber(response, "id", readingId) ||
      !parseJsonNumber(response, "anomaly_score", score) ||
      !parseJsonNumber(response, "threshold", threshold) ||
      readingId < 1.0f || score < 0.0f || threshold <= 0.0f) {
    Serial.println("JSON parsing error: missing or invalid inference fields.");
    return false;
  }
  if (status != "NORMAL" && status != "ANOMALY") {
    Serial.printf("JSON parsing error: unsupported classification '%s'.\n", status.c_str());
    return false;
  }
  if ((status == "NORMAL") != (score <= threshold)) {
    Serial.println("JSON parsing error: classification does not match score and threshold.");
    return false;
  }
  return true;
}

const char* httpErrorLabel(int responseCode) {
  switch (responseCode) {
    case 401: return "HTTP 401";
    case 403: return "HTTP 403";
    case 404: return "HTTP 404";
    case 422: return "HTTP 422";
    case 500: return "HTTP 500";
    case 503: return "HTTP 503";
    default: return responseCode > 0 ? "HTTP ERROR" : "NET ERROR";
  }
}

bool connectWiFi() {
  Serial.printf("Starting Wi-Fi connection to SSID %s\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD, WIFI_CHANNEL);
  lastWiFiAttemptAt = millis();
  wifiConnectionPending = true;
  return true;
}

void updateWiFiConnection() {
  unsigned long now = millis();
  bool connected = WiFi.status() == WL_CONNECTED;
  if (connected) {
    wifiConnectionPending = false;
    if (!wifiWasConnected) {
      Serial.println("Wi-Fi connected.");
      Serial.print("ESP32 IP address: ");
      Serial.println(WiFi.localIP());
      Serial.printf("Wi-Fi gateway: %s | DNS server: %s | RSSI: %d dBm\n",
                    WiFi.gatewayIP().toString().c_str(),
                    WiFi.dnsIP().toString().c_str(), WiFi.RSSI());
      Serial.printf("FastAPI target: http://%s:%u%s\n",
                    API_HOST, WOKWI_API_PORT, API_ROUTE);
      configTime(0, 0, "pool.ntp.org", "time.nist.gov");
      wifiWasConnected = true;
      apiHostResolved = false;
      lastDnsAttemptAt = 0;
    }
    if (!apiHostResolved &&
        (lastDnsAttemptAt == 0 || now - lastDnsAttemptAt >= DNS_RETRY_INTERVAL_MS)) {
      lastDnsAttemptAt = now;
      Serial.printf("Resolving API host %s...\n", API_HOST);
      if (WiFi.hostByName(API_HOST, apiHostAddress)) {
        apiHostResolved = true;
        Serial.printf("DNS resolved: %s -> %s\n",
                      API_HOST, apiHostAddress.toString().c_str());
      } else {
        Serial.printf("DNS lookup failed for %s. The Wokwi Public Gateway cannot reach "
                      "your computer; enable the Private IoT Gateway.\n", API_HOST);
      }
    }
    return;
  }

  if (wifiWasConnected) {
    Serial.println("Wi-Fi disconnected; readings will not be reported as saved.");
    wifiWasConnected = false;
    apiHostResolved = false;
  }
  if (wifiConnectionPending && now - lastWiFiAttemptAt >= WIFI_CONNECTION_TIMEOUT_MS) {
    Serial.printf("Wi-Fi connection timed out (status=%d). Check Wokwi-GUEST and the gateway.\n",
                  WiFi.status());
    wifiConnectionPending = false;
    lastWiFiAttemptAt = now;
  }
  if (!wifiConnectionPending && now - lastWiFiAttemptAt >= WIFI_RETRY_INTERVAL_MS) {
    connectWiFi();
  }
}

void sendReading(float elapsedSeconds) {
  char timestamp[32];
  tm currentTime = {};
  bool clockSynced = makeTimestamp(timestamp, sizeof(timestamp), currentTime);
  int adcValue = analogRead(POTENTIOMETER_PIN);
  float current = currentFromPotentiometer(adcValue);
  if (simulationMode == TEST_NORMAL_MODE) current = 2.5f;
  if (simulationMode == TEST_ANOMALY_MODE) current = 10.5f;

  const float voltage = SIMULATED_VOLTAGE_V;
  const float power = voltage * current;
  const float intervalEnergyKwh = power * elapsedSeconds / 3600000.0f;
  cumulativeEnergyKwh += intervalEnergyKwh;

  Serial.printf(
      "SIMULATED INPUT (not a physical measurement): ADC GPIO%d=%d | Mode: %s | "
      "Voltage: %.1f V | Current: %.2f A | Power: %.1f W | "
      "Interval energy: %.10f kWh | Elapsed: %.3f s | Timestamp: %s%s\n",
      POTENTIOMETER_PIN, adcValue, modeName(), voltage, current, power,
      intervalEnergyKwh, elapsedSeconds, timestamp,
      clockSynced ? "" : " (UTC clock not synchronized)");

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Cannot send reading: Wi-Fi is disconnected.");
    setIndicatorsOffline();
    lastDisplayedVoltage = voltage;
    lastDisplayedCurrent = current;
    lastDisplayedPower = power;
    lastIntervalEnergyKwh = intervalEnergyKwh;
    lastDisplayedStatus = "OFFLINE";
    apiConnected = false;
    lastHttpStatus = -1;
    return;
  }
  if (!apiHostResolved) {
    Serial.printf("Cannot send reading: API host %s is not resolved yet.\n", API_HOST);
    setIndicatorsOffline();
    lastDisplayedVoltage = voltage;
    lastDisplayedCurrent = current;
    lastDisplayedPower = power;
    lastIntervalEnergyKwh = intervalEnergyKwh;
    lastDisplayedStatus = "OFFLINE";
    apiConnected = false;
    lastHttpStatus = -1;
    return;
  }

  String payload = "{\"device_id\":\"" + String(WOKWI_DEVICE_ID) +
                   "\",\"timestamp\":\"" + String(timestamp) +
                   "\",\"voltage\":" + String(voltage, 1) +
                   ",\"current\":" + String(current, 3) +
                   ",\"power\":" + String(power, 2) +
                   ",\"interval_energy_kwh\":" + String(intervalEnergyKwh, 10) +
                   ",\"interval_seconds\":" + String(elapsedSeconds, 3) +
                   ",\"cumulative_energy_kwh\":" + String(cumulativeEnergyKwh, 10) +
                   ",\"data_source\":\"wokwi_simulation\"";
  String requestId = String(WOKWI_DEVICE_ID) + "-" +
                     String(static_cast<uint32_t>(esp_random()), HEX) + "-" +
                     String(static_cast<uint32_t>(esp_random()), HEX);
  payload += ",\"request_id\":\"" + requestId + "\"}";

  HTTPClient http;
  http.setTimeout(WOKWI_HTTP_TIMEOUT_MS);
  snprintf(API_URL, sizeof(API_URL), "http://%s:%u%s",
           API_HOST, WOKWI_API_PORT, API_ROUTE);
  if (!http.begin(API_URL)) {
    Serial.printf("HTTP setup failed for %s; check the gateway and API listener.\n", API_URL);
    setIndicatorsOffline();
    lastDisplayedVoltage = voltage;
    lastDisplayedCurrent = current;
    lastDisplayedPower = power;
    lastIntervalEnergyKwh = intervalEnergyKwh;
    lastDisplayedStatus = "OFFLINE";
    apiConnected = false;
    lastHttpStatus = -1;
    return;
  }
  http.addHeader("Content-Type", "application/json");
  int responseCode = -1;
  String response;
  for (int attempt = 0; attempt < 2; attempt++) {
    Serial.printf("POST /reading request_id=%s attempt=%d\n", requestId.c_str(), attempt + 1);
    responseCode = http.POST(payload);
    Serial.printf("FastAPI HTTP response code: %d\n", responseCode);
    response = responseCode > 0 ? http.getString() : "";
    if (responseCode == 201 || (responseCode >= 400 && responseCode < 500) || attempt == 1) {
      break;
    }

    if (responseCode > 0) {
      Serial.printf("Retrying after HTTP %d %s; response body:\n", responseCode, httpErrorLabel(responseCode));
      Serial.println(response);
    } else {
      Serial.printf("Retrying after transport error %d: %s\n", responseCode, http.errorToString(responseCode).c_str());
    }
    Serial.printf("Transient request failure; retrying once with request_id=%s\n", requestId.c_str());
    http.end();
    delay(100);
    if (!http.begin(API_URL)) {
      Serial.println("Retry setup failed; no reading success is reported.");
      responseCode = -1;
      break;
    }
    http.setTimeout(WOKWI_HTTP_TIMEOUT_MS);
    http.addHeader("Content-Type", "application/json");
  }

  if (responseCode == 201) {
    Serial.println("FastAPI response:");
    Serial.println(response);
    String status;
    float anomalyScore = 0.0f;
    if (hasValidInference(response, status, anomalyScore)) {
      lastDisplayedVoltage = voltage;
      lastDisplayedCurrent = current;
      lastDisplayedPower = power;
      lastIntervalEnergyKwh = intervalEnergyKwh;
      lastDisplayedStatus = status;
      lastAnomalyScore = anomalyScore;
      lastHttpStatus = responseCode;
      apiConnected = true;
      Serial.println("Reading accepted and stored by FastAPI.");
      setClassification(status);
    } else {
      Serial.println("HTTP 201 did not contain a valid persisted inference result.");
      Serial.println("Response body:");
      Serial.println(response);
      setIndicatorsOffline();
      lastDisplayedStatus = "WAITING";
      apiConnected = false;
      lastHttpStatus = responseCode;
    }
  } else {
    if (responseCode > 0) {
      Serial.printf("API request failed with HTTP %d %s.\n", responseCode, httpErrorLabel(responseCode));
      Serial.println(response);
    } else {
      Serial.printf("HTTP transport error %d: %s\n", responseCode, http.errorToString(responseCode).c_str());
    }
    setIndicatorsOffline();
    lastDisplayedVoltage = voltage;
    lastDisplayedCurrent = current;
    lastDisplayedPower = power;
    lastIntervalEnergyKwh = intervalEnergyKwh;
    lastDisplayedStatus = "OFFLINE";
    apiConnected = false;
    lastHttpStatus = responseCode > 0 ? responseCode : -1;
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(TEST_BUTTON_PIN, INPUT_PULLUP);
  analogReadResolution(12);
  analogSetPinAttenuation(POTENTIOMETER_PIN, ADC_11db);

  Wire.begin(21, 22);
  lcd.init();
  lcd.backlight();
  writeLcdLine(0, "V:-- I:-- A");
  writeLcdLine(1, "AI:WAITING");

  snprintf(API_URL, sizeof(API_URL), "http://%s:%u%s",
           API_HOST, WOKWI_API_PORT, API_ROUTE);
  Serial.printf("Configured API host=%s port=%u route=%s\n",
                API_HOST, WOKWI_API_PORT, API_ROUTE);
  Serial.printf("Configured API URL: %s\n", API_URL);
  connectWiFi();
  lastSentAt = millis();
  lastLcdScreenAt = millis();
  Serial.printf("Device ID: %s | Press MODE to cycle pot / test normal / test anomaly.\n", WOKWI_DEVICE_ID);
}

void loop() {
  updateTestButton();
  updateAlertPattern();

  updateWiFiConnection();
  updateLcdScreen();

  unsigned long now = millis();
  if (now - lastSentAt < SEND_INTERVAL_MS) {
    delay(10);
    return;
  }

  float elapsedSeconds = (now - lastSentAt) / 1000.0f;
  lastSentAt = now;
  sendReading(elapsedSeconds);
}
