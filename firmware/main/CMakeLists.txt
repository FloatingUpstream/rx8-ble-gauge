idf_component_register(SRCS "app_main.c"
                       INCLUDE_DIRS "."
                       REQUIRES nvs_flash waveshare__esp32_s3_touch_lcd_1_85B gauge_ui gauge_ble)
