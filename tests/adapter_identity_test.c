#include <stdio.h>

#include "gauge_adapter.h"

int main(void)
{
    gauge_adapter_t public_peer = {.address_type = 0, .address = {1, 2, 3, 4, 5, 6}};
    gauge_adapter_t other = public_peer;
    if (!gauge_adapter_same(&public_peer, &other) || !gauge_adapter_stable(&public_peer)) {
        return 1;
    }
    other.address[0] = 7;
    if (gauge_adapter_same(&public_peer, &other)) {
        return 2;
    }
    other = public_peer;
    other.address_type = 1;
    other.address[5] = 0xc1;
    if (!gauge_adapter_stable(&other)) {
        return 3;
    }
    other.address[5] = 0x41;
    if (gauge_adapter_stable(&other)) {
        return 4;
    }
    other.address[5] = 0x01;
    if (gauge_adapter_stable(&other)) {
        return 5;
    }
    other.address_type = 2;
    if (gauge_adapter_stable(&other)) {
        return 6;
    }
    return 0;
}
