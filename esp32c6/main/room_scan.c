/*
 * One-shot room scan for the ESP32-C6.
 *
 * Prints Wi-Fi APs, BLE advertisers, 802.15.4 energy, passive beacons, and
 * the result of an active Zigbee scan (beacon requests only). Does not
 * associate, join a PAN, pair, or open permit-join. The only 802.15.4 frames
 * transmitted are beacon requests.
 */

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "sdkconfig.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"

#include "esp_err.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "esp_wifi_default.h"
#include "nvs_flash.h"
#include "esp_ieee802154.h"

#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "host/ble_hs.h"
#include "host/util/util.h"
#include "host/ble_store.h"
#include "host/ble_hs_adv.h"

#define WIFI_MAX_AP          24
#define BLE_MAX_DEV          48
#define PAN_MAX              24
#define I154_CH_MIN          11
#define I154_CH_MAX          26
#define I154_CH_COUNT        (I154_CH_MAX - I154_CH_MIN + 1)
#define ED_SYMBOLS           4096
#define PASSIVE_MS           300
#define ACTIVE_LISTEN_MS     250
#define BLE_SCAN_10MS_UNITS  1000
#define START_WAIT_S         8

#define MODE_PASSIVE         1
#define MODE_ACTIVE          2

extern void ble_store_config_init(void);

typedef struct {
    uint8_t channel;
    int8_t rssi;
    uint8_t lqi;
    uint8_t psdu_len;
    uint8_t psdu[127];
} rx_item_t;

typedef struct {
    uint8_t addr[6];
    uint8_t type;
    int8_t rssi;
    bool have_rssi;
    char name[32];
    bool used;
} ble_dev_t;

typedef struct {
    uint16_t pan;
    uint16_t channels;
    int8_t best_rssi;
    uint8_t best_channel;
    bool coord;
    bool zigbee;
    bool from_beacon;
    bool from_data;
    bool has_extpan;
    uint8_t extpan[8];
    bool used;
} pan_rec_t;

static QueueHandle_t s_rx_q;
static SemaphoreHandle_t s_ed_sem;
static SemaphoreHandle_t s_tx_sem;
static SemaphoreHandle_t s_ble_done;
static volatile int s_tx_result = -1;
static volatile uint32_t s_rx_drops;
static int s_mode;
static uint8_t s_listen_channel = I154_CH_MIN;
static uint8_t s_seq;
static uint8_t s_beacon_req[16];

static int8_t s_ed[I154_CH_COUNT];
static bool s_ed_ok[I154_CH_COUNT];
static uint16_t s_frames[I154_CH_COUNT];
static uint16_t s_beacons[I154_CH_COUNT];
static uint16_t s_active_sent;
static uint16_t s_active_fail;
static uint16_t s_ack_frames;
static uint16_t s_other_printed;
static ble_dev_t s_ble[BLE_MAX_DEV];
static int s_ble_count;
static int s_ble_overflow;
static pan_rec_t s_pans[PAN_MAX];
static int s_pan_count;
static volatile bool s_ble_synced;
static int s_ble_start_rc = 1;

static void scan_log(const char *fmt, ...)
{
    va_list ap;
    fputs("SCAN ", stdout);
    va_start(ap, fmt);
    vprintf(fmt, ap);
    va_end(ap);
    fputc('\n', stdout);
    fflush(stdout);
}

static void copy_text(char *dst, size_t dst_len, const uint8_t *src, size_t src_len)
{
    size_t j = 0;
    if (dst_len == 0) {
        return;
    }
    for (size_t i = 0; i < src_len && j + 1 < dst_len; i++) {
        unsigned char c = src[i];
        if (c == 0) {
            break;
        }
        if (c < 32 || c > 126 || c == '"' || c == '\\') {
            c = '?';
        }
        dst[j++] = (char)c;
    }
    dst[j] = '\0';
}

static const char *auth_name(wifi_auth_mode_t mode)
{
    switch (mode) {
    case WIFI_AUTH_OPEN: return "OPEN";
    case WIFI_AUTH_WEP: return "WEP";
    case WIFI_AUTH_WPA_PSK: return "WPA_PSK";
    case WIFI_AUTH_WPA2_PSK: return "WPA2_PSK";
    case WIFI_AUTH_WPA_WPA2_PSK: return "WPA_WPA2_PSK";
    case WIFI_AUTH_ENTERPRISE: return "WPA2_ENTERPRISE";
    case WIFI_AUTH_WPA3_PSK: return "WPA3_PSK";
    case WIFI_AUTH_WPA2_WPA3_PSK: return "WPA2_WPA3_PSK";
    case WIFI_AUTH_WAPI_PSK: return "WAPI_PSK";
    case WIFI_AUTH_OWE: return "OWE";
    case WIFI_AUTH_WPA3_ENT_192: return "WPA3_ENT_192";
    case WIFI_AUTH_WPA3_EXT_PSK: return "WPA3_EXT_PSK";
    case WIFI_AUTH_WPA3_EXT_PSK_MIXED_MODE: return "WPA3_EXT_PSK_MIXED";
    case WIFI_AUTH_DPP: return "DPP";
    case WIFI_AUTH_WPA3_ENTERPRISE: return "WPA3_ENTERPRISE";
    case WIFI_AUTH_WPA2_WPA3_ENTERPRISE: return "WPA2_WPA3_ENTERPRISE";
    case WIFI_AUTH_WPA_ENTERPRISE: return "WPA_ENTERPRISE";
    default: return "UNKNOWN";
    }
}

