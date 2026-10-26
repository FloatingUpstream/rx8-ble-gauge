#include <SDL2/SDL.h>
#include <errno.h>
#include <limits.h>
#include <png.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "adapter_ui.h"
#include "elm_tcp.h"
#include "gauge_ui.h"

static const gauge_adapter_t* demo_adapters;

static void demo_select(const gauge_adapter_t* adapter)
{
    adapter_ui_set_selected(adapter, true);
    printf("fixture-selected: %.31s\n", adapter->name);
}

static void demo_scan(void)
{
    adapter_ui_set_candidates(demo_adapters, 3);
    adapter_ui_set_status("Tap a device to verify");
}

static void demo_forget(void)
{
    adapter_ui_set_selected(NULL, false);
    demo_scan();
    puts("fixture-forgotten");
}

static bool parse_unsigned(const char* text, unsigned maximum, unsigned* result)
{
    char* end;
    errno = 0;
    unsigned long parsed = strtoul(text, &end, 10);
    if (errno != 0 || *text == '\0' || *text == '-' || *end != '\0' || parsed > maximum) {
        return false;
    }
    *result = (unsigned)parsed;
    return true;
}

static bool snapshot(const char* path)
{
    lv_draw_buf_t* image = lv_snapshot_take(lv_screen_active(), LV_COLOR_FORMAT_RGB888);
    if (image == NULL) {
        return false;
    }
    png_image png = {.version = PNG_IMAGE_VERSION,
                     .width = image->header.w,
                     .height = image->header.h,
                     .format = PNG_FORMAT_BGR};
    bool result =
        png_image_write_to_file(&png, path, 0, image->data, (png_int_32)image->header.stride, NULL)
        != 0;
    if (!result) {
        fprintf(stderr, "PNG error: %s\n", png.message);
    }
    png_image_free(&png);
    lv_draw_buf_destroy(image);
    return result;
}

static bool fixture(const char* name, gauge_sample_t* sample)
{
    *sample = (gauge_sample_t) {.link = GAUGE_LIVE,
                                .simulated = true,
                                .coolant_valid = true,
                                .maf_valid = true,
                                .coolant_c = 87,
                                .maf_centi_gps = 1240};
    sample->coolant_support = GAUGE_PID_SUPPORTED;
    sample->maf_support = GAUGE_PID_SUPPORTED;
    if (strcmp(name, "normal") == 0) {
        return true;
    }
    if (strcmp(name, "cold") == 0) {
        sample->coolant_c = 20;
    } else if (strcmp(name, "hot") == 0) {
        sample->coolant_c = 110;
    } else if (strcmp(name, "missing") == 0) {
        sample->maf_valid = false;
    } else if (strcmp(name, "unsupported-maf") == 0) {
        sample->maf_valid = false;
        sample->maf_support = GAUGE_PID_UNSUPPORTED;
    } else if (strcmp(name, "unsupported-coolant") == 0) {
        sample->coolant_valid = false;
        sample->coolant_support = GAUGE_PID_UNSUPPORTED;
    } else if (strcmp(name, "unsupported-both") == 0) {
        sample->coolant_valid = false;
        sample->maf_valid = false;
        sample->coolant_support = GAUGE_PID_UNSUPPORTED;
        sample->maf_support = GAUGE_PID_UNSUPPORTED;
        sample->link = GAUGE_STALE;
    } else if (strcmp(name, "stale") == 0) {
        sample->link = GAUGE_STALE;
    } else if (strcmp(name, "disconnected") == 0) {
        sample->link = GAUGE_DISCONNECTED;
    } else if (strcmp(name, "connecting") == 0) {
        sample->link = GAUGE_CONNECTING;
    } else {
        return false;
    }
    return true;
}

