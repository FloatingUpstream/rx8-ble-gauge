/* Deterministic virtual-time soak and byte fuzzing; not a physical-radio soak. */
#include <stdio.h>
#include <string.h>

#include "elm_decode.h"
#include "elm_session.h"

#define CHECK(condition) \
    do { \
        if (!(condition)) { \
            fprintf(stderr, "Failed line %d: %s\n", __LINE__, #condition); \
            return 1; \
        } \
    } while (0)

static uint32_t random_state = UINT32_C(0x8e1f3271);

static uint32_t random_word(void)
{
    random_state ^= random_state << 13;
    random_state ^= random_state >> 17;
    random_state ^= random_state << 5;
    return random_state;
}

int main(void)
{
    elm_session_t session;
    uint32_t now = UINT32_MAX - 50000;
    elm_session_start(&session, now, true);
    unsigned commands = 0;
    unsigned restarts = 0;
    unsigned valid_samples = 0;
    for (unsigned cycle = 1; cycle <= 500000; ++cycle) {
        now += 100;
        const char* command = elm_session_poll(&session, now);
        if (session.failed) {
            ++restarts;
            elm_session_start(&session, now, true);
            continue;
        }
        if (command == NULL) {
            continue;
        }
        ++commands;
        const char* reply;
        if (strcmp(command, "ATZ\r") == 0 || strcmp(command, "ATI\r") == 0) {
            reply = "ELM327 v2.2\r>";
        } else if (strncmp(command, "AT", 2) == 0) {
            reply = "OK\r>";
        } else if (strcmp(command, "0100\r") == 0) {
            reply = cycle % 5 == 0 ? "NO DATA\r>" : "410008010000\r>";
        } else if (strcmp(command, "0105\r") == 0) {
            reply = cycle % 17 == 0 ? "NO DATA\r>" : "SEARCHING...\r41057F\r>";
        } else if (strcmp(command, "0110\r") == 0) {
            reply = cycle % 19 == 0 ? "4110ZZZZ\r>" : "411004D8\r>";
        } else {
            CHECK(false);
        }
        if (cycle % 503 == 0) {
            now += 10000;
        }
        if (cycle % 701 == 0) {
            char oversized[600];
            memset(oversized, 'X', sizeof(oversized));
            elm_session_feed(&session, oversized, sizeof(oversized), now);
        } else {
            size_t length = strlen(reply);
            for (size_t offset = 0; offset < length;) {
                size_t fragment = 1 + random_word() % 7;
                if (fragment > length - offset) {
                    fragment = length - offset;
                }
                elm_session_feed(&session, reply + offset, fragment, now);
                offset += fragment;
            }
        }
        CHECK(!session.sample.coolant_valid || session.sample.coolant_c == 87);
        CHECK(!session.sample.maf_valid || session.sample.maf_centi_gps == 1240);
        if (session.sample.coolant_valid || session.sample.maf_valid) {
            ++valid_samples;
        }
    }
    for (unsigned i = 0; i < 100000; ++i) {
        char noise[128];
        for (size_t j = 0; j + 1 < sizeof(noise); ++j) {
            noise[j] = (char)(random_word() & 255);
        }
        noise[sizeof(noise) - 1] = '\0';
        int decoded;
        uint32_t bitmap;
        if (elm_decode_pid(noise, 0x05, &decoded)) {
            CHECK(decoded >= -40 && decoded <= 215);
        }
        if (elm_decode_pid(noise, 0x10, &decoded)) {
            CHECK(decoded >= 0 && decoded <= 65535);
        }
        (void)elm_decode_bitmap(noise, 0, &bitmap);
        elm_session_start(&session, now, true);
        now += 200;
        CHECK(elm_session_poll(&session, now) != NULL);
        elm_session_feed(&session, noise, sizeof(noise) - 1, now);
    }
    for (unsigned pid = 0; pid < 256; ++pid) {
        (void)elm_bitmap_supports(UINT32_MAX, (uint8_t)pid);
    }
    CHECK(commands > 100000 && valid_samples > 100000 && restarts > 100);
    printf("500000 virtual ticks, 100000 fuzz frames; commands=%u restarts=%u valid_ticks=%u\n",
           commands,
           restarts,
           valid_samples);
    return 0;
}