static const char *addr_type_name(uint8_t type)
{
    switch (type) {
    case BLE_ADDR_PUBLIC: return "public";
    case BLE_ADDR_RANDOM: return "random";
    case BLE_ADDR_PUBLIC_ID: return "public_id";
    case BLE_ADDR_RANDOM_ID: return "random_id";
    default: return "other";
    }
}

static const char *frame_type_name(uint8_t type)
{
    switch (type) {
    case 0: return "beacon";
    case 1: return "data";
    case 2: return "ack";
    case 3: return "command";
    case 5: return "multipurpose";
    case 6: return "fragment";
    case 7: return "extended";
    default: return "reserved";
    }
}

static const char *tx_err_name(int err)
{
    switch (err) {
    case ESP_IEEE802154_TX_ERR_NONE: return "none";
    case ESP_IEEE802154_TX_ERR_CCA_BUSY: return "cca_busy";
    case ESP_IEEE802154_TX_ERR_ABORT: return "abort";
    case ESP_IEEE802154_TX_ERR_NO_ACK: return "no_ack";
    case ESP_IEEE802154_TX_ERR_INVALID_ACK: return "invalid_ack";
    case ESP_IEEE802154_TX_ERR_COEXIST: return "coexist";
    case ESP_IEEE802154_TX_ERR_SECURITY: return "security";
    default: return "other";
    }
}

static const char *mode_name(void)
{
    if (s_mode == MODE_PASSIVE) {
        return "passive";
    }
    if (s_mode == MODE_ACTIVE) {
        return "active";
    }
    return "other";
}

static void mask_to_str(char *dst, size_t n, uint16_t mask)
{
    size_t j = 0;
    if (n == 0) {
        return;
    }
    dst[0] = '\0';
    for (int ch = I154_CH_MIN; ch <= I154_CH_MAX; ch++) {
        if ((mask & (1u << (ch - I154_CH_MIN))) == 0) {
            continue;
        }
        int w = snprintf(dst + j, n - j, "%s%d", j ? "," : "", ch);
        if (w < 0 || (size_t)w >= n - j) {
            dst[n - 1] = '\0';
            return;
        }
        j += (size_t)w;
    }
    if (j == 0) {
        snprintf(dst, n, "none");
    }
}

static void eui64_str(char *dst, size_t n, const uint8_t *le)
{
    snprintf(dst, n, "%02x%02x%02x%02x%02x%02x%02x%02x",
             le[7], le[6], le[5], le[4], le[3], le[2], le[1], le[0]);
}

static void hex_bytes(char *dst, size_t n, const uint8_t *p, int len, int cap)
{
    size_t j = 0;
    int shown = len < cap ? len : cap;
    if (n == 0) {
        return;
    }
    dst[0] = '\0';
    for (int i = 0; i < shown; i++) {
        int w = snprintf(dst + j, n - j, "%02x", p[i]);
        if (w < 0 || (size_t)w >= n - j) {
            dst[n - 1] = '\0';
            return;
        }
        j += (size_t)w;
    }
    if (len > shown && j + 3 < n) {
        snprintf(dst + j, n - j, "...");
    }
}

static int channel_index(uint8_t channel)
{
    if (channel < I154_CH_MIN || channel > I154_CH_MAX) {
        return -1;
    }
    return (int)channel - I154_CH_MIN;
}

static void note_pan(uint16_t pan, uint8_t channel, int8_t rssi, bool beacon,
                     bool coord, bool zigbee, const uint8_t *extpan)
{
    pan_rec_t *rec = NULL;
    if (pan == 0xffff) {
        return;
    }
    for (int i = 0; i < s_pan_count; i++) {
        if (s_pans[i].used && s_pans[i].pan == pan) {
            rec = &s_pans[i];
            break;
        }
    }
    if (rec == NULL) {
        if (s_pan_count >= PAN_MAX) {
            scan_log("PAN_TABLE_FULL pan=0x%04x", pan);
            return;
        }
        rec = &s_pans[s_pan_count++];
        memset(rec, 0, sizeof(*rec));
        rec->used = true;
        rec->pan = pan;
        rec->best_rssi = rssi;
        rec->best_channel = channel;
    }
    int idx = channel_index(channel);
    if (idx >= 0) {
        rec->channels |= (uint16_t)(1u << idx);
    }
    if (rssi > rec->best_rssi) {
        rec->best_rssi = rssi;
        rec->best_channel = channel;
    }
    if (beacon) {
        rec->from_beacon = true;
    } else {
        rec->from_data = true;
    }
    if (coord) {
        rec->coord = true;
    }
    if (zigbee) {
        rec->zigbee = true;
    }
    if (extpan != NULL) {
        if (!rec->has_extpan) {
            memcpy(rec->extpan, extpan, 8);
            rec->has_extpan = true;
        } else if (memcmp(rec->extpan, extpan, 8) != 0) {
            char a[20];
            char b[20];
            eui64_str(a, sizeof(a), rec->extpan);
            eui64_str(b, sizeof(b), extpan);
            scan_log("PAN_EXTPAN_MISMATCH pan=0x%04x first=%s next=%s", pan, a, b);
        }
    }
}

static void wifi_shutdown(esp_netif_t *sta)
{
    esp_err_t err = esp_wifi_stop();
    if (err != ESP_OK && err != ESP_ERR_WIFI_NOT_INIT && err != ESP_ERR_WIFI_NOT_STARTED) {
        scan_log("WIFI_STOP_FAIL err=%s", esp_err_to_name(err));
    }
    err = esp_wifi_deinit();
    if (err != ESP_OK && err != ESP_ERR_WIFI_NOT_INIT) {
        scan_log("WIFI_DEINIT_FAIL err=%s", esp_err_to_name(err));
    }
    if (sta != NULL) {
        esp_netif_destroy_default_wifi(sta);
    }
}

