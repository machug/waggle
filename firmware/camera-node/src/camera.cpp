// Waggle Camera Node — Camera driver implementation.
// Pin assignments are for the AI-Thinker ESP32-CAM board.

#include "camera.h"
#include "config.h"

#include <Arduino.h>

// ── AI-Thinker ESP32-CAM pin configuration ──────────────────────────
static camera_config_t make_camera_config() {
    camera_config_t config;

    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer   = LEDC_TIMER_0;

    config.pin_pwdn     = 32;
    config.pin_reset    = -1;
    config.pin_xclk     = 0;
    config.pin_sscb_sda = 26;
    config.pin_sscb_scl = 27;

    config.pin_d7       = 35;
    config.pin_d6       = 34;
    config.pin_d5       = 39;
    config.pin_d4       = 36;
    config.pin_d3       = 21;
    config.pin_d2       = 19;
    config.pin_d1       = 18;
    config.pin_d0       = 5;

    config.pin_vsync    = 25;
    config.pin_href     = 23;
    config.pin_pclk     = 22;

    config.xclk_freq_hz = 20000000;       // 20 MHz XCLK
    config.pixel_format = PIXFORMAT_JPEG;

    // Use PSRAM for frame buffer if available (ESP32-CAM has 4 MB PSRAM)
    if (psramFound()) {
        config.frame_size   = CAMERA_FRAMESIZE;
        config.jpeg_quality = CAMERA_QUALITY;
        config.fb_count     = 2;           // Double buffer for smoother capture
        config.fb_location  = CAMERA_FB_IN_PSRAM;
        config.grab_mode    = CAMERA_GRAB_LATEST;
        log_i("PSRAM found — using PSRAM for frame buffers");
    } else {
        // Fallback for boards without PSRAM (unlikely for AI-Thinker)
        config.frame_size   = FRAMESIZE_SVGA;
        config.jpeg_quality = 16;          // Lower quality to fit in DRAM
        config.fb_count     = 1;
        config.fb_location  = CAMERA_FB_IN_DRAM;
        config.grab_mode    = CAMERA_GRAB_WHEN_EMPTY;
        log_w("No PSRAM — falling back to SVGA/quality 16");
    }

    return config;
}

// ── Public API ──────────────────────────────────────────────────────

bool camera_init() {
    // Power-down pin must be driven LOW to enable the camera
    pinMode(32, OUTPUT);
    digitalWrite(32, LOW);
    delay(10);

    camera_config_t config = make_camera_config();

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        log_e("Camera init failed: 0x%x", err);
        return false;
    }

    // Adjust sensor settings for beehive conditions (outdoor, variable light)
    sensor_t* s = esp_camera_sensor_get();
    if (s != nullptr) {
        s->set_brightness(s, 0);      // Default brightness
        s->set_contrast(s, 0);        // Default contrast
        s->set_saturation(s, 0);      // Default saturation
        s->set_whitebal(s, 1);        // Auto white balance ON
        s->set_awb_gain(s, 1);        // AWB gain ON
        s->set_wb_mode(s, 0);         // Auto WB mode
        s->set_exposure_ctrl(s, 1);   // Auto exposure ON
        s->set_aec2(s, 1);            // AEC DSP ON
        s->set_gain_ctrl(s, 1);       // Auto gain ON
        s->set_agc_gain(s, 0);        // AGC gain 0
        s->set_gainceiling(s, (gainceiling_t)6);  // 64x max gain for low light
        s->set_bpc(s, 1);             // Black pixel correction ON
        s->set_wpc(s, 1);             // White pixel correction ON
        s->set_raw_gma(s, 1);         // Gamma correction ON
        s->set_lenc(s, 1);            // Lens correction ON
    }

    log_i("Camera initialised: framesize=%d quality=%d", CAMERA_FRAMESIZE, CAMERA_QUALITY);
    return true;
}

camera_fb_t* camera_capture() {
    // Discard first frame — auto-exposure often needs one frame to settle
    camera_fb_t* discard = esp_camera_fb_get();
    if (discard != nullptr) {
        esp_camera_fb_return(discard);
    }

    camera_fb_t* fb = esp_camera_fb_get();
    if (fb == nullptr) {
        log_e("Camera capture failed");
        return nullptr;
    }

    log_i("Captured frame: %u bytes, %ux%u", fb->len, fb->width, fb->height);
    return fb;
}

void camera_release(camera_fb_t* fb) {
    if (fb != nullptr) {
        esp_camera_fb_return(fb);
    }
}

void camera_deinit() {
    esp_err_t err = esp_camera_deinit();
    if (err != ESP_OK) {
        log_w("Camera deinit returned 0x%x (may be benign)", err);
    } else {
        log_i("Camera deinitialised");
    }
}
