#include "gauge_ui.h"

#include "adapter_ui.h"

static lv_obj_t* panel;
static lv_obj_t* arc;
static lv_obj_t* kind;
static lv_obj_t* value;
static lv_obj_t* unit;
static lv_obj_t* secondary;
static lv_obj_t* status;
static bool maf_primary;
static gauge_sample_t current;
static bool force_render;

static lv_obj_t* label_at(const char* text, const lv_font_t* font, int y, uint32_t color)
{
    lv_obj_t* label = lv_label_create(panel);
    lv_label_set_text(label, text);
    lv_obj_set_style_text_font(label, font, 0);
    lv_obj_set_style_text_color(label, lv_color_hex(color), 0);
    lv_obj_align(label, LV_ALIGN_TOP_MID, 0, y);
    return label;
}

static void on_tap(lv_event_t* event)
{
    (void)event;
    lv_indev_t* input = lv_indev_active();
    if (input != NULL) {
        lv_point_t point;
        lv_indev_get_point(input, &point);
        int x = point.x - 180;
        int y = point.y - 180;
        if (x * x + y * y > 180 * 180) {
            return;
        }
    }
    gauge_ui_toggle_primary();
}

static void settings_tap(lv_event_t* event)
{
    (void)event;
    adapter_ui_show_settings();
}

void gauge_ui_set_visible(bool visible)
{
    if (visible) {
        lv_obj_remove_flag(panel, LV_OBJ_FLAG_HIDDEN);
    } else {
        lv_obj_add_flag(panel, LV_OBJ_FLAG_HIDDEN);
    }
}

