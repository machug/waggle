// Waggle Camera Node — NTP time synchronisation.
// Syncs the ESP32 RTC to NTP on first boot and every 24 hours thereafter.
// Provides ISO 8601 timestamps for photo metadata.

#pragma once

#include <Arduino.h>

// Configure the SNTP client and trigger a sync.
// WiFi must be connected before calling this.
// Returns true if time was successfully synchronised within ~5 seconds.
bool ntp_init();

// Check whether the system clock has been set via NTP.
// Returns true if the year is >= 2024 (i.e., not the 1970 epoch default).
bool ntp_synced();

// Get the current time as an ISO 8601 string (e.g. "2026-02-08T14:30:00Z").
// Returns "1970-01-01T00:00:00Z" if NTP has not synced yet.
String get_timestamp_iso8601();

// Check whether an NTP sync is needed.
// Returns true on first call or if more than NTP_SYNC_INTERVAL seconds
// have elapsed since the last successful sync.
bool should_sync();
