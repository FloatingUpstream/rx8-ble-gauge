# Vendored board support

Source: https://github.com/waveshareteam/ESP32-S3-Touch-LCD-1.85B  
Commit: `139e6db584f3737fcfc6a958ee83b79fb69d317c`  
Original directory: `Examples/ESP-IDF-V5.5.3/02_lvgl_demo/components/`

Retained:

- `waveshare__esp32_s3_touch_lcd_1_85B`: vendor BSP (Apache-2.0; LICENSE retained).
- `waveshare__qmi8658`: local sensor component (license.txt retained).

Registry cache markers `CHECKSUMS.json` and `.component_hash` are omitted because
these are intentionally vendored source components, not a registry download.
No vendor source changes at initial import. The BSP includes unrelated audio,
RTC, and storage support; minimize later after bring-up.

Dependency versions and project settings are controlled by the main project.
Vendor metadata still contains references to an unrelated camera board; do not
use those descriptions to identify this hardware.