int main(int argc, char** argv)
{
    const char* scenario = "normal";
    const char* image_path = NULL;
    unsigned seconds = 0;
    unsigned port = 0;
    bool maf = false;
    bool click = false;
    bool click_outside = false;
    bool picker_page = false;
    bool settings_page = false;
    bool empty_scan = false;
    unsigned click_x = 180;
    unsigned click_y = 180;
    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--maf") == 0) {
            maf = true;
        } else if (strcmp(argv[i], "--picker") == 0) {
            picker_page = true;
        } else if (strcmp(argv[i], "--settings") == 0) {
            settings_page = true;
        } else if (strcmp(argv[i], "--empty-scan") == 0) {
            empty_scan = true;
        } else if (i + 1 < argc && strcmp(argv[i], "--click-x") == 0) {
            if (!parse_unsigned(argv[++i], 359, &click_x)) {
                return 2;
            }
            click = true;
        } else if (i + 1 < argc && strcmp(argv[i], "--click-y") == 0) {
            if (!parse_unsigned(argv[++i], 359, &click_y)) {
                return 2;
            }
            click = true;
        } else if (strcmp(argv[i], "--click") == 0) {
            click = true;
        } else if (strcmp(argv[i], "--click-outside") == 0) {
            click = true;
            click_outside = true;
        } else if (i + 1 < argc && strcmp(argv[i], "--scenario") == 0) {
            scenario = argv[++i];
        } else if (i + 1 < argc && strcmp(argv[i], "--snapshot") == 0) {
            image_path = argv[++i];
        } else if (i + 1 < argc && strcmp(argv[i], "--seconds") == 0) {
            if (!parse_unsigned(argv[++i], UINT_MAX / 1000, &seconds)) {
                fprintf(stderr, "Invalid duration\n");
                return 2;
            }
        } else if (i + 1 < argc && strcmp(argv[i], "--elm-port") == 0) {
            if (!parse_unsigned(argv[++i], 65535, &port) || port == 0) {
                fprintf(stderr, "Invalid TCP port\n");
                return 2;
            }
        } else {
            fprintf(stderr, "Usage: %s [--scenario normal|cold|hot|missing|stale|disconnected|connecting]"
                            " [--maf] [--elm-port PORT] [--seconds N] [--snapshot FILE.png]\n", argv[0]);
            return 2;
        }
    }
    gauge_sample_t sample;
    if (!fixture(scenario, &sample)) {
        fprintf(stderr, "Unknown scenario: %s\n", scenario);
        return 2;
    }
    if (click && seconds == 0) {
        seconds = 1;
    }
    if (image_path != NULL && getenv("SDL_VIDEODRIVER") == NULL) {
        SDL_setenv("SDL_VIDEODRIVER", "dummy", 1);
    }
    lv_init();
    lv_display_t* display = lv_sdl_window_create(360, 360);
    if (display == NULL) {
        return 1;
    }
    lv_sdl_window_set_title(display, "RX-8 gauge");
    lv_indev_t* mouse = lv_sdl_mouse_create();
    lv_indev_set_display(mouse, display);
    gauge_ui_create(lv_screen_active());
    const gauge_adapter_t adapters[] = {
        /* Synthetic locally administered identities; never actual adapter addresses. */
        {.address_type = 0, .address = {0x01, 0, 0, 0, 0, 0x02}, .name = "RX8-ELM-SIM"},
        {.address_type = 0, .address = {0x02, 0, 0, 0, 0, 0x02}, .name = "VEEPEAK (fixture)"},
        {.address_type = 0, .address = {0x03, 0, 0, 0, 0, 0x02}, .name = "Other BLE device"},
    };
    adapter_ui_set_candidates(adapters, empty_scan ? 0 : 3);
    demo_adapters = adapters;
    const adapter_ui_actions_t demo_actions = {
        .select = demo_select,
        .scan = demo_scan,
        .forget = demo_forget,
    };
    adapter_ui_set_actions(&demo_actions);
    adapter_ui_set_selected(empty_scan ? NULL : &adapters[0], !empty_scan);
    adapter_ui_set_status(empty_scan ? "Scanning..." : "Tap a device to verify");
    if (picker_page) {
        adapter_ui_show_picker();
    } else if (settings_page) {
        adapter_ui_show_settings();
    }
    if (maf) {
        gauge_ui_toggle_primary();
    }
    if (port != 0) {
        sample = (gauge_sample_t) {.link = GAUGE_CONNECTING, .simulated = true};
        elm_tcp_start((uint16_t)port);
    }
    uint32_t started = SDL_GetTicks();
    uint32_t next_ui_update = 0;
    unsigned click_phase = 0;
    do {
        uint32_t elapsed = SDL_GetTicks() - started;
        if (click && ((click_phase == 0 && elapsed >= 50) || (click_phase == 1 && elapsed >= 150)))
        {
            SDL_Event event = {0};
            event.type = click_phase == 0 ? SDL_MOUSEBUTTONDOWN : SDL_MOUSEBUTTONUP;
            event.button.windowID = SDL_GetWindowID(lv_sdl_window_get_window(display));
            event.button.button = SDL_BUTTON_LEFT;
            event.button.state = click_phase == 0 ? SDL_PRESSED : SDL_RELEASED;
            event.button.x = click_outside ? 3 : (int)click_x;
            event.button.y = click_outside ? 3 : (int)click_y;
            SDL_PushEvent(&event);
            ++click_phase;
        }
        if (port != 0) {
            elm_tcp_poll(elapsed, &sample);
        }
        if (elapsed >= next_ui_update) {
            gauge_ui_update(&sample);
            next_ui_update = elapsed + 100;
        }
        lv_timer_handler();
        SDL_Delay(5);
        if (seconds != 0 && elapsed >= seconds * 1000) {
            break;
        }
    } while (image_path == NULL || seconds != 0);
    bool success = true;
    if (image_path != NULL) {
        gauge_ui_update(&sample);
        lv_obj_update_layout(lv_screen_active());
        success = snapshot(image_path);
        printf("link=%d coolant_valid=%d coolant=%d maf_valid=%d maf_centi=%d\n",
               sample.link,
               sample.coolant_valid,
               sample.coolant_c,
               sample.maf_valid,
               sample.maf_centi_gps);
        printf("coolant_support=%d maf_support=%d\n", sample.coolant_support, sample.maf_support);
    }
    elm_tcp_stop();
    lv_deinit();
    SDL_Quit();
    return success ? 0 : 1;
}
