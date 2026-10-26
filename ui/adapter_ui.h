#ifndef ADAPTER_UI_H
#define ADAPTER_UI_H
#include <stddef.h>

#include "gauge_adapter.h"
#include "lvgl.h"

typedef struct
{
    void (*select)(const gauge_adapter_t* adapter);
    void (*scan)(void);
    void (*forget)(void);
    void (*resume)(void);
} adapter_ui_actions_t;

void adapter_ui_create(lv_obj_t* screen);
void adapter_ui_set_actions(const adapter_ui_actions_t* actions);
void adapter_ui_show_picker(void);
void adapter_ui_show_settings(void);
void adapter_ui_show_dashboard(void);
void adapter_ui_set_candidates(const gauge_adapter_t* adapters, size_t count);
void adapter_ui_set_selected(const gauge_adapter_t* adapter, bool saved);
void adapter_ui_set_status(const char* text);
#endif
