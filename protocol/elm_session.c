#include "elm_session.h"

#include <ctype.h>
#include <string.h>

#include "elm_decode.h"

enum
{
    DISCOVERY_INDEX = 7,
    COOLANT_INDEX = 8,
    MAF_INDEX = 9
};

static const char* const commands[] = {
    "ATZ\r",
    "ATE0\r",
    "ATL0\r",
    "ATS0\r",
    "ATH0\r",
    "ATSP0\r",
    "ATI\r",
    "0100\r",
    "0105\r",
    "0110\r",
};

bool elm_session_initialized(const elm_session_t* session)
{
    /* ELM verification doesn't require an awake ECU or a valid bitmap. */
    return !session->failed && session->command_index >= DISCOVERY_INDEX;
}

void elm_session_disconnect(elm_session_t* session)
{
    session->failed = true;
    session->waiting = false;
    session->sample.link = GAUGE_DISCONNECTED;
    session->sample.coolant_valid = false;
    session->sample.maf_valid = false;
}

void elm_session_start(elm_session_t* session, uint32_t now, bool simulated)
{
    *session = (elm_session_t) {.sample = {.link = GAUGE_CONNECTING, .simulated = simulated},
                                .next_at = now + 150,
                                .discovery_at = now};
}

static void refresh(elm_session_t* session, uint32_t now)
{
    if (session->sample.coolant_valid && now - session->coolant_at > 3000) {
        session->sample.coolant_valid = false;
    }
    if (session->sample.maf_valid && now - session->maf_at > 3000) {
        session->sample.maf_valid = false;
    }
    if (elm_session_initialized(session)) {
        session->sample.link =
            session->sample.coolant_valid || session->sample.maf_valid ? GAUGE_LIVE : GAUGE_STALE;
    }
}

const char* elm_session_poll(elm_session_t* session, uint32_t now)
{
    refresh(session, now);
    if (session->failed) {
        return NULL;
    }
    if (session->waiting) {
        if (now - session->sent_at >= 10000) {
            elm_session_disconnect(session);
        }
        return NULL;
    }
    if ((int32_t)(now - session->next_at) < 0) {
        return NULL;
    }
    if (elm_session_initialized(session)) {
        bool none_supported = session->sample.coolant_support == GAUGE_PID_UNSUPPORTED
            && session->sample.maf_support == GAUGE_PID_UNSUPPORTED;
        /* Retry discovery between complete PID cycles, not ahead of a slow MAF
         * probe. Otherwise slow coolant replies can starve unknown MAF forever. */
        if ((session->command_index == DISCOVERY_INDEX || session->command_index == COOLANT_INDEX)
            && (!session->capabilities_known || none_supported)
            && (int32_t)(now - session->discovery_at) >= 0)
        {
            session->command_index = DISCOVERY_INDEX;
        } else {
            if (none_supported) {
                return NULL;
            }
            if (session->command_index == COOLANT_INDEX
                && session->sample.coolant_support == GAUGE_PID_UNSUPPORTED)
            {
                session->command_index = MAF_INDEX;
            }
            if (session->command_index == MAF_INDEX
                && session->sample.maf_support == GAUGE_PID_UNSUPPORTED)
            {
                session->command_index = COOLANT_INDEX;
            }
        }
    }
    session->waiting = true;
    session->sent_at = now;
    session->length = 0;
    return commands[session->command_index];
}

static bool prefix(const char* text, size_t length, const char* expected)
{
    size_t count = strlen(expected);
    if (length < count) {
        return false;
    }
    for (size_t i = 0; i < count; ++i) {
        if (toupper((unsigned char)text[i]) != expected[i]) {
            return false;
        }
    }
    return true;
}

