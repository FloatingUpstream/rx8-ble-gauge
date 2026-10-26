#include "adapter_ui.h"

#include <stdio.h>
#include <string.h>

#include "gauge_ui.h"

static lv_obj_t* picker;
static lv_obj_t* settings;
static lv_obj_t* rows;
static lv_obj_t* scan_status;
static lv_obj_t* selected_name;
static lv_obj_t* selected_address;
static lv_obj_t* selected_state;
static gauge_adapter_t candidates[GAUGE_ADAPTER_MAX];
static adapter_ui_actions_t actions;

static lv_obj_t* label(lv_obj_t* parent, const char* text, int y, const lv_font_t* font)
{
    lv_obj_t* object = lv_label_create(parent);
    lv_label_set_text(object, text);
    lv_obj_set_style_text_font(object, font, 0);
    lv_obj_set_style_text_color(object, lv_color_hex(0xcbd4df), 0);
    lv_obj_align(object, LV_ALIGN_TOP_MID, 0, y);
    return object;
}

static lv_obj_t* page(lv_obj_t* screen, const char* heading)
{
    lv_obj_t* object = lv_obj_create(screen);
    lv_obj_set_size(object, 360, 360);
    lv_obj_center(object);
    lv_obj_set_style_radius(object, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_clip_corner(object, true, 0);
    lv_obj_set_style_bg_color(object, lv_color_hex(0x080c12), 0);
    lv_obj_set_style_border_width(object, 0, 0);
    lv_obj_set_style_pad_all(object, 0, 0);
    lv_obj_remove_flag(object, LV_OBJ_FLAG_SCROLLABLE);
    label(object, "RX-8", 55, &lv_font_montserrat_14);
    label(object, heading, 86, &lv_font_montserrat_24);
    lv_obj_add_flag(object, LV_OBJ_FLAG_HIDDEN);
    return object;
}

static lv_obj_t* button(
    lv_obj_t* parent, const char* text, int x, int y, int width, lv_event_cb_t callback, void* data)
{
    lv_obj_t* object = lv_button_create(parent);
    lv_obj_set_size(object, width, 34);
    lv_obj_align(object, LV_ALIGN_TOP_MID, x, y);
    lv_obj_set_style_bg_color(object, lv_color_hex(0x202a38), 0);
    lv_obj_set_style_radius(object, 8, 0);
    lv_obj_set_style_shadow_width(object, 0, 0);
    lv_obj_t* caption = label(object, text, 0, &lv_font_montserrat_14);
    lv_obj_set_style_text_color(caption, lv_color_hex(0xffd54f), 0);
    lv_obj_center(caption);
    lv_obj_add_event_cb(object, callback, LV_EVENT_CLICKED, data);
    return object;
}

void adapter_ui_show_dashboard(void)
{
    lv_obj_add_flag(picker, LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(settings, LV_OBJ_FLAG_HIDDEN);
    gauge_ui_set_visible(true);
}

void adapter_ui_show_picker(void)
{
    gauge_ui_set_visible(false);
    lv_obj_add_flag(settings, LV_OBJ_FLAG_HIDDEN);
    lv_obj_remove_flag(picker, LV_OBJ_FLAG_HIDDEN);
}

void adapter_ui_show_settings(void)
{
    gauge_ui_set_visible(false);
    lv_obj_add_flag(picker, LV_OBJ_FLAG_HIDDEN);
    lv_obj_remove_flag(settings, LV_OBJ_FLAG_HIDDEN);
}

static void back(lv_event_t* event)
{
    (void)event;
    if (actions.resume != NULL) {
        actions.resume();
    }
    adapter_ui_show_dashboard();
}

static void refresh(lv_event_t* event)
{
    (void)event;
    adapter_ui_set_status("Scanning...");
    if (actions.scan != NULL) {
        actions.scan();
    }
}

static void choose(lv_event_t* event)
{
    adapter_ui_show_picker();
    refresh(event);
}

static void forget(lv_event_t* event)
{
    (void)event;
    if (actions.forget != NULL) {
        actions.forget();
    }
    adapter_ui_show_picker();
}

static void pick(lv_event_t* event)
{
    const gauge_adapter_t* adapter = lv_event_get_user_data(event);
    if (adapter != NULL && actions.select != NULL) {
        actions.select(adapter);
        adapter_ui_show_dashboard();
    }
}

void adapter_ui_create(lv_obj_t* screen)
{
    memset(&actions, 0, sizeof(actions));
    picker = page(screen, "Choose adapter");
    rows = lv_obj_create(picker);
    lv_obj_set_size(rows, 270, 154);
    lv_obj_align(rows, LV_ALIGN_TOP_MID, 0, 121);
    lv_obj_set_style_bg_opa(rows, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(rows, 0, 0);
    lv_obj_set_style_pad_all(rows, 0, 0);
    lv_obj_set_style_pad_row(rows, 6, 0);
    lv_obj_set_flex_flow(rows, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_scroll_dir(rows, LV_DIR_VER);
    scan_status = label(picker, "Scanning...", 282, &lv_font_montserrat_14);
    button(picker, "Refresh", -54, 307, 94, refresh, NULL);
    button(picker, "Back", 54, 307, 94, back, NULL);
    settings = page(screen, "Adapter");
    selected_name = label(settings, "None selected", 132, &lv_font_montserrat_18);
    lv_obj_set_width(selected_name, 250);
    lv_obj_set_style_text_align(selected_name, LV_TEXT_ALIGN_CENTER, 0);
    lv_label_set_long_mode(selected_name, LV_LABEL_LONG_DOT);
    selected_address = label(settings, "--", 169, &lv_font_montserrat_14);
    selected_state = label(settings, "Not saved", 198, &lv_font_montserrat_14);
    button(settings, "Choose adapter", 0, 231, 208, choose, NULL);
    button(settings, "Forget adapter", 0, 276, 208, forget, NULL);
    button(settings, "Back", -76, 43, 60, back, NULL);
}

void adapter_ui_set_actions(const adapter_ui_actions_t* callbacks)
{
    actions = *callbacks;
}

void adapter_ui_set_candidates(const gauge_adapter_t* adapters, size_t count)
{
    if (count > GAUGE_ADAPTER_MAX) {
        count = GAUGE_ADAPTER_MAX;
    }
    if (count != 0) {
        memcpy(candidates, adapters, count * sizeof(*adapters));
    }
    lv_obj_clean(rows);
    if (count == 0) {
        label(rows, "No named devices yet", 20, &lv_font_montserrat_14);
    }
    for (size_t i = 0; i < count; ++i) {
        const gauge_adapter_t* adapter = &candidates[i];
        char text[80];
        snprintf(text,
                 sizeof(text),
                 "%.31s\n%02X:%02X:%02X:%02X:%02X:%02X",
                 adapter->name,
                 adapter->address[5],
                 adapter->address[4],
                 adapter->address[3],
                 adapter->address[2],
                 adapter->address[1],
                 adapter->address[0]);
        lv_obj_t* row = button(rows, text, 0, 0, 262, pick, &candidates[i]);
        lv_obj_set_height(row, 54);
    }
}

void adapter_ui_set_selected(const gauge_adapter_t* adapter, bool saved)
{
    if (adapter == NULL) {
        lv_label_set_text(selected_name, "None selected");
        lv_label_set_text(selected_address, "--");
        lv_label_set_text(selected_state, "Not saved");
        return;
    }
    lv_label_set_text_fmt(selected_name, "%.31s", adapter->name);
    lv_label_set_text_fmt(selected_address,
                          "%02X:%02X:%02X:%02X:%02X:%02X",
                          adapter->address[5],
                          adapter->address[4],
                          adapter->address[3],
                          adapter->address[2],
                          adapter->address[1],
                          adapter->address[0]);
    lv_label_set_text(selected_state, saved ? "Saved / auto reconnect" : "Not saved");
}

void adapter_ui_set_status(const char* text)
{
    lv_label_set_text(scan_status, text);
}
