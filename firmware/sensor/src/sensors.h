// Waggle Sensor Node — Sensor abstraction layer.
// Provides init + individual read functions for HX711, BME280, and battery ADC.
// Each read function returns a value (0 on error) and sets the appropriate
// error flag in the `flags` output parameter.

#ifndef SENSORS_H
#define SENSORS_H

#include <stdint.h>

// Initialise all sensors.  Returns a flags byte with error bits set for
// any sensor that failed to initialise (FLAG_HX711_ERROR, FLAG_BME280_ERROR).
uint8_t sensors_init();

// Read the load-cell weight in grams.
// On failure: returns 0 and sets FLAG_HX711_ERROR in *flags.
int32_t read_weight_g(uint8_t* flags);

// Read temperature in hundredths of a degree C (e.g. 3645 = 36.45 C).
// On failure: returns 0 and sets FLAG_BME280_ERROR in *flags.
int16_t read_temperature_x100(uint8_t* flags);

// Read relative humidity in hundredths of a percent (e.g. 5120 = 51.20%).
// On failure: returns 0 and sets FLAG_BME280_ERROR in *flags.
uint16_t read_humidity_x100(uint8_t* flags);

// Read barometric pressure in tenths of hPa (e.g. 10132 = 1013.2 hPa).
// On failure: returns 0 and sets FLAG_BME280_ERROR in *flags.
uint16_t read_pressure_x10(uint8_t* flags);

// Read battery voltage in millivolts via ADC with divider compensation.
uint16_t read_battery_mv();

#endif // SENSORS_H