static bool init_reply(const char* response, bool identity)
{
    const char* line = response;
    for (const char* cursor = response;; ++cursor) {
        if (*cursor == '\r' || *cursor == '\n' || *cursor == '>' || *cursor == '\0') {
            size_t length = (size_t)(cursor - line);
            while (length > 0 && isspace((unsigned char)*line)) {
                ++line;
                --length;
            }
            while (length > 0 && isspace((unsigned char)line[length - 1])) {
                --length;
            }
            if (!identity && length == 2 && prefix(line, length, "OK")) {
                return true;
            }
            if (identity && prefix(line, length, "ELM327")
                && (length == 6 || isspace((unsigned char)line[6])))
            {
                return true;
            }
            if (identity && prefix(line, length, "STN")) {
                size_t end = 3;
                while (end < length && isdigit((unsigned char)line[end])) {
                    ++end;
                }
                if (end >= 7 && (end == length || isspace((unsigned char)line[end]))) {
                    return true;
                }
            }
            if (*cursor == '\0') {
                break;
            }
            line = cursor + 1;
        }
    }
    return false;
}

static void complete(elm_session_t* session, uint32_t now)
{
    session->response[session->length] = '\0';
    if (session->command_index < DISCOVERY_INDEX) {
        if (!init_reply(session->response,
                        session->command_index == 0 || session->command_index == 6))
        {
            elm_session_disconnect(session);
            return;
        }
        ++session->command_index;
    } else if (session->command_index == DISCOVERY_INDEX) {
        uint32_t bitmap;
        if (elm_decode_bitmap(session->response, 0, &bitmap)) {
            session->capabilities_known = true;
            session->sample.coolant_support =
                elm_bitmap_supports(bitmap, 0x05) ? GAUGE_PID_SUPPORTED : GAUGE_PID_UNSUPPORTED;
            session->sample.maf_support =
                elm_bitmap_supports(bitmap, 0x10) ? GAUGE_PID_SUPPORTED : GAUGE_PID_UNSUPPORTED;
            if (session->sample.coolant_support == GAUGE_PID_UNSUPPORTED) {
                session->sample.coolant_valid = false;
            }
            if (session->sample.maf_support == GAUGE_PID_UNSUPPORTED) {
                session->sample.maf_valid = false;
            }
        } else {
            session->capabilities_known = false;
            if (session->sample.coolant_support == GAUGE_PID_UNSUPPORTED) {
                session->sample.coolant_support = GAUGE_PID_UNKNOWN;
            }
            if (session->sample.maf_support == GAUGE_PID_UNSUPPORTED) {
                session->sample.maf_support = GAUGE_PID_UNKNOWN;
            }
        }
        /* No valid map means unknown, not unsupported. Probe PIDs while retrying.
         * A confirmed empty map is rechecked slowly without hammering absent PIDs. */
        session->discovery_at = now + (session->capabilities_known ? 30000 : 2000);
        session->command_index = COOLANT_INDEX;
    } else {
        bool coolant = session->command_index == COOLANT_INDEX;
        int decoded;
        bool valid = elm_decode_pid(session->response, coolant ? 0x05 : 0x10, &decoded);
        if (coolant) {
            session->sample.coolant_valid = valid;
            if (valid) {
                session->sample.coolant_support = GAUGE_PID_SUPPORTED;
                session->sample.coolant_c = decoded;
                session->coolant_at = now;
            }
        } else {
            session->sample.maf_valid = valid;
            if (valid) {
                session->sample.maf_support = GAUGE_PID_SUPPORTED;
                session->sample.maf_centi_gps = decoded;
                session->maf_at = now;
            }
        }
        session->command_index = coolant ? MAF_INDEX : COOLANT_INDEX;
    }
    session->waiting = false;
    session->length = 0;
    session->next_at = now + (session->command_index >= DISCOVERY_INDEX ? 100 : 20);
    refresh(session, now);
}

void elm_session_feed(elm_session_t* session, const void* data, size_t length, uint32_t now)
{
    if (length > 0 && data == NULL) {
        elm_session_disconnect(session);
        return;
    }
    if (session->waiting && now - session->sent_at >= 10000) {
        elm_session_disconnect(session);
        return;
    }
    const unsigned char* bytes = data;
    for (size_t i = 0; i < length; ++i) {
        if (!session->waiting || session->failed) {
            return;
        }
        if (bytes[i] == '>') {
            complete(session, now);
        } else if ((bytes[i] < 32 && bytes[i] != '\r' && bytes[i] != '\n' && bytes[i] != '\t')
                   || bytes[i] > 126 || session->length + 1 >= sizeof(session->response))
        {
            elm_session_disconnect(session);
        } else {
            session->response[session->length++] = (char)bytes[i];
        }
    }
}
