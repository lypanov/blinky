idf_component_register(SRCS "room_scan.c"
                       PRIV_REQUIRES nvs_flash esp_wifi esp_event esp_netif ieee802154 bt
                       INCLUDE_DIRS ".")
