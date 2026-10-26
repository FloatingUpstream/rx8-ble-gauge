#ifndef ELM_SESSION_H
#define ELM_SESSION_H
#include <stddef.h>
#include <stdint.h>

#include "gauge_sample.h"

typedef struct
{
    gauge_sample_t sample;
    char response[512];
    size_t length;
    unsigned command_index;
    bool waiting;
    bool failed;
    uint32_t sent_at;
    uint32_t next_at;
    uint32_t coolant_at;
    uint32_t maf_at;
    uint32_t discovery_at;
    bool capabilities_known;
} elm_session_t;

/* All calls belong to one context. Returned commands include CR. */
void elm_session_start(elm_session_t* session, uint32_t now, bool simulated);
const char* elm_session_poll(elm_session_t* session, uint32_t now);
void elm_session_feed(elm_session_t* session, const void* data, size_t length, uint32_t now);
void elm_session_disconnect(elm_session_t* session);
bool elm_session_initialized(const elm_session_t* session);
#endif
