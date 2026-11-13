#include <stdio.h>

#include "ds18b20.h"
#include "esp_err.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "onewire_bus.h"

static const char *TAG = "tempprobe";

#define ONEWIRE_GPIO 4
#define MAX_DEVICES 8

static void print_rom(uint64_t address)
{
    for (int i = 0; i < 8; i++) {
        printf("%02X%s", (unsigned)((address >> (8 * i)) & 0xFF), i == 7 ? "" : " ");
    }
}

void app_main(void)
{
    onewire_bus_handle_t bus = NULL;
    onewire_bus_config_t bus_config = {
        .bus_gpio_num = ONEWIRE_GPIO,
        .flags = {
            .en_pull_up = true,
        },
    };
    onewire_bus_rmt_config_t rmt_config = {
        .max_rx_bytes = 10,
    };

    printf("tempprobe: DS18B20 scan on GPIO %d\n", ONEWIRE_GPIO);
    ESP_ERROR_CHECK(onewire_new_bus_rmt(&bus_config, &rmt_config, &bus));

    int found = 0;
    int ds_count = 0;
    ds18b20_device_handle_t sensors[MAX_DEVICES];
    onewire_device_iter_handle_t iter = NULL;
    onewire_device_t next_device;
    esp_err_t search_result = ESP_OK;

    ESP_ERROR_CHECK(onewire_new_device_iter(bus, &iter));
    do {
        search_result = onewire_device_iter_get_next(iter, &next_device);
        if (search_result == ESP_OK) {
            printf("ROM: ");
            print_rom(next_device.address);
            printf("\n");
            found++;
            if (ds_count < MAX_DEVICES &&
                    ds18b20_new_device_from_enumeration(&next_device, &(ds18b20_config_t) {},
                                                        &sensors[ds_count]) == ESP_OK) {
                ds_count++;
            } else if (ds_count >= MAX_DEVICES) {
                printf("device list full\n");
            } else {
                printf("not a DS18B20\n");
            }
        }
    } while (search_result == ESP_OK);
    ESP_ERROR_CHECK(onewire_del_device_iter(iter));

    if (search_result != ESP_ERR_NOT_FOUND) {
        printf("scan error: %s\n", esp_err_to_name(search_result));
    }
    printf("devices: %d\n", found);

    while (1) {
        if (ds_count == 0) {
            printf("temp: no devices\n");
        } else {
            esp_err_t err = ds18b20_trigger_temperature_conversion_for_all(bus);
            if (err != ESP_OK) {
                printf("convert failed: %s\n", esp_err_to_name(err));
            } else {
                for (int i = 0; i < ds_count; i++) {
                    float temperature = 0.0f;
                    onewire_device_address_t address = 0;
                    ds18b20_get_device_address(sensors[i], &address);
                    err = ds18b20_get_temperature(sensors[i], &temperature);
                    if (err == ESP_OK) {
                        printf("temp ROM ");
                        print_rom(address);
                        printf(": %.2f C\n", temperature);
                    } else {
                        printf("temp ROM ");
                        print_rom(address);
                        printf(": read failed: %s\n", esp_err_to_name(err));
                        if (err == ESP_ERR_INVALID_STATE) {
                            ESP_LOGW(TAG, "power-on reading (85 C) or conversion did not run");
                        }
                    }
                }
            }
        }
        /* Conversion itself waits ~800 ms at 12-bit. Pad so a sample lands about once a second. */
        vTaskDelay(pdMS_TO_TICKS(ds_count == 0 ? 1000 : 200));
    }
}
