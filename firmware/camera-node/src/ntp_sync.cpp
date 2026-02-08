// Waggle Camera Node — NTP synchronisation implementation.

#include "ntp_sync.h"
#include "config.h"

#include <Arduino.h>
#include <time.h>
#include <esp_sntp.h>

// ── Track last sync time in RTC memory (survives deep sleep) ────────
RTC_DATA_ATTR static unsigned long s_last_sync_epoch = 0;

// ── Public API ──────────────────────────────────────────────────────

bool ntp_init() {
    log_i("Configuring NTP: server=%s", NTP_SERVER);

    // Configure timezone to UTC (beehive timestamps are always UTC)
    configTzTime("UTC0", NTP_SERVER);

    // Wait for NTP sync (poll every 250 ms, up to 5 seconds)
    int attempts = 0;
    const int max_attempts = 20;

    while (!ntp_synced() && attempts < max_attempts) {
        delay(250);
        attempts++;
    }

    if (ntp_synced()) {
        // Record the epoch of last sync so should_sync() can check later
        time_t now;
        time(&now);
        s_last_sync_epoch = (unsigned long)now;

        struct tm timeinfo;
        gmtime_r(&now, &timeinfo);
        log_i("NTP synced: %04d-%02d-%02dT%02d:%02d:%02dZ (attempt %d/%d)",
              timeinfo.tm_year + 1900, timeinfo.tm_mon + 1, timeinfo.tm_mday,
              timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec,
              attempts, max_attempts);
        return true;
    }

    log_e("NTP sync failed after %d attempts", max_attempts);
    return false;
}

bool ntp_synced() {
    time_t now;
    time(&now);
    struct tm timeinfo;
    gmtime_r(&now, &timeinfo);

    // If the year is >= 2024, we have a valid time (not the 1970 epoch default)
    return (timeinfo.tm_year + 1900) >= 2024;
}

String get_timestamp_iso8601() {
    time_t now;
    time(&now);
    struct tm timeinfo;
    gmtime_r(&now, &timeinfo);

    char buf[25];  // "2026-02-08T14:30:00Z" = 20 chars + null
    snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02dZ",
             timeinfo.tm_year + 1900,
             timeinfo.tm_mon + 1,
             timeinfo.tm_mday,
             timeinfo.tm_hour,
             timeinfo.tm_min,
             timeinfo.tm_sec);

    return String(buf);
}

bool should_sync() {
    // First boot — never synced
    if (s_last_sync_epoch == 0) {
        log_i("NTP sync needed: first boot (no previous sync)");
        return true;
    }

    time_t now;
    time(&now);
    unsigned long elapsed = (unsigned long)now - s_last_sync_epoch;

    if (elapsed >= NTP_SYNC_INTERVAL) {
        log_i("NTP sync needed: %lu s since last sync (threshold %d s)",
              elapsed, NTP_SYNC_INTERVAL);
        return true;
    }

    log_d("NTP sync not needed: %lu s since last sync", elapsed);
    return false;
}
