#include "elm_tcp.h"

#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <poll.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#include "elm_session.h"

static int connection = -1;
static uint16_t server_port;
static bool connecting;
static uint32_t deadline;
static uint32_t next_connection;
static elm_session_t session;

void elm_tcp_start(uint16_t port)
{
    server_port = port;
    next_connection = 0;
}

void elm_tcp_stop(void)
{
    if (connection >= 0) {
        close(connection);
    }
    connection = -1;
    connecting = false;
}

static void disconnect(uint32_t now, gauge_sample_t* sample)
{
    elm_tcp_stop();
    elm_session_disconnect(&session);
    *sample = session.sample;
    next_connection = now + 1000;
}

static void open_connection(uint32_t now, gauge_sample_t* sample)
{
    elm_session_start(&session, now, true);
    *sample = session.sample;
    connection = socket(AF_INET, SOCK_STREAM, 0);
    if (connection < 0) {
        disconnect(now, sample);
        return;
    }
    int flags = fcntl(connection, F_GETFL, 0);
    if (flags < 0 || fcntl(connection, F_SETFL, flags | O_NONBLOCK) < 0) {
        disconnect(now, sample);
        return;
    }
    struct sockaddr_in address = {.sin_family = AF_INET,
                                  .sin_port = htons(server_port),
                                  .sin_addr = {.s_addr = htonl(INADDR_LOOPBACK)}};
    int result = connect(connection, (struct sockaddr*)&address, sizeof(address));
    if (result < 0 && errno != EINPROGRESS) {
        disconnect(now, sample);
        return;
    }
    connecting = result < 0;
    deadline = now + 2000;
}

void elm_tcp_poll(uint32_t now, gauge_sample_t* sample)
{
    if (connection < 0) {
        if ((int32_t)(now - next_connection) >= 0) {
            open_connection(now, sample);
        }
        return;
    }
    if (connecting) {
        struct pollfd socket_poll = {.fd = connection, .events = POLLOUT};
        int ready = poll(&socket_poll, 1, 0);
        if (ready == 0 && now < deadline) {
            return;
        }
        int error = 0;
        socklen_t length = sizeof(error);
        if (ready <= 0 || getsockopt(connection, SOL_SOCKET, SO_ERROR, &error, &length) < 0
            || error != 0)
        {
            disconnect(now, sample);
            return;
        }
        connecting = false;
    }
    char data[128];
    ssize_t count = recv(connection, data, sizeof(data), MSG_DONTWAIT);
    if (count == 0 || (count < 0 && errno != EAGAIN && errno != EWOULDBLOCK)) {
        disconnect(now, sample);
        return;
    }
    if (count > 0) {
        elm_session_feed(&session, data, (size_t)count, now);
    }
    const char* command = elm_session_poll(&session, now);
    if (command != NULL) {
        size_t length = strlen(command);
        /* Tiny commands; fail closed on partial writes rather than duplicating. */
        if (send(connection, command, length, MSG_NOSIGNAL) != (ssize_t)length) {
            disconnect(now, sample);
            return;
        }
    }
    if (session.failed) {
        disconnect(now, sample);
        return;
    }
    *sample = session.sample;
}
