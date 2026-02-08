// Waggle Sensor Node — Hardware pin definitions and tunables.
// All GPIO assignments match the Phase-1 spec schematic.

#ifndef CONFIG_H
#define CONFIG_H

// ── HX711 load-cell amplifier ───────────────────────────────────────
#define HX711_DOUT_PIN   16   // GPIO16 — HX711 data out
#define HX711_SCK_PIN     4   // GPIO4  — HX711 clock

// ── BME280 I2C environmental sensor ─────────────────────────────────
#define BME280_SDA_PIN   21   // GPIO21 — default I2C SDA
#define BME280_SCL_PIN   22   // GPIO22 — default I2C SCL
#define BME280_I2C_ADDR  0x76 // SDO tied low (common breakout default)

// ── Battery ADC ─────────────────────────────────────────────────────
#define BATTERY_PIN      34   // GPIO34 — ADC1_CH6 (input-only pin)
// Voltage divider: 100 k + 100 k → factor 2.
// ADC full-scale 3.3 V on 12-bit gives ~0.806 mV/count before divider.
#define BATTERY_DIVIDER_FACTOR  2

// ── Provisioning / status ───────────────────────────────────────────
#define PROVISION_PIN    27   // GPIO27 — active LOW enters provisioning
#define LED_PIN           2   // GPIO2  — on-board LED

// ── Timing ──────────────────────────────────────────────────────────
#define WAKE_INTERVAL_SEC  60 // Deep-sleep duration between readings

// ── ESP-NOW ─────────────────────────────────────────────────────────
#define ESPNOW_CHANNEL     1  // Wi-Fi channel for ESP-NOW
#define ESPNOW_MAX_RETRIES 3  // Transmit attempts before giving up
#define ESPNOW_RETRY_MS  100  // Delay between retries (ms)

// ── Battery thresholds ──────────────────────────────────────────────
#define LOW_BATTERY_MV  3300  // Below this → LOW_BATTERY flag set

// ── NVS namespace ───────────────────────────────────────────────────
#define NVS_NAMESPACE  "waggle"

#endif // CONFIG_H
