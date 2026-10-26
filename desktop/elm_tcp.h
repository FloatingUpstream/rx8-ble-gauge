#ifndef ELM_TCP_H
#define ELM_TCP_H

#include <stdint.h>

#include "gauge_ui.h"

/* Desktop-only loopback transport. Shares the decoder, not the BLE stack. */
void elm_tcp_start(uint16_t port);
void elm_tcp_poll(uint32_t now, gauge_sample_t* sample);
void elm_tcp_stop(void);

#endif
