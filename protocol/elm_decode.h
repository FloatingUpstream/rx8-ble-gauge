#ifndef ELM_DECODE_H
#define ELM_DECODE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Headerless Mode 01 responses (ATH0); one request outstanding at a time.
 * Accept echoed commands and compact/spaced responses, reject malformed data. */
bool elm_decode_pid(const char* response, uint8_t pid, int* value);
/* OR matching ECU maps; corrupt matching maps cannot prove absence. */
bool elm_decode_bitmap(const char* response, uint8_t base, uint32_t* bitmap);
/* PID 1..32 within this table; the application currently uses the 0100 table. */
bool elm_bitmap_supports(uint32_t bitmap, uint8_t pid);

#endif
