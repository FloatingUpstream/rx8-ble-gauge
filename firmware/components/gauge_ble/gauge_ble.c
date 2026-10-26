#include "gauge_ble.h"

#include <string.h>

#include "adapter_ui.h"
#include "bsp/esp-bsp.h"
#include "elm_session.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "gauge_ui.h"
#include "host/ble_hs.h"
#include "host/util/util.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "nvs.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"

/* SDK utility header depends on declarations from ble_hs.h above. */
#include "esp_central.h"

/* Uses pinned Espressif CC0 nimble_central_utils for discovery.
 * User chooses the adapter; only verified, stable identities are persisted. */
static const char* tag = "gauge_ble";
static QueueHandle_t events;
static struct ble_npl_callout scan_timer;
static uint8_t address_type;
static bool connecting;
static bool canceling;
static bool link_active;
static bool want_target;
static bool target_verified;
static gauge_adapter_t target;
static gauge_adapter_t initial_peer;
static bool initial_saved;
static uint16_t active_connection = BLE_HS_CONN_HANDLE_NONE;
static QueueHandle_t controls;
static struct ble_npl_event control_event;

typedef enum
{
    CONTROL_PICK,
    CONTROL_SCAN,
    CONTROL_FORGET,
    CONTROL_VERIFIED,
    CONTROL_REJECT,
    CONTROL_RESUME
} control_kind_t;

typedef struct
{
    control_kind_t kind;
    gauge_adapter_t adapter;
} control_t;

typedef struct
{
    uint16_t connection;
    uint16_t rx;
    uint16_t tx;
    bool acknowledged;
    bool verified;
    gauge_adapter_t adapter;
} endpoint_t;

typedef enum
{
    EVENT_READY,
    EVENT_DOWN,
    EVENT_DATA,
    EVENT_CANDIDATE,
    EVENT_PICK,
    EVENT_SCAN,
    EVENT_FORGET,
    EVENT_UNSUPPORTED,
} event_kind_t;

typedef struct
{
    event_kind_t kind;
    endpoint_t endpoint;
    size_t length;
    char data[64];
} transport_event_t;

static endpoint_t discovered;
static int gap_event(struct ble_gap_event* event, void* arg);
static void scan(struct ble_npl_event* event);

static bool load_peer(gauge_adapter_t* peer)
{
    nvs_handle_t storage;
    if (nvs_open("gauge_ble", NVS_READONLY, &storage) != ESP_OK) {
        return false;
    }
    size_t size = sizeof(*peer);
    esp_err_t result = nvs_get_blob(storage, "peer_v1", peer, &size);
    nvs_close(storage);
    peer->name[sizeof(peer->name) - 1] = '\0';
    return result == ESP_OK && size == sizeof(*peer) && gauge_adapter_stable(peer);
}

static esp_err_t store_peer(const gauge_adapter_t* peer)
{
    nvs_handle_t storage;
    esp_err_t result = nvs_open("gauge_ble", NVS_READWRITE, &storage);
    if (result != ESP_OK) {
        return result;
    }
    result = peer != NULL ? nvs_set_blob(storage, "peer_v1", peer, sizeof(*peer))
                          : nvs_erase_key(storage, "peer_v1");
    if (result == ESP_ERR_NVS_NOT_FOUND) {
        result = ESP_OK;
    }
    if (result == ESP_OK) {
        result = nvs_commit(storage);
    }
    nvs_close(storage);
    return result;
}

static void retry_scan(void)
{
    ble_npl_callout_reset(&scan_timer, ble_npl_time_ms_to_ticks32(1000));
}

static void post(const transport_event_t* event)
{
    if (xQueueSend(events, event, 0) != pdTRUE) {
        ESP_LOGE(tag, "Queue overflow: terminating link");
        if (event->kind == EVENT_DATA || event->kind == EVENT_READY) {
            ble_gap_terminate(event->endpoint.connection, BLE_ERR_REM_USER_CONN_TERM);
        }
    }
}