static void wifi_scan(void)
{
    static wifi_ap_record_t aps[WIFI_MAX_AP];
    esp_netif_t *sta = NULL;
    esp_err_t err;
    uint16_t stored = WIFI_MAX_AP;
    uint16_t found = 0;

    scan_log("WIFI_BEGIN");
    err = esp_netif_init();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        scan_log("WIFI_FAIL stage=netif err=%s", esp_err_to_name(err));
        return;
    }
    err = esp_event_loop_create_default();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        scan_log("WIFI_FAIL stage=event_loop err=%s", esp_err_to_name(err));
        return;
    }
    sta = esp_netif_create_default_wifi_sta();
    if (sta == NULL) {
        scan_log("WIFI_FAIL stage=sta_netif err=NULL");
        return;
    }

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    err = esp_wifi_init(&cfg);
    if (err != ESP_OK) {
        scan_log("WIFI_FAIL stage=init err=%s", esp_err_to_name(err));
        esp_netif_destroy_default_wifi(sta);
        return;
    }
    err = esp_wifi_set_mode(WIFI_MODE_STA);
    if (err == ESP_OK) {
        err = esp_wifi_start();
    }
    if (err != ESP_OK) {
        scan_log("WIFI_FAIL stage=start err=%s", esp_err_to_name(err));
        wifi_shutdown(sta);
        return;
    }

    wifi_scan_config_t scan = {0};
    scan.show_hidden = true;
    scan.scan_type = WIFI_SCAN_TYPE_ACTIVE;
    scan.scan_time.active.min = 120;
    scan.scan_time.active.max = 300;
    err = esp_wifi_scan_start(&scan, true);
    if (err != ESP_OK) {
        scan_log("WIFI_FAIL stage=scan err=%s", esp_err_to_name(err));
        wifi_shutdown(sta);
        return;
    }

    esp_wifi_scan_get_ap_num(&found);
    memset(aps, 0, sizeof(aps));
    err = esp_wifi_scan_get_ap_records(&stored, aps);
    if (err != ESP_OK) {
        scan_log("WIFI_FAIL stage=records err=%s", esp_err_to_name(err));
        wifi_shutdown(sta);
        return;
    }

    for (int i = 0; i < stored; i++) {
        char ssid[33];
        copy_text(ssid, sizeof(ssid), aps[i].ssid, sizeof(aps[i].ssid));
        scan_log("WIFI ssid=\"%s\" bssid=%02x:%02x:%02x:%02x:%02x:%02x rssi=%d channel=%u auth=%s",
                 ssid,
                 aps[i].bssid[0], aps[i].bssid[1], aps[i].bssid[2],
                 aps[i].bssid[3], aps[i].bssid[4], aps[i].bssid[5],
                 aps[i].rssi, aps[i].primary, auth_name(aps[i].authmode));
    }
    scan_log("WIFI_END found=%u listed=%u", found, stored);
    wifi_shutdown(sta);
    vTaskDelay(pdMS_TO_TICKS(300));
}

static void note_ble(const ble_addr_t *addr, int8_t rssi, const uint8_t *data, uint8_t len)
{
    struct ble_hs_adv_fields fields;
    char name[32];
    ble_dev_t *dev = NULL;
    bool is_new = false;
    bool name_changed = false;

    memset(&fields, 0, sizeof(fields));
    name[0] = '\0';
    if (data != NULL && len > 0 && ble_hs_adv_parse_fields(&fields, data, len) == 0 && fields.name != NULL) {
        copy_text(name, sizeof(name), fields.name, fields.name_len);
    }

    for (int i = 0; i < s_ble_count; i++) {
        if (s_ble[i].used && s_ble[i].type == addr->type && memcmp(s_ble[i].addr, addr->val, 6) == 0) {
            dev = &s_ble[i];
            break;
        }
    }
    if (dev == NULL) {
        if (s_ble_count >= BLE_MAX_DEV) {
            s_ble_overflow++;
            return;
        }
        dev = &s_ble[s_ble_count++];
        memset(dev, 0, sizeof(*dev));
        dev->used = true;
        dev->type = addr->type;
        memcpy(dev->addr, addr->val, 6);
        dev->rssi = rssi;
        dev->have_rssi = rssi != 127;
        is_new = true;
    } else if (rssi != 127 && (!dev->have_rssi || rssi > dev->rssi)) {
        dev->rssi = rssi;
        dev->have_rssi = true;
    }
    if (name[0] != '\0' && strcmp(dev->name, name) != 0) {
        snprintf(dev->name, sizeof(dev->name), "%s", name);
        name_changed = true;
    }
    if (is_new || name_changed) {
        if (dev->have_rssi) {
            scan_log("BLE addr=%02x:%02x:%02x:%02x:%02x:%02x type=%s(%u) rssi=%d name=\"%s\"",
                     addr->val[5], addr->val[4], addr->val[3], addr->val[2], addr->val[1], addr->val[0],
                     addr_type_name(addr->type), addr->type, dev->rssi, dev->name);
        } else {
            scan_log("BLE addr=%02x:%02x:%02x:%02x:%02x:%02x type=%s(%u) rssi=unknown name=\"%s\"",
                     addr->val[5], addr->val[4], addr->val[3], addr->val[2], addr->val[1], addr->val[0],
                     addr_type_name(addr->type), addr->type, dev->name);
        }
    }
}