void gauge_ui_create(lv_obj_t* screen)
{
    maf_primary = false;
    current = (gauge_sample_t) {.link = GAUGE_DISCONNECTED, .simulated = true};
    lv_obj_set_style_bg_color(screen, lv_color_black(), 0);
    lv_obj_remove_flag(screen, LV_OBJ_FLAG_SCROLLABLE);

    panel = lv_obj_create(screen);
    lv_obj_set_size(panel, 360, 360);
    lv_obj_center(panel);
    lv_obj_set_style_radius(panel, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_clip_corner(panel, true, 0);
    lv_obj_set_style_bg_color(panel, lv_color_hex(0x080c12), 0);
    lv_obj_set_style_border_width(panel, 0, 0);
    lv_obj_set_style_pad_all(panel, 0, 0);
    lv_obj_remove_flag(panel, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_event_cb(panel, on_tap, LV_EVENT_CLICKED, NULL);

    arc = lv_arc_create(panel);
    lv_obj_set_size(arc, 334, 334);
    lv_obj_center(arc);
    lv_arc_set_rotation(arc, 135);
    lv_arc_set_bg_angles(arc, 0, 270);
    lv_arc_set_range(arc, 40, 120);
    lv_obj_remove_style(arc, NULL, LV_PART_KNOB);
    lv_obj_remove_flag(arc, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_style_arc_color(arc, lv_color_hex(0x202a38), LV_PART_MAIN);
    lv_obj_set_style_arc_width(arc, 5, LV_PART_MAIN);
    lv_obj_set_style_arc_width(arc, 5, LV_PART_INDICATOR);

    label_at("RX-8", &lv_font_montserrat_14, 55, 0x8392a5);
    lv_obj_t* menu = label_at("...", &lv_font_montserrat_24, 42, 0xffd54f);
    lv_obj_align(menu, LV_ALIGN_TOP_MID, 78, 42);
    lv_obj_add_flag(menu, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_style_pad_all(menu, 8, 0);
    lv_obj_add_event_cb(menu, settings_tap, LV_EVENT_CLICKED, NULL);
    kind = label_at("COOLANT", &lv_font_montserrat_18, 104, 0xcbd4df);
    value = label_at("--", &lv_font_montserrat_48, 137, 0xf5f7fa);
    unit = label_at("°C", &lv_font_montserrat_24, 194, 0xcbd4df);
    secondary = label_at("MAF -- g/s", &lv_font_montserrat_24, 237, 0xcbd4df);
    status = label_at("DISCONNECTED", &lv_font_montserrat_14, 285, 0x8392a5);
    label_at("tap to switch", &lv_font_montserrat_14, 309, 0x657488);
    force_render = true;
    gauge_ui_update(&current);
    adapter_ui_create(screen);
}

void gauge_ui_update(const gauge_sample_t* sample)
{
    bool unchanged = sample->link == current.link && sample->coolant_valid == current.coolant_valid
        && sample->maf_valid == current.maf_valid && sample->coolant_c == current.coolant_c
        && sample->maf_centi_gps == current.maf_centi_gps
        && sample->coolant_support == current.coolant_support
        && sample->maf_support == current.maf_support;
    if (unchanged && !force_render) {
        current = *sample;
        return;
    }
    gauge_sample_t previous = current;
    current = *sample;
    bool live = sample->link == GAUGE_LIVE;
    bool available = live && (maf_primary ? sample->maf_valid : sample->coolant_valid);
    uint32_t accent = live ? 0xffd54f : 0x657488;
    if (force_render) {
        lv_label_set_text(kind, maf_primary ? "AIRFLOW" : "COOLANT");
        lv_label_set_text(unit, maf_primary ? "g/s" : "°C");
    }
    if (!available) {
        lv_label_set_text(value, "--");
    } else if (maf_primary) {
        lv_label_set_text_fmt(
            value, "%d.%02d", sample->maf_centi_gps / 100, sample->maf_centi_gps % 100);
    } else {
        lv_label_set_text_fmt(value, "%d", sample->coolant_c);
    }
    if (maf_primary) {
        if (sample->coolant_support == GAUGE_PID_UNSUPPORTED) {
            lv_label_set_text(secondary, "Coolant unsupported");
        } else if (live && sample->coolant_valid) {
            lv_label_set_text_fmt(secondary, "Coolant %d°C", sample->coolant_c);
        } else {
            lv_label_set_text(secondary, "Coolant --°C");
        }
    } else if (sample->maf_support == GAUGE_PID_UNSUPPORTED) {
        lv_label_set_text(secondary, "MAF unsupported");
    } else if (live && sample->maf_valid) {
        lv_label_set_text_fmt(
            secondary, "MAF %d.%02d g/s", sample->maf_centi_gps / 100, sample->maf_centi_gps % 100);
    } else {
        lv_label_set_text(secondary, "MAF -- g/s");
    }
    const char* text = "DISCONNECTED";
    gauge_pid_support_t primary_support =
        maf_primary ? sample->maf_support : sample->coolant_support;
    if (sample->link == GAUGE_CONNECTING) {
        text = "CONNECTING";
    } else if (sample->link != GAUGE_DISCONNECTED && primary_support == GAUGE_PID_UNSUPPORTED) {
        text = maf_primary ? "MAF UNSUPPORTED" : "COOLANT UNSUPPORTED";
    } else if (sample->link == GAUGE_STALE) {
        text = "STALE / NO DATA";
    } else if (live) {
        text = available ? "LIVE" : (maf_primary ? "MAF UNAVAILABLE" : "COOLANT UNAVAILABLE");
    }
    lv_label_set_text(status, text);
    bool availability_changed = previous.link != sample->link
        || previous.coolant_valid != sample->coolant_valid
        || previous.maf_valid != sample->maf_valid;
    if (force_render || availability_changed) {
        lv_obj_set_style_text_color(status, lv_color_hex(accent), 0);
        lv_obj_set_style_text_color(value, lv_color_hex(available ? 0xf5f7fa : 0x657488), 0);
        lv_obj_set_style_arc_color(arc, lv_color_hex(accent), LV_PART_INDICATOR);
    }
    /* Illustrative coolant range, not an engine-health or oil-warmth indicator. */
    if (force_render || availability_changed || previous.coolant_c != sample->coolant_c) {
        lv_arc_set_value(arc, live && sample->coolant_valid ? sample->coolant_c : 40);
    }
    force_render = false;
}

void gauge_ui_toggle_primary(void)
{
    maf_primary = !maf_primary;
    force_render = true;
    gauge_ui_update(&current);
}
