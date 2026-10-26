#ifndef GAUGE_SAMPLE_H
#define GAUGE_SAMPLE_H
#include <stdbool.h>

typedef enum
{
    GAUGE_CONNECTING,
    GAUGE_LIVE,
    GAUGE_STALE,
    GAUGE_DISCONNECTED,
} gauge_link_t;

typedef enum
{
    GAUGE_PID_UNKNOWN,
    GAUGE_PID_SUPPORTED,
    GAUGE_PID_UNSUPPORTED,
} gauge_pid_support_t;

typedef struct
{
    gauge_link_t link;
    bool simulated;
    bool coolant_valid;
    bool maf_valid;
    int coolant_c;
    int maf_centi_gps;
    gauge_pid_support_t coolant_support;
    gauge_pid_support_t maf_support;
} gauge_sample_t;
#endif
