// Waggle Camera Node — Camera abstraction layer.
// Wraps the ESP32 camera driver for the AI-Thinker ESP32-CAM board.
// Init, capture a JPEG frame, release the framebuffer, and deinit.

#pragma once

#include "esp_camera.h"

// Initialise the AI-Thinker ESP32-CAM with configured framesize and quality.
// Must be called before camera_capture().
// Returns true on success, false if the camera driver fails to start.
bool camera_init();

// Capture a single JPEG frame.
// Returns a pointer to the framebuffer (caller must release with camera_release),
// or nullptr on failure.
camera_fb_t* camera_capture();

// Release a previously captured framebuffer back to the driver.
void camera_release(camera_fb_t* fb);

// Deinitialise the camera driver to save power before deep sleep.
void camera_deinit();
