#include "elm_decode.h"

#include <stdio.h>

#define CHECK(condition) \
    do { \
        if (!(condition)) { \
            fprintf(stderr, "Failed at line %d: %s\n", __LINE__, #condition); \
            return 1; \
        } \
    } while (0)

int main(void)
{
    int value = 999;
    uint32_t bitmap = 0;
    CHECK(elm_decode_bitmap("0100\r41 00 08 01 00 00\r>", 0, &bitmap));
    CHECK(bitmap == UINT32_C(0x08010000));
    CHECK(elm_bitmap_supports(bitmap, 0x05) && elm_bitmap_supports(bitmap, 0x10));
    CHECK(!elm_bitmap_supports(bitmap, 0) && !elm_bitmap_supports(bitmap, 33));
    CHECK(elm_decode_bitmap("410008000000\r410000010000\r>", 0, &bitmap));
    CHECK(bitmap == UINT32_C(0x08010000)); /* Two ECU support maps. */
    CHECK(!elm_decode_bitmap("410000000000\r41 00 08 01 ZZ ZZ\r>", 0, &bitmap));
    CHECK(elm_decode_bitmap("410000000000\r>", 0, &bitmap) && bitmap == 0);
    CHECK(!elm_decode_bitmap("NO DATA\r>", 0, &bitmap));
    CHECK(!elm_decode_bitmap("41000801000000\r>", 0, &bitmap));
    CHECK(!elm_decode_bitmap("4100080100\r>", 0, &bitmap));
    CHECK(!elm_decode_bitmap("410008010000\r>", 1, &bitmap));
    CHECK(elm_decode_pid("0105\r41 05 7F\r>", 0x05, &value) && value == 87);
    CHECK(elm_decode_pid("41053c\r>", 0x05, &value) && value == 20);
    CHECK(elm_decode_pid("41 10 04 D8\r>", 0x10, &value) && value == 1240);
    CHECK(!elm_decode_pid("NO DATA\r>", 0x05, &value));
    CHECK(!elm_decode_pid("41 05 ZZ\r>", 0x05, &value));
    CHECK(!elm_decode_pid("41 05 7F 00\r>", 0x05, &value));
    CHECK(!elm_decode_pid("41 10 7F\r>", 0x10, &value));
    CHECK(!elm_decode_pid("7E8 03 41 05 7F\r>", 0x05, &value));
    CHECK(!elm_decode_pid("41 0C 00 00\r>", 0x0c, &value));
    CHECK(!elm_decode_pid(NULL, 0x05, &value));
    CHECK(!elm_decode_pid("41 05 7F", 0x05, NULL));
    return 0;
}