static int ble_gap_event(struct ble_gap_event *event, void *arg)
{
    (void)arg;
    switch (event->type) {
    case BLE_GAP_EVENT_DISC:
        note_ble(&event->disc.addr, event->disc.rssi, event->disc.data, event->disc.length_data);
        return 0;
#if MYNEWT_VAL(BLE_EXT_ADV)
    case BLE_GAP_EVENT_EXT_DISC:
        note_ble(&event->ext_disc.addr, event->ext_disc.rssi, event->ext_disc.data, event->ext_disc.length_data);
        return 0;
#endif
    case BLE_GAP_EVENT_DISC_COMPLETE:
        scan_log("BLE_DISC_COMPLETE reason=%d", event->disc_complete.reason);
        if (s_ble_done != NULL) {
            xSemaphoreGive(s_ble_done);
        }
        return 0;
    default:
        return 0;
    }
}

static void ble_on_reset(int reason)
{
    scan_log("BLE_HOST_RESET reason=%d", reason);
}

static void ble_on_sync(void)
{
    uint8_t own_addr_type = BLE_ADDR_PUBLIC;
    int rc;

    s_ble_synced = true;
    rc = ble_hs_util_ensure_addr(0);
    if (rc != 0) {
        s_ble_start_rc = rc;
        scan_log("BLE_FAIL stage=ensure_addr rc=%d", rc);
        xSemaphoreGive(s_ble_done);
        return;
    }
    rc = ble_hs_id_infer_auto(0, &own_addr_type);
    if (rc != 0) {
        s_ble_start_rc = rc;
        scan_log("BLE_FAIL stage=addr_type rc=%d", rc);
        xSemaphoreGive(s_ble_done);
        return;
    }

#if MYNEWT_VAL(BLE_EXT_ADV)
    struct ble_gap_ext_disc_params params = {0};
    params.itvl = 96;
    params.window = 96;
    params.passive = 0;
    rc = ble_gap_ext_disc(own_addr_type, BLE_SCAN_10MS_UNITS, 0, 0, 0, 0,
                          &params, &params, ble_gap_event, NULL);
    if (rc != 0) {
        rc = ble_gap_ext_disc(own_addr_type, BLE_SCAN_10MS_UNITS, 0, 0, 0, 0,
                              &params, NULL, ble_gap_event, NULL);
    }
#else
    struct ble_gap_disc_params params = {0};
    params.filter_duplicates = 0;
    params.passive = 0;
    rc = ble_gap_disc(own_addr_type, BLE_SCAN_10MS_UNITS * 10, &params, ble_gap_event, NULL);
#endif
    s_ble_start_rc = rc;
    if (rc != 0) {
        scan_log("BLE_FAIL stage=discover rc=%d", rc);
        xSemaphoreGive(s_ble_done);
    } else {
        scan_log("BLE_DISCOVER_STARTED active=1 duration_s=%d", BLE_SCAN_10MS_UNITS / 100);
    }
}

static void ble_host_task(void *param)
{
    (void)param;
    nimble_port_run();
    nimble_port_freertos_deinit();
}

static void ble_scan(void)
{
    int rc;

    scan_log("BLE_BEGIN");
    s_ble_done = xSemaphoreCreateBinary();
    if (s_ble_done == NULL) {
        scan_log("BLE_FAIL stage=semaphore err=ENOMEM");
        return;
    }
    rc = nimble_port_init();
    if (rc != ESP_OK) {
        scan_log("BLE_FAIL stage=init rc=%d", rc);
        vSemaphoreDelete(s_ble_done);
        s_ble_done = NULL;
        return;
    }
    ble_hs_cfg.reset_cb = ble_on_reset;
    ble_hs_cfg.sync_cb = ble_on_sync;
    ble_hs_cfg.store_status_cb = ble_store_util_status_rr;
    ble_store_config_init();
    nimble_port_freertos_init(ble_host_task);

    if (xSemaphoreTake(s_ble_done, pdMS_TO_TICKS(16000)) != pdTRUE) {
        scan_log("BLE_FAIL stage=timeout synced=%d", s_ble_synced ? 1 : 0);
        ble_gap_disc_cancel();
    }
    rc = nimble_port_stop();
    if (rc == 0) {
        nimble_port_deinit();
    } else {
        scan_log("BLE_STOP_FAIL rc=%d", rc);
    }
    scan_log("BLE_END count=%d overflow=%d", s_ble_count, s_ble_overflow);
    vSemaphoreDelete(s_ble_done);
    s_ble_done = NULL;
    vTaskDelay(pdMS_TO_TICKS(300));
}

static void on_rx(uint8_t *frame, esp_ieee802154_frame_info_t *info)
{
    rx_item_t item;
    uint8_t n;

    memset(&item, 0, sizeof(item));
    n = frame[0] & 0x7f;
    if (n > sizeof(item.psdu)) {
        n = sizeof(item.psdu);
    }
    item.psdu_len = frame[0] & 0x7f;
    if (info != NULL) {
        item.channel = info->channel;
        item.rssi = info->rssi;
        item.lqi = info->lqi;
    }
    if (n > 0) {
        memcpy(item.psdu, frame + 1, n);
    }
    esp_ieee802154_receive_handle_done(frame);
    if (s_rx_q == NULL || xQueueSendFromISR(s_rx_q, &item, NULL) != pdTRUE) {
        s_rx_drops++;
    }
}

static void on_tx_done(const uint8_t *frame, const uint8_t *ack, esp_ieee802154_frame_info_t *ack_info)
{
    (void)frame;
    (void)ack_info;
    s_tx_result = ESP_IEEE802154_TX_ERR_NONE;
    if (ack != NULL) {
        esp_ieee802154_receive_handle_done(ack);
    }
    if (s_tx_sem != NULL) {
        xSemaphoreGiveFromISR(s_tx_sem, NULL);
    }
}

static void on_tx_failed(const uint8_t *frame, esp_ieee802154_tx_error_t error)
{
    (void)frame;
    s_tx_result = (int)error;
    if (s_tx_sem != NULL) {
        xSemaphoreGiveFromISR(s_tx_sem, NULL);
    }
}

