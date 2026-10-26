#include "bsp/esp-bsp.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "gauge_ble.h"
#include "gauge_ui.h"
#include "nvs_flash.h"

static const char* tag = "rx8gauge";

void app_main(void)
{
    /* Don't silently erase existing factory NVS on incompatible data. */
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_LOGI(tag, "Shared gauge UI: BLE adapter discovery and saved selection");
    lv_display_t* display = bsp_display_start();
    ESP_ERROR_CHECK(display ? ESP_OK : ESP_FAIL);
    ESP_ERROR_CHECK(bsp_display_backlight_on());
    ESP_ERROR_CHECK(bsp_display_lock(1000));
    gauge_ui_create(lv_screen_active());
    const gauge_sample_t demo = {
        .link = GAUGE_CONNECTING, .simulated = true, .coolant_valid = false, .maf_valid = false};
    gauge_ui_update(&demo);
    bsp_display_unlock();
    gauge_ble_start();

    while (true) {
        ESP_LOGI(tag,
                 "BLE simulator gauge alive; free internal=%u, PSRAM=%u",
                 (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
                 (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
        vTaskDelay(pdMS_TO_TICKS(5000));
    }
}
