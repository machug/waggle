// Waggle Sensor Node — Sensor implementations.

#include "sensors.h"
#include "config.h"
#include "payload.h"  // flag constants

#include <Arduino.h>
#include <Wire.h>
#include <HX711.h>
#include <Adafruit_BME280.h>

// ── Module-level sensor objects ─────────────────────────────────────
static HX711 scale;
static Adafruit_BME280 bme;

static bool hx711_ok  = false;
static bool bme280_ok = false;

// ── NVS-backed calibration values (loaded by provision module) ──────
// Declared extern so the provisioning module can set them after reading NVS.
extern float hx711_scale_factor;  // counts per gram
extern long  hx711_offset;        // tare offset

// ── Init ────────────────────────────────────────────────────────────
uint8_t sensors_init() {
    uint8_t flags = 0;

    // HX711
    scale.begin(HX711_DOUT_PIN, HX711_SCK_PIN);
    if (scale.wait_ready_timeout(1000)) {
        scale.set_scale(hx711_scale_factor);
        scale.set_offset(hx711_offset);
        hx711_ok = true;
        log_i("HX711 initialised (scale=%.2f, offset=%ld)", hx711_scale_factor, hx711_offset);
    } else {
        hx711_ok = false;
        flags |= FLAG_HX711_ERROR;
        log_e("HX711 init failed — sensor not ready");
    }

    // BME280 over I2C
    Wire.begin(BME280_SDA_PIN, BME280_SCL_PIN);
    if (bme.begin(BME280_I2C_ADDR, &Wire)) {
        // Force mode: single measurement then sleep (low power)
        bme.setSampling(Adafruit_BME280::MODE_FORCED,
                        Adafruit_BME280::SAMPLING_X1,   // temp
                        Adafruit_BME280::SAMPLING_X1,   // pressure
                        Adafruit_BME280::SAMPLING_X1,   // humidity
                        Adafruit_BME280::FILTER_OFF,
                        Adafruit_BME280::STANDBY_MS_0_5);
        bme280_ok = true;
        log_i("BME280 initialised at 0x%02X", BME280_I2C_ADDR);
    } else {
        bme280_ok = false;
        flags |= FLAG_BME280_ERROR;
        log_e("BME280 init failed — check wiring / address 0x%02X", BME280_I2C_ADDR);
    }

    // Battery ADC — no special init needed; analogRead works on input-only pins.
    analogSetAttenuation(ADC_11db);  // 0–3.3 V range

    return flags;
}

// ── Weight ──────────────────────────────────────────────────────────
int32_t read_weight_g(uint8_t* flags) {
    if (!hx711_ok) {
        *flags |= FLAG_HX711_ERROR;
        return 0;
    }
    if (!scale.is_ready()) {
        log_w("HX711 not ready during read");
        *flags |= FLAG_HX711_ERROR;
        return 0;
    }
    // Average 5 readings for stability
    float grams = scale.get_units(5);
    log_d("Weight: %.1f g", grams);
    return (int32_t)grams;
}

// ── Temperature ─────────────────────────────────────────────────────
int16_t read_temperature_x100(uint8_t* flags) {
    if (!bme280_ok) {
        *flags |= FLAG_BME280_ERROR;
        return 0;
    }
    bme.takeForcedMeasurement();
    float t = bme.readTemperature();
    if (isnan(t)) {
        *flags |= FLAG_BME280_ERROR;
        return 0;
    }
    log_d("Temp: %.2f C", t);
    return (int16_t)(t * 100.0f);
}

// ── Humidity ────────────────────────────────────────────────────────
uint16_t read_humidity_x100(uint8_t* flags) {
    if (!bme280_ok) {
        *flags |= FLAG_BME280_ERROR;
        return 0;
    }
    float h = bme.readHumidity();
    if (isnan(h)) {
        *flags |= FLAG_BME280_ERROR;
        return 0;
    }
    log_d("Humidity: %.2f %%", h);
    return (uint16_t)(h * 100.0f);
}

// ── Pressure ────────────────────────────────────────────────────────
uint16_t read_pressure_x10(uint8_t* flags) {
    if (!bme280_ok) {
        *flags |= FLAG_BME280_ERROR;
        return 0;
    }
    float p = bme.readPressure() / 100.0f;  // Pa → hPa
    if (isnan(p)) {
        *flags |= FLAG_BME280_ERROR;
        return 0;
    }
    log_d("Pressure: %.1f hPa", p);
    return (uint16_t)(p * 10.0f);
}

// ── Battery ─────────────────────────────────────────────────────────
uint16_t read_battery_mv() {
    // ESP32 ADC: 12-bit (0-4095), 0-3.3 V range with 11 dB attenuation.
    // With a 100k+100k voltage divider, actual voltage = ADC voltage * 2.
    uint32_t raw = analogRead(BATTERY_PIN);
    // analogRead with 11 dB attenuation maps 0-3.3 V to 0-4095.
    // mV = raw * 3300 / 4095 * DIVIDER_FACTOR
    uint16_t mv = (uint16_t)((raw * 3300UL * BATTERY_DIVIDER_FACTOR) / 4095UL);
    log_d("Battery: %u mV (raw=%u)", mv, raw);
    return mv;
}