static void on_ed(int8_t power)
{
    (void)power;
    if (s_ed_sem != NULL) {
        xSemaphoreGiveFromISR(s_ed_sem, NULL);
    }
}

static esp_err_t on_enh_ack(uint8_t *frame, esp_ieee802154_frame_info_t *info, uint8_t *enhack)
{
    (void)frame;
    (void)info;
    (void)enhack;
    return ESP_FAIL;
}

static bool read_u8(const uint8_t *p, int mac_len, int *off, uint8_t *out)
{
    if (*off < 0 || *off >= mac_len) {
        return false;
    }
    *out = p[*off];
    *off += 1;
    return true;
}

static bool read_u16(const uint8_t *p, int mac_len, int *off, uint16_t *out)
{
    if (*off < 0 || *off + 1 >= mac_len) {
        return false;
    }
    *out = (uint16_t)p[*off] | ((uint16_t)p[*off + 1] << 8);
    *off += 2;
    return true;
}

static bool read_skip(int mac_len, int *off, int n)
{
    if (n < 0 || *off < 0 || *off + n > mac_len) {
        return false;
    }
    *off += n;
    return true;
}

static bool read_copy(const uint8_t *p, int mac_len, int *off, uint8_t *dst, int n)
{
    if (n < 0 || *off < 0 || *off + n > mac_len) {
        return false;
    }
    memcpy(dst, p + *off, (size_t)n);
    *off += n;
    return true;
}

