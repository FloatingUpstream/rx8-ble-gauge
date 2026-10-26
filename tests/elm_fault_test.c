#include <stdio.h>
#include <string.h>

#include "elm_session.h"

#define CHECK(condition) \
    do { \
        if (!(condition)) { \
            fprintf(stderr, "Failed line %d: %s\n", __LINE__, #condition); \
            return 1; \
        } \
    } while (0)

static bool initialize(elm_session_t* session, uint32_t* now, const char* map)
{
    elm_session_start(session, *now, true);
    for (unsigned i = 0; i < 7; ++i) {
        *now += 200;
        const char* command = elm_session_poll(session, *now);
        if (command == NULL) {
            return false;
        }
        const char* reply = i == 0 || i == 6 ? "ELM327 v2.2\r>" : "OK\r>";
        elm_session_feed(session, reply, strlen(reply), *now);
    }
    *now += 200;
    const char* command = elm_session_poll(session, *now);
    if (command == NULL || strcmp(command, "0100\r") != 0) {
        return false;
    }
    elm_session_feed(session, map, strlen(map), *now);
    return !session->failed;
}

int main(void)
{
    elm_session_t session;
    uint32_t now = 0;
    CHECK(initialize(&session, &now, "410008000000\r>"));
    CHECK(session.sample.maf_support == GAUGE_PID_UNSUPPORTED);
    for (unsigned i = 0; i < 100; ++i) {
        now += 200;
        CHECK(strcmp(elm_session_poll(&session, now), "0105\r") == 0);
        elm_session_feed(&session, "41057F\r>", 8, now);
        CHECK(!session.sample.maf_valid);
    }
    CHECK(initialize(&session, &now, "410000010000\r>"));
    for (unsigned i = 0; i < 20; ++i) {
        now += 200;
        CHECK(strcmp(elm_session_poll(&session, now), "0110\r") == 0);
        elm_session_feed(&session, "411004D8\r>", 10, now);
        CHECK(session.sample.link == GAUGE_LIVE && !session.sample.coolant_valid);
    }
    CHECK(initialize(&session, &now, "410000000000\r>"));
    now += 1000;
    CHECK(elm_session_poll(&session, now) == NULL);
    CHECK(session.sample.maf_support == GAUGE_PID_UNSUPPORTED);
    now += 30000;
    CHECK(strcmp(elm_session_poll(&session, now), "0100\r") == 0);
    elm_session_feed(&session, "410008010000\r>", 14, now);
    now += 200;
    CHECK(strcmp(elm_session_poll(&session, now), "0105\r") == 0);

    CHECK(initialize(&session, &now, "410000000000\r>"));
    now += 30000;
    CHECK(strcmp(elm_session_poll(&session, now), "0100\r") == 0);
    elm_session_feed(&session, "NO DATA\r>", 9, now);
    CHECK(!session.capabilities_known);
    CHECK(session.sample.coolant_support == GAUGE_PID_UNKNOWN);
    CHECK(session.sample.maf_support == GAUGE_PID_UNKNOWN);
    now += 200;
    CHECK(strcmp(elm_session_poll(&session, now), "0105\r") == 0);
    now += 2500;
    elm_session_feed(&session, "NO DATA\r>", 9, now);
    now += 200;
    CHECK(strcmp(elm_session_poll(&session, now), "0110\r") == 0);
    now += 2500;
    elm_session_feed(&session, "NO DATA\r>", 9, now);
    now += 200;
    CHECK(strcmp(elm_session_poll(&session, now), "0100\r") == 0);

    CHECK(initialize(&session, &now, "410000000000\r41 00 08 01 ZZ ZZ\r>"));
    CHECK(!session.capabilities_known);
    CHECK(session.sample.maf_support == GAUGE_PID_UNKNOWN);

    CHECK(initialize(&session, &now, "NO DATA\r>"));
    CHECK(!session.capabilities_known);
    CHECK(session.sample.coolant_support == GAUGE_PID_UNKNOWN);
    now += 200;
    CHECK(strcmp(elm_session_poll(&session, now), "0105\r") == 0);
    elm_session_feed(&session, "NO DATA\r>", 9, now);
    CHECK(session.sample.coolant_support == GAUGE_PID_UNKNOWN);
    now += 2000;
    CHECK(strcmp(elm_session_poll(&session, now), "0110\r") == 0);
    elm_session_feed(&session, "NO DATA\r>", 9, now);
    now += 200;
    CHECK(strcmp(elm_session_poll(&session, now), "0100\r") == 0);

    CHECK(initialize(&session, &now, "410008010000\r>"));
    now += 200;
    CHECK(elm_session_poll(&session, now) != NULL);
    elm_session_feed(&session, "41057F\r>", 8, now + 10000);
    CHECK(session.failed && !session.sample.coolant_valid); /* Late response, before poll. */
    CHECK(initialize(&session, &now, "410008010000\r>"));
    now += 200;
    CHECK(elm_session_poll(&session, now) != NULL);
    const char binary[] = {'4', '1', '0', '5', '7', 'F', '\0', '>'};
    elm_session_feed(&session, binary, sizeof(binary), now);
    CHECK(session.failed && !session.sample.coolant_valid);
    CHECK(initialize(&session, &now, "410008010000\r>"));
    now += 200;
    CHECK(elm_session_poll(&session, now) != NULL);
    elm_session_feed(&session, "411004D8\r>", 10, now); /* Wrong PID, not coolant. */
    CHECK(!session.failed && !session.sample.coolant_valid);
    CHECK(session.sample.coolant_support == GAUGE_PID_SUPPORTED);

    elm_session_start(&session, now, true);
    now += 200;
    CHECK(elm_session_poll(&session, now) != NULL);
    elm_session_feed(&session, "NOT ELM327\r>", 12, now);
    CHECK(session.failed);
    elm_session_start(&session, now, true);
    now += 200;
    CHECK(elm_session_poll(&session, now) != NULL);
    elm_session_feed(&session, "STN1170 v5.0\r>", 14, now);
    CHECK(!session.failed);
    now += 200;
    CHECK(elm_session_poll(&session, now) != NULL);
    elm_session_feed(&session, "NOT OK\r>", 8, now);
    CHECK(session.failed);

    now = UINT32_MAX - 1000;
    CHECK(initialize(&session, &now, "410008010000\r>")); /* Clock wraps during init. */
    now += 200;
    CHECK(strcmp(elm_session_poll(&session, now), "0105\r") == 0);
    elm_session_feed(&session, "41057F\r>", 8, now);
    now += 3001;
    CHECK(elm_session_poll(&session, now) != NULL);
    CHECK(!session.sample.coolant_valid);
    return 0;
}
