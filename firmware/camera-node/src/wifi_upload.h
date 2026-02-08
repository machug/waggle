// Waggle Camera Node — WiFi connection and HTTP photo upload.
// Connects to WiFi, POSTs a multipart/form-data JPEG to the hub,
// and disconnects to save power.

#pragma once

#include <stdint.h>
#include <stddef.h>

// Connect to WiFi with the given credentials.
// Blocks up to timeout_ms waiting for connection.
// Returns true on successful connection, false on timeout.
bool wifi_connect(const char* ssid, const char* pass, uint32_t timeout_ms);

// Disconnect from WiFi and turn off the radio to save power.
void wifi_disconnect();

// Upload a JPEG photo to the hub via HTTP POST multipart/form-data.
//
// url:        Full endpoint URL, e.g. "http://192.168.1.50:8000/api/hives/3/photos"
// api_key:    API key sent in X-API-Key header
// device_id:  Device UUID sent in X-Device-ID header
// jpeg_data:  Pointer to JPEG image bytes
// jpeg_len:   Length of JPEG data in bytes
// timestamp:  ISO 8601 timestamp string sent in X-Timestamp header
//
// Returns HTTP status code (200/201 on success), or -1 on connection/transport error.
int upload_photo(const char* url, const char* api_key, const char* device_id,
                 const uint8_t* jpeg_data, size_t jpeg_len,
                 const char* timestamp);
