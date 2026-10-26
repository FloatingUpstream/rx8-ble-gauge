#include "elm_session.h"

#include <stdio.h>
#include <string.h>

#define CHECK(condition) \
    do { \
        if (!(condition)) { \
            fprintf(stderr, "Failed line %d: %s\n", __LINE__, #condition); \
            return 1; \
        } \
    } while (0)

int main(void)
{
    elm_session_t session;
    uint32_t now = 0;
    elm_session_start(&session, now, true);
    CHECK(elm_session_poll(&session, now) == NULL);
    const char* const init[] = {
        "ATZ\r", "ATE0\r", "ATL0\r", "ATS0\r", "ATH0\r", "ATSP0\r", "ATI\r"};
    for (unsigned i = 0; i < 7; ++i) {
        now += 200;
        CHECK(strcmp(elm_session_poll(&session, now), init[i]) == 0);
        CHECK(elm_session_poll(&session, now) == NULL);
        const char* response = (i == 0 || i == 6) ? "ELM327 v1.5\r>" : "OK\r>";
        for (size_t j = 0; j < strlen(response); ++j) {
            elm_session_feed(&session, response + j, 1, now);
        }
        CHECK(!session.failed);
        CHECK(elm_session_initialized(&session) == (i == 6));
    }
    now += 200;
    CHECK(strcmp(elm_session_poll(&session, now), "0100\r") == 0);
    elm_session_feed(&session, "410008010000\r>", 14, now);
    CHECK(session.capabilities_known);
    CHECK(session.sample.coolant_support == GAUGE_PID_SUPPORTED);
    CHECK(session.sample.maf_support == GAUGE_PID_SUPPORTED);
    now += 200;
    CHECK(strcmp(elm_session_poll(&session, now), "0105\r") == 0);
    const char coolant[] = "SEARCHING...\r41 05 7F\r>";
    elm_session_feed(&session, coolant, sizeof(coolant) - 1, now);
    CHECK(session.sample.coolant_valid && session.sample.coolant_c == 87);
    now += 200;
    CHECK(strcmp(elm_session_poll(&session, now), "0110\r") == 0);
    elm_session_feed(&session, "411004D8\r>", 10, now);
    CHECK(session.sample.maf_valid && session.sample.maf_centi_gps == 1240);
    now += 200;
    CHECK(elm_session_poll(&session, now) != NULL);
    elm_session_feed(&session, "NO DATA\r>", 9, now);
    CHECK(!session.sample.coolant_valid && session.sample.link == GAUGE_LIVE);
    now += 3200;
    CHECK(elm_session_poll(&session, now) != NULL);
    CHECK(!session.sample.maf_valid);
    now += 10000;
    CHECK(elm_session_poll(&session, now) == NULL && session.failed);
    elm_session_start(&session, now, true);
    now += 200;
    CHECK(strcmp(elm_session_poll(&session, now), "ATZ\r") == 0);
    char oversized[600];
    memset(oversized, 'X', sizeof(oversized));
    elm_session_feed(&session, oversized, sizeof(oversized), now);
    CHECK(session.failed && !session.sample.coolant_valid);
    return 0;
}