static void send_control(control_kind_t kind, const gauge_adapter_t* adapter)
{
    control_t command = {.kind = kind};
    if (adapter != NULL) {
        command.adapter = *adapter;
    }
    if (xQueueSend(controls, &command, 0) == pdTRUE) {
        ble_npl_eventq_put(nimble_port_get_dflt_eventq(), &control_event);
    } else {
        ESP_LOGW(tag, "Control queue full");
    }
}

static void select_adapter(const gauge_adapter_t* adapter)
{
    send_control(CONTROL_PICK, adapter);
}

static void request_scan(void)
{
    send_control(CONTROL_SCAN, NULL);
}

static void forget_adapter(void)
{
    send_control(CONTROL_FORGET, NULL);
}

static void resume_adapter(void)
{
    send_control(CONTROL_RESUME, NULL);
}

static void handle_controls(struct ble_npl_event* event)
{
    (void)event;
    control_t command;
    while (xQueueReceive(controls, &command, 0) == pdTRUE) {
        if (command.kind == CONTROL_RESUME) {
            if (want_target || !load_peer(&command.adapter)) {
                continue;
            }
            command.kind = CONTROL_PICK;
        }
        if (command.kind == CONTROL_VERIFIED) {
            if (want_target && gauge_adapter_same(&command.adapter, &target)) {
                target_verified = true;
            }
            continue;
        }
        if (command.kind == CONTROL_REJECT) {
            if (!want_target || !gauge_adapter_same(&command.adapter, &target)) {
                continue;
            }
            want_target = false;
            const transport_event_t rejected = {.kind = EVENT_UNSUPPORTED};
            post(&rejected);
        } else {
            want_target = command.kind == CONTROL_PICK;
            target_verified = false;
            if (want_target) {
                target = command.adapter;
            }
            transport_event_t changed = {
                .kind = command.kind == CONTROL_PICK ? EVENT_PICK
                    : command.kind == CONTROL_FORGET ? EVENT_FORGET
                                                     : EVENT_SCAN,
                .endpoint = {.adapter = command.adapter},
            };
            post(&changed);
        }
        ble_gap_disc_cancel();
        if (connecting) {
            canceling = true;
            ble_gap_conn_cancel();
        }
        if (active_connection != BLE_HS_CONN_HANDLE_NONE) {
            ble_gap_terminate(active_connection, BLE_ERR_REM_USER_CONN_TERM);
        } else {
            retry_scan();
        }
    }
}

static void scan(struct ble_npl_event* event)
{
    (void)event;
    if (connecting || link_active) {
        return;
    }
    /* Deduplicate in the worker, not controller cache: restarted advertisers
     * must remain discoverable at the same address. */
    struct ble_gap_disc_params parameters = {.passive = 0, .filter_duplicates = 0};
    int result = ble_gap_disc(address_type, 5000, &parameters, gap_event, NULL);
    if (result != 0) {
        ESP_LOGW(tag, "Scan failed: %d", result);
        retry_scan();
    }
}

static int subscribed(uint16_t connection,
                      const struct ble_gatt_error* error,
                      struct ble_gatt_attr* attribute,
                      void* arg)
{
    (void)attribute;
    (void)arg;
    if (error->status != 0) {
        ESP_LOGW(tag, "Subscribe failed: %d", error->status);
        ble_gap_terminate(connection, BLE_ERR_REM_USER_CONN_TERM);
        return 0;
    }
    if (!want_target || connection != active_connection
        || !gauge_adapter_same(&discovered.adapter, &target))
    {
        ble_gap_terminate(connection, BLE_ERR_REM_USER_CONN_TERM);
        return 0;
    }
    ESP_LOGI(tag,
             "Subscribed: conn=%u RX=%u TX=%u acknowledged=%d",
             connection,
             discovered.rx,
             discovered.tx,
             discovered.acknowledged);
    const transport_event_t event = {.kind = EVENT_READY, .endpoint = discovered};
    post(&event);
    return 0;
}

