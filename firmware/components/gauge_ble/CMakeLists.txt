set(central_utils "$ENV{IDF_PATH}/examples/bluetooth/nimble/common/nimble_central_utils")
idf_component_register(SRCS "gauge_ble.c" "${central_utils}/peer.c"
                       INCLUDE_DIRS "." "${central_utils}"
                       REQUIRES bt freertos esp_timer nvs_flash gauge_ui elm_decode
                                waveshare__esp32_s3_touch_lcd_1_85B)
