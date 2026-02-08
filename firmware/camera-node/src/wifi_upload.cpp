// Waggle Camera Node — WiFi and HTTP upload implementation.

#include "wifi_upload.h"
#include "config.h"

#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>

// ── WiFi Connection ─────────────────────────────────────────────────

bool wifi_connect(const char* ssid, const char* pass, uint32_t timeout_ms) {
    log_i("Connecting to WiFi SSID: %s", ssid);

    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, pass);

    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - start >= timeout_ms) {
            log_e("WiFi connection timed out after %u ms", timeout_ms);
            WiFi.disconnect(true);
            WiFi.mode(WIFI_OFF);
            return false;
        }
        delay(100);
    }

    log_i("WiFi connected — IP: %s (took %lu ms)",
          WiFi.localIP().toString().c_str(), millis() - start);
    return true;
}

void wifi_disconnect() {
    WiFi.disconnect(true);   // true = erase AP credentials from RAM
    WiFi.mode(WIFI_OFF);
    log_i("WiFi disconnected, radio off");
}

// ── Multipart Upload ────────────────────────────────────────────────
//
// Builds a multipart/form-data body in memory with a single "file" part
// containing the JPEG data.  The boundary is a fixed string (safe since
// we control both ends and JPEG data won't contain it).

static const char* BOUNDARY = "----WaggleCamBoundary7d2a";

int upload_photo(const char* url, const char* api_key, const char* device_id,
                 const uint8_t* jpeg_data, size_t jpeg_len,
                 const char* timestamp) {

    if (WiFi.status() != WL_CONNECTED) {
        log_e("upload_photo called but WiFi not connected");
        return -1;
    }

    // ── Build multipart body ────────────────────────────────────────
    // Header part (text)
    String part_header = String("--") + BOUNDARY + "\r\n"
        "Content-Disposition: form-data; name=\"file\"; filename=\"capture.jpg\"\r\n"
        "Content-Type: image/jpeg\r\n\r\n";

    // Footer part (text)
    String part_footer = String("\r\n--") + BOUNDARY + "--\r\n";

    size_t total_len = part_header.length() + jpeg_len + part_footer.length();

    // ── Assemble into a contiguous buffer ───────────────────────────
    // We use PSRAM-aware malloc since JPEG can be large (VGA ~30-80 KB)
    uint8_t* body = (uint8_t*)ps_malloc(total_len);
    if (body == nullptr) {
        // Fallback to regular malloc if PSRAM not available
        body = (uint8_t*)malloc(total_len);
    }
    if (body == nullptr) {
        log_e("Failed to allocate %u bytes for multipart body", total_len);
        return -1;
    }

    size_t offset = 0;
    memcpy(body + offset, part_header.c_str(), part_header.length());
    offset += part_header.length();
    memcpy(body + offset, jpeg_data, jpeg_len);
    offset += jpeg_len;
    memcpy(body + offset, part_footer.c_str(), part_footer.length());

    // ── HTTP POST ───────────────────────────────────────────────────
    HTTPClient http;
    http.begin(url);
    http.setTimeout(15000);  // 15 s server response timeout

    // Custom headers
    http.addHeader("X-API-Key", api_key);
    http.addHeader("X-Device-ID", device_id);
    http.addHeader("X-Timestamp", timestamp);

    String content_type = String("multipart/form-data; boundary=") + BOUNDARY;
    http.addHeader("Content-Type", content_type);

    log_i("Uploading %u bytes to %s", total_len, url);
    unsigned long t0 = millis();

    int http_code = http.POST(body, total_len);

    unsigned long elapsed = millis() - t0;

    if (http_code > 0) {
        log_i("Upload complete: HTTP %d (%lu ms)", http_code, elapsed);
        // Read and discard response body to free resources
        http.getString();
    } else {
        log_e("Upload failed: %s (code %d, %lu ms)",
              http.errorToString(http_code).c_str(), http_code, elapsed);
    }

    http.end();
    free(body);

    return http_code;
}