static void discovery_complete(const struct peer* peer, int status, void* arg)
{
    (void)arg;
    if (status != 0 || !want_target || peer->conn_handle != active_connection
        || !gauge_adapter_same(&discovered.adapter, &target))
    {
        goto failure;
    }
    const ble_uuid_t* service = BLE_UUID16_DECLARE(CONFIG_GAUGE_BLE_SERVICE);
    const struct peer_chr* rx =
        peer_chr_find_uuid(peer, service, BLE_UUID16_DECLARE(CONFIG_GAUGE_BLE_RX));
    const struct peer_chr* tx =
        peer_chr_find_uuid(peer, service, BLE_UUID16_DECLARE(CONFIG_GAUGE_BLE_TX));
    if (tx == NULL) {
        tx = rx; /* Some adapters use one notify/write characteristic. */
    }
    const struct peer_dsc* cccd =
        peer_dsc_find_uuid(peer,
                           service,
                           BLE_UUID16_DECLARE(CONFIG_GAUGE_BLE_RX),
                           BLE_UUID16_DECLARE(BLE_GATT_DSC_CLT_CFG_UUID16));
    if (rx == NULL || tx == NULL || cccd == NULL || !(rx->chr.properties & BLE_GATT_CHR_PROP_NOTIFY)
        || !(tx->chr.properties & (BLE_GATT_CHR_PROP_WRITE | BLE_GATT_CHR_PROP_WRITE_NO_RSP)))
    {
        goto failure;
    }
    discovered = (endpoint_t) {.connection = peer->conn_handle,
                               .rx = rx->chr.val_handle,
                               .tx = tx->chr.val_handle,
                               .acknowledged = (tx->chr.properties & BLE_GATT_CHR_PROP_WRITE) != 0,
                               .verified = target_verified,
                               .adapter = target};
    const uint8_t enable[] = {1, 0};
    if (ble_gattc_write_flat(
            peer->conn_handle, cccd->dsc.handle, enable, sizeof(enable), subscribed, NULL)
        != 0)
    {
        goto failure;
    }
    return;
failure:
    ESP_LOGW(tag, "Discovery/profile mismatch: %d", status);
    if (want_target && !target_verified) {
        send_control(CONTROL_REJECT, &discovered.adapter);
    }
    ble_gap_terminate(peer->conn_handle, BLE_ERR_REM_USER_CONN_TERM);
}