static void handle_rx(const rx_item_t *item)
{
    uint8_t channel = item->channel;
    int mac_len;
    const uint8_t *p;
    uint8_t fc0;
    uint8_t fc1;
    uint8_t type;
    uint8_t version;
    uint8_t dst_mode;
    uint8_t src_mode;
    bool security;
    bool pan_comp;
    int off;
    uint8_t seq = 0;
    uint16_t dst_pan = 0xffff;
    uint16_t src_pan = 0xffff;
    bool has_dst_pan = false;
    bool has_src_pan = false;
    uint8_t src_addr[8];
    int src_len = 0;
    int idx;
    char raw[80];

    if (channel < I154_CH_MIN || channel > I154_CH_MAX) {
        channel = s_listen_channel;
    }
    idx = channel_index(channel);
    if (item->psdu_len < 2) {
        return;
    }
    mac_len = (int)item->psdu_len - 2;
    if (mac_len < 2 || mac_len > 125) {
        return;
    }
    p = item->psdu;
    fc0 = p[0];
    fc1 = p[1];
    type = fc0 & 0x07;
    security = ((fc0 >> 3) & 0x01) != 0;
    pan_comp = ((fc0 >> 6) & 0x01) != 0;
    version = (fc1 >> 4) & 0x03;
    dst_mode = (fc1 >> 2) & 0x03;
    src_mode = (fc1 >> 6) & 0x03;
    if (idx >= 0) {
        s_frames[idx]++;
    }
    if (type == 2) {
        s_ack_frames++;
        return;
    }

    hex_bytes(raw, sizeof(raw), p, mac_len, 24);
    if (version > 1 || dst_mode == 1 || src_mode == 1) {
        if (s_other_printed < 40) {
            scan_log("FRAME mode=%s channel=%u type=%s version=%u secured=%d rssi=%d lqi=%u raw=%s",
                     mode_name(), channel, frame_type_name(type), version, security ? 1 : 0,
                     item->rssi, item->lqi, raw);
            s_other_printed++;
        }
        return;
    }

    off = 2;
    if (!read_u8(p, mac_len, &off, &seq)) {
        return;
    }
    if (dst_mode != 0) {
        int dst_len = dst_mode == 2 ? 2 : 8;
        if (!read_u16(p, mac_len, &off, &dst_pan) || !read_skip(mac_len, &off, dst_len)) {
            scan_log("FRAME_TRUNCATED mode=%s channel=%u type=%s rssi=%d raw=%s",
                     mode_name(), channel, frame_type_name(type), item->rssi, raw);
            return;
        }
        has_dst_pan = true;
    }
    if (src_mode != 0) {
        src_len = src_mode == 2 ? 2 : 8;
        if (!pan_comp) {
            if (!read_u16(p, mac_len, &off, &src_pan)) {
                return;
            }
            has_src_pan = true;
        } else if (has_dst_pan) {
            src_pan = dst_pan;
            has_src_pan = true;
        }
        if (!read_copy(p, mac_len, &off, src_addr, src_len)) {
            return;
        }
    }

    if (type == 1) {
        uint16_t pan = has_src_pan ? src_pan : dst_pan;
        if (has_src_pan || has_dst_pan) {
            note_pan(pan, channel, item->rssi, false, false, false, NULL);
        }
        if (s_other_printed < 40) {
            scan_log("FRAME mode=%s channel=%u type=data pan=0x%04x rssi=%d lqi=%u secured=%d raw=%s",
                     mode_name(), channel, pan, item->rssi, item->lqi, security ? 1 : 0, raw);
            s_other_printed++;
        }
        return;
    }

    if (type == 3) {
        uint8_t cmd = 0xff;
        const char *cmd_name = "other";
        if (!security && read_u8(p, mac_len, &off, &cmd)) {
            if (cmd == 0x07) {
                cmd_name = "beacon_request";
            } else if (cmd == 0x01) {
                cmd_name = "association_request";
            } else if (cmd == 0x04) {
                cmd_name = "data_request";
            }
        }
        if (s_other_printed < 40) {
            scan_log("FRAME mode=%s channel=%u type=command cmd=%s id=%u rssi=%d lqi=%u raw=%s",
                     mode_name(), channel, cmd_name, cmd, item->rssi, item->lqi, raw);
            s_other_printed++;
        }
        return;
    }

    if (type != 0) {
        if (s_other_printed < 40) {
            scan_log("FRAME mode=%s channel=%u type=%s rssi=%d lqi=%u raw=%s",
                     mode_name(), channel, frame_type_name(type), item->rssi, item->lqi, raw);
            s_other_printed++;
        }
        return;
    }

    if (idx >= 0) {
        s_beacons[idx]++;
    }
    if (!has_src_pan) {
        scan_log("BEACON mode=%s channel=%u pan=missing rssi=%d lqi=%u secured=%d raw=%s",
                 mode_name(), channel, item->rssi, item->lqi, security ? 1 : 0, raw);
        return;
    }

    if (security) {
        note_pan(src_pan, channel, item->rssi, true, false, false, NULL);
        scan_log("BEACON mode=%s channel=%u pan=0x%04x secured=1 coord=unknown rssi=%d lqi=%u raw=%s",
                 mode_name(), channel, src_pan, item->rssi, item->lqi, raw);
        return;
    }

    {
        uint16_t superframe = 0;
        uint8_t gts = 0;
        uint8_t pending = 0;
        int gts_count;
        int payload_len;
        bool coord = false;
        bool assoc = false;
        bool zigbee = false;
        uint8_t extpan[8];
        char extpan_txt[20];
        char src_txt[20];
        char payload_txt[40];

        memset(extpan, 0, sizeof(extpan));
        extpan_txt[0] = '\0';
        src_txt[0] = '\0';
        payload_txt[0] = '\0';
        if (src_len == 2) {
            snprintf(src_txt, sizeof(src_txt), "0x%02x%02x", src_addr[1], src_addr[0]);
        } else if (src_len == 8) {
            eui64_str(src_txt, sizeof(src_txt), src_addr);
        } else {
            snprintf(src_txt, sizeof(src_txt), "none");
        }

        if (!read_u16(p, mac_len, &off, &superframe)) {
            note_pan(src_pan, channel, item->rssi, true, false, false, NULL);
            scan_log("BEACON mode=%s channel=%u pan=0x%04x src=%s superframe=missing rssi=%d lqi=%u raw=%s",
                     mode_name(), channel, src_pan, src_txt, item->rssi, item->lqi, raw);
            return;
        }
        coord = ((superframe >> 14) & 0x01) != 0;
        assoc = ((superframe >> 15) & 0x01) != 0;
        if (!read_u8(p, mac_len, &off, &gts)) {
            note_pan(src_pan, channel, item->rssi, true, coord, false, NULL);
            scan_log("BEACON mode=%s channel=%u pan=0x%04x src=%s coord=%d assoc_permit=%d payload=missing rssi=%d lqi=%u",
                     mode_name(), channel, src_pan, src_txt, coord ? 1 : 0, assoc ? 1 : 0, item->rssi, item->lqi);
            return;
        }
        gts_count = gts & 0x07;
        if (gts_count > 0) {
            if (!read_skip(mac_len, &off, 1 + (gts_count * 3))) {
                note_pan(src_pan, channel, item->rssi, true, coord, false, NULL);
                return;
            }
        }
        if (!read_u8(p, mac_len, &off, &pending)) {
            note_pan(src_pan, channel, item->rssi, true, coord, false, NULL);
            return;
        }
        if (!read_skip(mac_len, &off, (pending & 0x07) * 2 + ((pending >> 4) & 0x07) * 8)) {
            note_pan(src_pan, channel, item->rssi, true, coord, false, NULL);
            return;
        }
        payload_len = mac_len - off;
        if (payload_len < 0) {
            payload_len = 0;
        }
        hex_bytes(payload_txt, sizeof(payload_txt), p + off, payload_len, 16);
        if (payload_len >= 15 && p[off] == 0x00) {
            zigbee = true;
            memcpy(extpan, p + off + 3, 8);
            eui64_str(extpan_txt, sizeof(extpan_txt), extpan);
        }
        note_pan(src_pan, channel, item->rssi, true, coord, zigbee, zigbee ? extpan : NULL);
        if (zigbee) {
            uint8_t stack = p[off + 1] & 0x0f;
            uint8_t proto = (p[off + 1] >> 4) & 0x0f;
            uint8_t depth = (p[off + 2] >> 1) & 0x0f;
            scan_log("BEACON mode=%s channel=%u pan=0x%04x src=%s coord=%d assoc_permit=%d bo=%u so=%u zigbee=1 stack=%u proto=%u depth=%u extpan=%s rssi=%d lqi=%u payload=%s",
                     mode_name(), channel, src_pan, src_txt, coord ? 1 : 0, assoc ? 1 : 0,
                     superframe & 0x0f, (superframe >> 4) & 0x0f, stack, proto, depth,
                     extpan_txt, item->rssi, item->lqi, payload_txt);
        } else {
            scan_log("BEACON mode=%s channel=%u pan=0x%04x src=%s coord=%d assoc_permit=%d bo=%u so=%u zigbee=0 rssi=%d lqi=%u payload=%s raw=%s",
                     mode_name(), channel, src_pan, src_txt, coord ? 1 : 0, assoc ? 1 : 0,
                     superframe & 0x0f, (superframe >> 4) & 0x0f, item->rssi, item->lqi, payload_txt, raw);
        }
    }
}

static void collect_ms(int ms)
{
    TickType_t start = xTaskGetTickCount();
    TickType_t ticks = pdMS_TO_TICKS(ms);
    while ((xTaskGetTickCount() - start) < ticks) {
        rx_item_t item;
        TickType_t left = ticks - (xTaskGetTickCount() - start);
        if (left < 1) {
            left = 1;
        }
        if (xQueueReceive(s_rx_q, &item, left) == pdTRUE) {
            handle_rx(&item);
        }
    }
}

