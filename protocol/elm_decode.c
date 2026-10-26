#include "elm_decode.h"

#include <ctype.h>

static int hex_digit(char digit)
{
    if (digit >= '0' && digit <= '9') {
        return digit - '0';
    }
    digit = (char)toupper((unsigned char)digit);
    return digit >= 'A' && digit <= 'F' ? digit - 'A' + 10 : -1;
}

static bool decode_line(
    const char* line, size_t length, uint8_t pid, size_t payload_bytes, uint32_t* value)
{
    char compact[12];
    size_t count = 0;
    for (size_t i = 0; i < length; ++i) {
        if (isspace((unsigned char)line[i])) {
            continue;
        }
        if (count == sizeof(compact) || hex_digit(line[i]) < 0) {
            return false;
        }
        compact[count++] = line[i];
    }
    if (count != (payload_bytes + 2) * 2) {
        return false;
    }
    uint8_t mode = (uint8_t)(hex_digit(compact[0]) * 16 + hex_digit(compact[1]));
    uint8_t response_pid = (uint8_t)(hex_digit(compact[2]) * 16 + hex_digit(compact[3]));
    if (mode != 0x41 || response_pid != pid) {
        return false;
    }
    *value = 0;
    for (size_t i = 4; i < count; i += 2) {
        *value = (*value << 8) | (uint32_t)(hex_digit(compact[i]) * 16 + hex_digit(compact[i + 1]));
    }
    return true;
}

static bool matching_header(const char* line, size_t length, uint8_t pid)
{
    unsigned header = 0;
    unsigned digits = 0;
    for (size_t i = 0; i < length && digits < 4; ++i) {
        if (isspace((unsigned char)line[i])) {
            continue;
        }
        int digit = hex_digit(line[i]);
        if (digit < 0) {
            return false;
        }
        header = (header << 4) | (unsigned)digit;
        ++digits;
    }
    return digits == 4 && header == (0x4100U | pid);
}

static bool decode_response(
    const char* response, uint8_t pid, size_t payload_bytes, bool merge, uint32_t* value)
{
    if (response == NULL || value == NULL) {
        return false;
    }
    uint32_t result = 0;
    bool found = false;
    const char* line = response;
    for (const char* cursor = response;; ++cursor) {
        if (*cursor == '\r' || *cursor == '\n' || *cursor == '>' || *cursor == '\0') {
            uint32_t decoded;
            if (decode_line(line, (size_t)(cursor - line), pid, payload_bytes, &decoded)) {
                result |= decoded;
                found = true;
                if (!merge) {
                    *value = result;
                    return true;
                }
            } else if (merge && matching_header(line, (size_t)(cursor - line), pid)) {
                /* Partial/corrupt ECU maps cannot prove a PID's absence. */
                return false;
            }
            if (*cursor == '\0') {
                break;
            }
            line = cursor + 1;
        }
    }
    if (found) {
        *value = result;
    }
    return found;
}

bool elm_decode_pid(const char* response, uint8_t pid, int* value)
{
    if (value == NULL || (pid != 0x05 && pid != 0x10)) {
        return false;
    }
    uint32_t decoded;
    if (!decode_response(response, pid, pid == 0x05 ? 1 : 2, false, &decoded)) {
        return false;
    }
    *value = pid == 0x05 ? (int)decoded - 40 : (int)decoded;
    return true;
}

bool elm_decode_bitmap(const char* response, uint8_t base, uint32_t* bitmap)
{
    return (base & 0x1f) == 0 && decode_response(response, base, 4, true, bitmap);
}

bool elm_bitmap_supports(uint32_t bitmap, uint8_t pid)
{
    return pid > 0 && pid <= 32 && (bitmap & (UINT32_C(1) << (32 - pid))) != 0;
}