static int gap_event(struct ble_gap_event* event, void* arg)
{
    (void)arg;
    switch (event->type) {
        case BLE_GAP_EVENT_DISC: {
            struct ble_hs_adv_fields fields;
            if (connecting || link_active
                || ble_hs_adv_parse_fields(&fields, event->disc.data, event->disc.length_data) != 0)
            {
                break;
            }
            gauge_adapter_t candidate = {.address_type = event->disc.addr.type};
            memcpy(candidate.address, event->disc.addr.val, sizeof(candidate.address));
            if (fields.name != NULL && fields.name_len > 0) {
                size_t length = fields.name_len;
                if (length >= sizeof(candidate.name)) {
                    length = sizeof(candidate.name) - 1;
                }
                memcpy(candidate.name, fields.name, length);
                const transport_event_t found = {.kind = EVENT_CANDIDATE,
                                                 .endpoint = {.adapter = candidate}};
                post(&found);
            }
            if (!want_target || !gauge_adapter_same(&candidate, &target)) {
                break;
            }
            ESP_LOGI(tag, "Selected adapter found: %.31s", target.name);
            connecting = true;
            discovered = (endpoint_t) {.connection = BLE_HS_CONN_HANDLE_NONE, .adapter = target};
            ble_gap_disc_cancel();
            int result =
                ble_gap_connect(address_type, &event->disc.addr, 10000, NULL, gap_event, NULL);
            if (result != 0) {
                connecting = false;
                retry_scan();
            }
            break;
        }
        case BLE_GAP_EVENT_DISC_COMPLETE:
            if (!connecting && !link_active) {
                retry_scan();
            }
            break;
        case BLE_GAP_EVENT_CONNECT: {
            bool was_canceling = canceling;
            canceling = false;
            connecting = false;
            link_active = event->connect.status == 0;
            if (event->connect.status != 0) {
                if (want_target && !target_verified && !was_canceling) {
                    send_control(CONTROL_REJECT, &target);
                }
                retry_scan();
            } else {
                active_connection = event->connect.conn_handle;
                discovered.connection = active_connection;
                if (!want_target || !gauge_adapter_same(&discovered.adapter, &target)
                    || peer_add(event->connect.conn_handle) != 0
                    || peer_disc_all(event->connect.conn_handle, discovery_complete, NULL) != 0)
                {
                    ble_gap_terminate(event->connect.conn_handle, BLE_ERR_REM_USER_CONN_TERM);
                }
            }
            break;
        }
        case BLE_GAP_EVENT_DISCONNECT: {
            uint16_t connection = event->disconnect.conn.conn_handle;
            link_active = false;
            active_connection = BLE_HS_CONN_HANDLE_NONE;
            ESP_LOGI(tag, "Disconnected: reason=%d", event->disconnect.reason);
            peer_delete(connection);
            const transport_event_t down = {.kind = EVENT_DOWN,
                                            .endpoint = {.connection = connection}};
            post(&down);
            retry_scan();
            break;
        }
        case BLE_GAP_EVENT_NOTIFY_RX: {
            if (event->notify_rx.attr_handle != discovered.rx
                || event->notify_rx.conn_handle != discovered.connection)
            {
                break;
            }
            size_t length = os_mbuf_len(event->notify_rx.om);
            for (size_t offset = 0; offset < length;) {
                transport_event_t data = {.kind = EVENT_DATA, .endpoint = discovered};
                data.length = length - offset;
                if (data.length > sizeof(data.data)) {
                    data.length = sizeof(data.data);
                }
                if (os_mbuf_copydata(event->notify_rx.om, (int)offset, (int)data.length, data.data)
                    != 0)
                {
                    ble_gap_terminate(discovered.connection, BLE_ERR_REM_USER_CONN_TERM);
                    break;
                }
                post(&data);
                offset += data.length;
            }
            break;
        }
        default:
            break;
    }
    return 0;
}

static int written(uint16_t connection,
                   const struct ble_gatt_error* error,
                   struct ble_gatt_attr* attribute,
                   void* arg)
{
    (void)attribute;
    (void)arg;
    if (error->status != 0) {
        ESP_LOGW(tag, "Write failed: %d", error->status);
        ble_gap_terminate(connection, BLE_ERR_REM_USER_CONN_TERM);
    }
    return 0;
}

