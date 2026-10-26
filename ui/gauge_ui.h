#ifndef GAUGE_UI_H
#define GAUGE_UI_H

#include "gauge_sample.h"
#include "lvgl.h"

/* One UI instance, owned and updated exclusively in the LVGL context. */
void gauge_ui_create(lv_obj_t* screen);
void gauge_ui_update(const gauge_sample_t* sample);
void gauge_ui_toggle_primary(void);
void gauge_ui_set_visible(bool visible);

#endif
