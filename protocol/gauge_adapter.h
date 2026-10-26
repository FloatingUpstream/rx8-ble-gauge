#ifndef GAUGE_ADAPTER_H
#define GAUGE_ADAPTER_H
#include <stdbool.h>
#include <stdint.h>

#define GAUGE_ADAPTER_MAX 12

typedef struct
{
    uint8_t address_type;
    uint8_t address[6]; /* Bluetooth little-endian address. */
    char name[32];
} gauge_adapter_t;

static inline bool gauge_adapter_same(const gauge_adapter_t* left, const gauge_adapter_t* right)
{
    if (left->address_type != right->address_type) {
        return false;
    }
    for (unsigned i = 0; i < 6; ++i) {
        if (left->address[i] != right->address[i]) {
            return false;
        }
    }
    return true;
}

/* Public addresses and static random addresses can be remembered directly.
 * Rotating private addresses require identity resolution, not MAC pinning. */
static inline bool gauge_adapter_stable(const gauge_adapter_t* adapter)
{
    return adapter->address_type == 0
        || (adapter->address_type == 1 && (adapter->address[5] & 0xc0) == 0xc0);
}
#endif