static void worker(void* arg)
{
    (void)arg;
    elm_session_t session;
    elm_session_start(&session, 0, true);
    endpoint_t endpoint = {.connection = BLE_HS_CONN_HANDLE_NONE};
    gauge_adapter_t candidates[GAUGE_ADAPTER_MAX] = {0};
    size_t candidate_count = 0;
    gauge_adapter_t saved_peer = initial_peer;
    bool have_saved = initial_saved;
    gauge_adapter_t selected = initial_peer;
    bool have_selected = initial_saved;
    bool selected_saved = initial_saved;
    bool selection_dirty = true;
    bool list_dirty = true;
    bool show_picker = !initial_saved;
    bool connection_verified = false;
    const char* picker_status = "Scanning...";
    uint32_t next_ui = 0;
    uint32_t next_log = 0;
    while (true) {
        transport_event_t event;
        uint32_t now = (uint32_t)(esp_timer_get_time() / 1000);
        while (xQueueReceive(events, &event, 0) == pdTRUE) {
            if (event.kind == EVENT_CANDIDATE) {
                size_t index = 0;
                while (index < candidate_count
                       && !gauge_adapter_same(&candidates[index], &event.endpoint.adapter))
                {
                    ++index;
                }
                if (index < GAUGE_ADAPTER_MAX
                    && (index == candidate_count
                        || strcmp(candidates[index].name, event.endpoint.adapter.name) != 0))
                {
                    candidates[index] = event.endpoint.adapter;
                    if (index == candidate_count) {
                        ++candidate_count;
                    }
                    list_dirty = true;
                    picker_status = "Tap a device to verify";
                }
            } else if (event.kind == EVENT_PICK || event.kind == EVENT_SCAN
                       || event.kind == EVENT_FORGET || event.kind == EVENT_UNSUPPORTED)
            {
                endpoint.connection = BLE_HS_CONN_HANDLE_NONE;
                elm_session_disconnect(&session);
                if (event.kind == EVENT_PICK) {
                    session.sample.link = GAUGE_CONNECTING;
                    selected = event.endpoint.adapter;
                    have_selected = true;
                    selected_saved = have_saved && gauge_adapter_same(&selected, &saved_peer);
                    selection_dirty = true;
                    show_picker = false;
                } else {
                    show_picker = true;
                    picker_status =
                        event.kind == EVENT_UNSUPPORTED ? "ELM verification failed" : "Scanning...";
                    if (event.kind != EVENT_UNSUPPORTED) {
                        candidate_count = 0;
                        list_dirty = true;
                    }
                    if (event.kind == EVENT_FORGET) {
                        esp_err_t result = store_peer(NULL);
                        if (result == ESP_OK) {
                            have_saved = false;
                            have_selected = false;
                            selected_saved = false;
                            selection_dirty = true;
                            ESP_LOGI(tag, "Saved adapter forgotten");
                        } else {
                            picker_status = "Forget failed";
                            ESP_LOGE(tag, "NVS erase failed: %s", esp_err_to_name(result));
                        }
                    }
                }
            } else if (event.kind == EVENT_READY) {
                endpoint = event.endpoint;
                connection_verified = false;
                elm_session_start(&session, now, true);
            } else if (event.endpoint.connection == endpoint.connection) {
                if (event.kind == EVENT_DOWN) {
                    endpoint.connection = BLE_HS_CONN_HANDLE_NONE;
                    elm_session_disconnect(&session);
                } else if (event.kind == EVENT_DATA) {
                    elm_session_feed(&session, event.data, event.length, now);
                }
            }
        }
        if (endpoint.connection != BLE_HS_CONN_HANDLE_NONE) {
            const char* command = elm_session_poll(&session, now);
            if (command != NULL) {
                size_t length = strlen(command);
                int result = endpoint.acknowledged
                    ? ble_gattc_write_flat(endpoint.connection,
                                           endpoint.tx,
                                           command,
                                           (uint16_t)length,
                                           written,
                                           NULL)
                    : ble_gattc_write_no_rsp_flat(
                          endpoint.connection, endpoint.tx, command, (uint16_t)length);
                if (result != 0) {
                    elm_session_disconnect(&session);
                }
            }
            if (elm_session_initialized(&session) && !connection_verified) {
                connection_verified = true;
                selected = endpoint.adapter;
                have_selected = true;
                selected_saved = have_saved && gauge_adapter_same(&selected, &saved_peer);
                if (gauge_adapter_stable(&selected) && !selected_saved) {
                    esp_err_t result = store_peer(&selected);
                    if (result == ESP_OK) {
                        saved_peer = selected;
                        have_saved = true;
                        selected_saved = true;
                        ESP_LOGI(tag, "Verified adapter saved: %.31s", selected.name);
                    } else {
                        ESP_LOGE(tag, "NVS save failed: %s", esp_err_to_name(result));
                    }
                }
                if (!gauge_adapter_stable(&selected)) {
                    ESP_LOGW(tag, "Private address: session-only selection");
                }
                selection_dirty = true;
                send_control(CONTROL_VERIFIED, &selected);
            }
            if (session.failed) {
                if (!connection_verified && !endpoint.verified) {
                    send_control(CONTROL_REJECT, &endpoint.adapter);
                }
                ble_gap_terminate(endpoint.connection, BLE_ERR_REM_USER_CONN_TERM);
                endpoint.connection = BLE_HS_CONN_HANDLE_NONE;
            }
        }
        if ((int32_t)(now - next_ui) >= 0 && bsp_display_lock(200) == ESP_OK) {
            gauge_ui_update(&session.sample);
            if (list_dirty) {
                adapter_ui_set_candidates(candidates, candidate_count);
                list_dirty = false;
            }
            if (selection_dirty) {
                adapter_ui_set_selected(have_selected ? &selected : NULL, selected_saved);
                selection_dirty = false;
            }
            adapter_ui_set_status(picker_status);
            if (show_picker) {
                adapter_ui_show_picker();
                show_picker = false;
            }
            bsp_display_unlock();
            next_ui = now + 100;
        }
        if ((int32_t)(now - next_log) >= 0) {
            ESP_LOGI(tag,
                     "ELM link=%d coolant=%d valid=%d MAF_centi=%d valid=%d support=%d/%d",
                     session.sample.link,
                     session.sample.coolant_c,
                     session.sample.coolant_valid,
                     session.sample.maf_centi_gps,
                     session.sample.maf_valid,
                     session.sample.coolant_support,
                     session.sample.maf_support);
            next_log = now + 5000;
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

static void synced(void)
{
    if (ble_hs_util_ensure_addr(0) != 0 || ble_hs_id_infer_auto(0, &address_type) != 0) {
        ESP_LOGE(tag, "BLE address initialization failed");
        return;
    }
    scan(NULL);
}

static void host(void* arg)
{
    (void)arg;
    nimble_port_run();
    nimble_port_freertos_deinit();
}

void gauge_ble_start(void)
{
    initial_saved = load_peer(&initial_peer);
    want_target = initial_saved;
    target_verified = initial_saved;
    if (initial_saved) {
        target = initial_peer;
        ESP_LOGI(tag, "Saved adapter loaded: %.31s", target.name);
    }
    events = xQueueCreate(64, sizeof(transport_event_t));
    controls = xQueueCreate(8, sizeof(control_t));
    ESP_ERROR_CHECK(events != NULL && controls != NULL ? ESP_OK : ESP_ERR_NO_MEM);
    ESP_ERROR_CHECK(nimble_port_init());
    ble_svc_gap_init();
    ble_svc_gatt_init();
    ESP_ERROR_CHECK(ble_svc_gap_device_name_set("RX-8 gauge") == 0 ? ESP_OK : ESP_FAIL);
    ESP_ERROR_CHECK(peer_init(1, 32, 32, 32) == 0 ? ESP_OK : ESP_FAIL);
    ble_npl_callout_init(&scan_timer, nimble_port_get_dflt_eventq(), scan, NULL);
    ble_npl_event_init(&control_event, handle_controls, NULL);
    ble_hs_cfg.sync_cb = synced;
    const adapter_ui_actions_t callbacks = {
        .select = select_adapter,
        .scan = request_scan,
        .forget = forget_adapter,
        .resume = resume_adapter,
    };
    ESP_ERROR_CHECK(bsp_display_lock(1000));
    adapter_ui_set_actions(&callbacks);
    bsp_display_unlock();
    ESP_ERROR_CHECK(
        xTaskCreate(worker, "elm_worker", 8192, NULL, 4, NULL) == pdPASS ? ESP_OK : ESP_ERR_NO_MEM);
    nimble_port_freertos_init(host);
}