static void drain_rx(void)
{
    rx_item_t item;
    while (xQueueReceive(s_rx_q, &item, 0) == pdTRUE) {
    }
}

static void radio_listen(uint8_t channel)
{
    esp_err_t err;
    s_listen_channel = channel;
    esp_ieee802154_set_rx_when_idle(false);
    esp_ieee802154_sleep();
    err = esp_ieee802154_set_channel(channel);
    if (err != ESP_OK) {
        scan_log("I154_CHANNEL_FAIL channel=%u err=%s", channel, esp_err_to_name(err));
    }
    esp_ieee802154_set_rx_when_idle(true);
    err = esp_ieee802154_receive();
    if (err != ESP_OK) {
        scan_log("I154_RX_FAIL channel=%u err=%s", channel, esp_err_to_name(err));
    }
}

static void build_beacon_request(void)
{
    /* PSDU length includes the 2-byte FCS the radio appends. */
    s_beacon_req[0] = 10;
    s_beacon_req[1] = 0x03;
    s_beacon_req[2] = 0x08;
    s_beacon_req[3] = s_seq++;
    s_beacon_req[4] = 0xff;
    s_beacon_req[5] = 0xff;
    s_beacon_req[6] = 0xff;
    s_beacon_req[7] = 0xff;
    s_beacon_req[8] = 0x07;
}

static bool send_beacon_request(uint8_t channel)
{
    bool sent = false;
    int last = -1;

    for (int attempt = 0; attempt < 4; attempt++) {
        esp_err_t err;
        while (xSemaphoreTake(s_tx_sem, 0) == pdTRUE) {
        }
        build_beacon_request();
        s_tx_result = -1;
        err = esp_ieee802154_transmit(s_beacon_req, true);
        if (err != ESP_OK) {
            scan_log("BEACON_REQUEST_FAIL channel=%u stage=transmit err=%s", channel, esp_err_to_name(err));
            s_active_fail++;
            return false;
        }
        if (xSemaphoreTake(s_tx_sem, pdMS_TO_TICKS(400)) != pdTRUE) {
            scan_log("BEACON_REQUEST_FAIL channel=%u stage=timeout", channel);
            s_active_fail++;
            return false;
        }
        last = s_tx_result;
        if (last == ESP_IEEE802154_TX_ERR_NONE) {
            sent = true;
            break;
        }
        if (last == ESP_IEEE802154_TX_ERR_CCA_BUSY) {
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }
        break;
    }
    if (!sent && last == ESP_IEEE802154_TX_ERR_CCA_BUSY) {
        esp_err_t err;
        while (xSemaphoreTake(s_tx_sem, 0) == pdTRUE) {
        }
        build_beacon_request();
        s_tx_result = -1;
        err = esp_ieee802154_transmit(s_beacon_req, false);
        if (err == ESP_OK && xSemaphoreTake(s_tx_sem, pdMS_TO_TICKS(400)) == pdTRUE &&
                s_tx_result == ESP_IEEE802154_TX_ERR_NONE) {
            scan_log("BEACON_REQUEST channel=%u cca_override=1", channel);
            sent = true;
        } else {
            last = s_tx_result;
        }
    }
    if (sent) {
        s_active_sent++;
        return true;
    }
    s_active_fail++;
    scan_log("BEACON_REQUEST_FAIL channel=%u err=%s", channel, tx_err_name(last));
    return false;
}

static volatile int8_t s_last_ed;

static void on_ed_store(int8_t power)
{
    s_last_ed = power;
    on_ed(power);
}

static void i154_scan(void)
{
    uint8_t ext[8] = {0};
    esp_ieee802154_event_cb_list_t cbs = {
        .rx_done_cb = on_rx,
        .tx_done_cb = on_tx_done,
        .tx_failed_cb = on_tx_failed,
        .ed_done_cb = on_ed_store,
        .enh_ack_generator_cb = on_enh_ack,
    };
    esp_err_t err;
    char chans[64];

    scan_log("I154_BEGIN");
    s_rx_q = xQueueCreate(24, sizeof(rx_item_t));
    s_ed_sem = xSemaphoreCreateBinary();
    s_tx_sem = xSemaphoreCreateBinary();
    if (s_rx_q == NULL || s_ed_sem == NULL || s_tx_sem == NULL) {
        scan_log("I154_FAIL stage=queue err=ENOMEM");
        return;
    }
    err = esp_ieee802154_event_callback_list_register(cbs);
    if (err != ESP_OK) {
        scan_log("I154_FAIL stage=callback err=%s", esp_err_to_name(err));
        return;
    }
    err = esp_ieee802154_enable();
    if (err != ESP_OK) {
        scan_log("I154_FAIL stage=enable err=%s", esp_err_to_name(err));
        return;
    }
    esp_ieee802154_set_promiscuous(true);
    esp_ieee802154_set_coordinator(false);
    esp_ieee802154_set_panid(0xffff);
    esp_ieee802154_set_short_address(0xfffe);
    if (esp_read_mac(ext, ESP_MAC_IEEE802154) == ESP_OK) {
        esp_ieee802154_set_extended_address(ext);
    }
    esp_ieee802154_set_rx_when_idle(false);
    scan_log("I154_RADIO promiscuous=1 coordinator=0 auto_ack_disabled=1");

    scan_log("ED_BEGIN symbols=%u", ED_SYMBOLS);
    for (uint8_t ch = I154_CH_MIN; ch <= I154_CH_MAX; ch++) {
        int idx = channel_index(ch);
        esp_ieee802154_set_rx_when_idle(false);
        esp_ieee802154_sleep();
        esp_ieee802154_set_channel(ch);
        s_listen_channel = ch;
        while (xSemaphoreTake(s_ed_sem, 0) == pdTRUE) {
        }
        s_last_ed = -128;
        if (esp_ieee802154_energy_detect(ED_SYMBOLS) != ESP_OK) {
            scan_log("ED_FAIL channel=%u stage=start", ch);
            continue;
        }
        if (xSemaphoreTake(s_ed_sem, pdMS_TO_TICKS(500)) != pdTRUE) {
            scan_log("ED_FAIL channel=%u stage=timeout", ch);
            continue;
        }
        s_ed[idx] = s_last_ed;
        s_ed_ok[idx] = true;
        scan_log("ED channel=%u dbm=%d", ch, s_last_ed);
    }
    scan_log("ED_END");

    scan_log("PASSIVE_BEGIN ms_per_channel=%d", PASSIVE_MS);
    s_mode = MODE_PASSIVE;
    for (uint8_t ch = I154_CH_MIN; ch <= I154_CH_MAX; ch++) {
        drain_rx();
        radio_listen(ch);
        collect_ms(PASSIVE_MS);
    }
    scan_log("PASSIVE_END");

    scan_log("ACTIVE_BEGIN listen_ms=%d", ACTIVE_LISTEN_MS);
    s_mode = MODE_ACTIVE;
    for (uint8_t ch = I154_CH_MIN; ch <= I154_CH_MAX; ch++) {
        drain_rx();
        radio_listen(ch);
        send_beacon_request(ch);
        collect_ms(ACTIVE_LISTEN_MS);
        send_beacon_request(ch);
        collect_ms(ACTIVE_LISTEN_MS);
    }
    esp_ieee802154_set_rx_when_idle(false);
    esp_ieee802154_sleep();
    scan_log("ACTIVE_END requests_sent=%u requests_failed=%u", s_active_sent, s_active_fail);

    for (int i = 0; i < I154_CH_COUNT; i++) {
        if (s_ed_ok[i]) {
            scan_log("SUM CHANNEL channel=%d ed_dbm=%d frames=%u beacons=%u",
                     I154_CH_MIN + i, s_ed[i], s_frames[i], s_beacons[i]);
        } else {
            scan_log("SUM CHANNEL channel=%d ed_dbm=fail frames=%u beacons=%u",
                     I154_CH_MIN + i, s_frames[i], s_beacons[i]);
        }
    }
    if (s_pan_count == 0) {
        scan_log("SUM PAN none");
        scan_log("SUM COORDINATOR none");
    } else {
        bool any_coord = false;
        for (int i = 0; i < s_pan_count; i++) {
            char extpan_txt[20];
            mask_to_str(chans, sizeof(chans), s_pans[i].channels);
            if (s_pans[i].has_extpan) {
                eui64_str(extpan_txt, sizeof(extpan_txt), s_pans[i].extpan);
            } else {
                snprintf(extpan_txt, sizeof(extpan_txt), "none");
            }
            scan_log("SUM PAN pan=0x%04x channels=%s coordinator=%d zigbee=%d from_beacon=%d from_data=%d extpan=%s best_rssi=%d best_channel=%u",
                     s_pans[i].pan, chans, s_pans[i].coord ? 1 : 0, s_pans[i].zigbee ? 1 : 0,
                     s_pans[i].from_beacon ? 1 : 0, s_pans[i].from_data ? 1 : 0,
                     extpan_txt, s_pans[i].best_rssi, s_pans[i].best_channel);
            if (s_pans[i].coord) {
                any_coord = true;
                scan_log("SUM COORDINATOR pan=0x%04x channels=%s zigbee=%d extpan=%s rssi=%d channel=%u",
                         s_pans[i].pan, chans, s_pans[i].zigbee ? 1 : 0, extpan_txt,
                         s_pans[i].best_rssi, s_pans[i].best_channel);
            }
        }
        if (!any_coord) {
            scan_log("SUM COORDINATOR none");
        }
    }
    scan_log("I154_END drops=%u acks=%u other_printed=%u", s_rx_drops, s_ack_frames, s_other_printed);
    esp_ieee802154_disable();
}

static void print_identity(void)
{
    uint8_t base[6] = {0};
    uint8_t eui[8] = {0};
    if (esp_read_mac(base, ESP_MAC_BASE) == ESP_OK) {
        scan_log("CHIP base_mac=%02x:%02x:%02x:%02x:%02x:%02x idf=%s",
                 base[0], base[1], base[2], base[3], base[4], base[5], IDF_VER);
    } else {
        scan_log("CHIP base_mac=unknown idf=%s", IDF_VER);
    }
    if (esp_read_mac(eui, ESP_MAC_IEEE802154) == ESP_OK) {
        scan_log("CHIP eui64=%02x%02x%02x%02x%02x%02x%02x%02x",
                 eui[7], eui[6], eui[5], eui[4], eui[3], eui[2], eui[1], eui[0]);
    }
}

void app_main(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        err = nvs_flash_init();
    }
    if (err != ESP_OK) {
        printf("SCAN NVS_FAIL err=%s\n", esp_err_to_name(err));
        fflush(stdout);
    }

    esp_log_level_set("*", ESP_LOG_WARN);
    scan_log("POLICY no_join no_permit_join beacon_request_only");
    for (int s = START_WAIT_S; s >= 1; s--) {
        scan_log("WAIT seconds=%d", s);
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
    scan_log("BEGIN");
    print_identity();
    wifi_scan();
    ble_scan();
    i154_scan();
    scan_log("DONE");
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(10000));
    }
}
