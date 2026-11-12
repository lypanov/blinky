# Wi-Fi and Zigbee on one ESP32-C6

Can one ESP32-C6 run a Zigbee coordinator, with the VINDSTYRKA already joined, and a Wi-Fi station at the same time?

This note uses Espressif's ESP-IDF v5.5.6, which is the tree installed on this machine, the ESP Zigbee SDK introduction, and Espressif's replies on their own issue trackers. No board was flashed and no serial port was opened for this note. The miss counts below follow from the reporting intervals and the retry rules. They are not a measurement from the air.

The last section is the inverse schedule: Wi-Fi for most of each ten minutes, and the coordinator only on the wall-clock mark.

## One 2.4 GHz radio

The ESP32-C6 is a Wi-Fi, Bluetooth LE, and 802.15.4 (Thread / Zigbee) chip with a single 2.4 GHz radio. ESP-IDF's coexistence guide says a module cannot receive or transmit while another module is using the radio, so the chip shares it by time-division multiplexing.

[RF Coexistence, ESP-IDF v5.5.6 for ESP32-C6](https://docs.espressif.com/projects/esp-idf/en/v5.5.6/esp32c6/api-guides/coexist.html)

The same page says normal 802.15.4 receive is the lowest priority. Wi-Fi or BLE takes the radio whenever it asks. Transmits, ACK receive, and anything scheduled for a specific time sit higher, and they still lose when Wi-Fi or BLE holds a higher priority at that moment.

Software coexistence has to be compiled in. `CONFIG_ESP_COEX_SW_COEXIST_ENABLE` is the switch. In ESP-IDF v5.5.6 it defaults on when Wi-Fi and 802.15.4 are both enabled, and turning it on also selects `CONFIG_ESP_WIFI_STA_DISCONNECTED_PM_ENABLE`, so a station that is not associated can release the radio. The guide says the feature does not run without that option. The published API that turns on Wi-Fi plus 802.15.4 coexistence is `esp_coex_wifi_i154_enable()`.

- Header in ESP-IDF v5.5.6: `components/esp_coex/include/esp_coexist.h`
- Kconfig: `components/esp_coex/Kconfig`
- Espressif engineer, 3 Nov 2026, on [esp-idf#19306](https://github.com/espressif/esp-idf/issues/19306): that call enables coexistence and sets the 802.15.4 coexistence status. It is the API for Wi-Fi plus 802.15.4.

## Coordinator, router, and end device

The coexistence table has three 802.15.4 columns: Scan, Router, and End Device. There is no Coordinator column. A coordinator is the router that formed the network. It keeps the same always-on receiver. Espressif's note under the table is the one that applies here:

> Routers in Thread and Zigbee networks maintain unsynchronized links with their neighbors, requiring continuous signal reception. With only a single RF path, increased Wi-Fi or BLE traffic may lead to higher packet loss rates for Thread and Zigbee communications.

The marks are: **Y** supported and stable, **C1** supported but unstable, **X** not supported.

For a Wi-Fi station, the cells are:

| Wi-Fi station | 802.15.4 scan | 802.15.4 router | 802.15.4 end device |
| --- | --- | --- | --- |
| Scanning, connecting, or connected | C1 | C1 | Y |

A sleepy end device plus a connected station is the stable cell. A router or a coordinator plus a connected station is C1: it runs, and Espressif calls the performance unstable. More Wi-Fi traffic means more lost Zigbee packets. They do not publish a loss percentage.

A SoftAP is worse for this role. SoftAP connected plus a Zigbee router is **X**. Espressif staff said in March 2024 that station plus Zigbee is what they support, and AP plus Zigbee is not ([esp-zigbee-sdk#273](https://github.com/espressif/esp-zigbee-sdk/issues/273)). In May 2026 they confirmed that is still a platform limit in Zigbee SDK 1.6.8 and 2.0, and wrote again that a single ESP32-C6 is not recommended as a gateway.

The VINDSTYRKA (IKEA E2112) is itself a mains-powered Zigbee router. That does not change the C6's column. The C6 is the coordinator, so the C6 sits in the router column. The sensor pushes reports. It does not poll a parent, and nothing queues a report for later if the coordinator misses it.

[Zigbee2MQTT, IKEA E2112](https://www.zigbee2mqtt.io/devices/E2112.html)

## What Espressif ships for a gateway

The Zigbee SDK introduction describes a gateway as two chips: an 802.15.4 SoC (ESP32-H2, ESP32-C6, and so on) plus a separate Wi-Fi SoC (ESP32, ESP32-C3, ESP32-S3, and so on).

[ESP Zigbee SDK introduction](https://docs.espressif.com/projects/esp-zigbee-sdk/en/latest/esp32c6/introduction.html)

ESP-IDF v5.5.6 includes `examples/zigbee/esp_zigbee_gateway`. By default it is two chips: a Wi-Fi SoC running the example, and an ESP32-H2 running the OpenThread RCP, joined by UART. The README then allows one chip:

> The example could also run on a single SoC which supports both Wi-Fi and Zigbee (e.g., ESP32-C6), but since there is only one RF path in ESP32-C6, which means Wi-Fi and Zigbee can't receive simultaneously, it has a significant impact on performance. Hence the two SoCs solution is recommended.

[Gateway example README at v5.5.6](https://github.com/espressif/esp-idf/blob/v5.5.6/examples/zigbee/esp_zigbee_gateway/README.md)

On a C6 the example expects `CONFIG_ESP_COEX_SW_COEXIST_ENABLE` and `CONFIG_ZB_RADIO_NATIVE`. Both default on for that target. The device type is a coordinator (`ESP_ZB_ZC_CONFIG()`, `ESP_ZB_DEVICE_TYPE_COORDINATOR`). On the Zigbee skip-startup signal the example calls `esp_coex_wifi_i154_enable()`, connects as a station, then calls `esp_wifi_set_ps(WIFI_PS_MIN_MODEM)`, and only then forms the Zigbee network.

`WIFI_PS_MIN_MODEM` wakes the station for every DTIM beacon. In the README's sample log the office AP has a 102.4 ms beacon and DTIM period 1, so the station still wants the radio about ten times a second while it stays associated. That is continuous sharing, which is the C1 case, even when the station is idle. The same log forms Zigbee on channel 13 after associating to Wi-Fi channel 13. Those are different frequencies. See the next section.

Espressif's own engineers describe the same split. On [esp-zigbee-sdk#361](https://github.com/espressif/esp-zigbee-sdk/issues/361) (June 2024) they wrote that the C6 supports Wi-Fi and Zigbee coexistence and pointed at the gateway example on a C6, then said the two-chip gateway is what they recommend because it performs better. The follow-up from Espressif repeats the README: one RF path, Wi-Fi and Zigbee cannot receive at the same time, significant impact, two SoCs recommended. The coexistence guide's product line is the same: for a Wi-Fi Thread border router or a Zigbee gateway, use two SoCs and two antennas, for example ESP32-S3 plus ESP32-H2, so both radios can receive at once.

Three radios at once are a separate limit. On 3 Nov 2026, on [esp-idf#19306](https://github.com/espressif/esp-idf/issues/19306), Espressif wrote that simultaneous Wi-Fi, 802.15.4, and BLE traffic is not supported and can introduce unknown risks. The validated pattern is two stacks active at a time. The report itself was filed against ESP-IDF v5.3. This machine is on v5.5.6. The "two at a time" limit is the part Espressif stated as current.

## Does the Wi-Fi channel have to match the Zigbee channel?

No. Espressif never says the station and the Zigbee network have to sit on one channel. The gateway example pins Zigbee to channel 13 (`ESP_ZB_PRIMARY_CHANNEL_MASK` is `1 << 13` in `esp_zigbee_gateway.h`) and lets the station follow the access point. Nothing in that example copies one channel onto the other.

The channel numbers are also different scales. IEEE 802.15.4 channels 11 through 26 are 5 MHz apart, with centers from 2405 MHz to 2480 MHz. Channel 13 is 2415 MHz, and the signal is about 2 MHz wide. Wi-Fi channel 13 in the 2.4 GHz band is centered at 2472 MHz. The sample log's "Wi-Fi channel 13" and "Zigbee channel 13" are 57 MHz apart.

[Silicon Labs, network formation: 802.15.4 centers from 2.405 GHz to 2.480 GHz](https://docs.silabs.com/zigbee/9.0.1/zigbee-concepts/network-activities)

[Silicon Labs, Wi-Fi impact on 802.15.4](https://docs.silabs.com/bluetooth/10.1.2/multiprotocol-wifi-coexistence-fundamentals/02-wi-fi-impact-on-bluetooth-and-802-15-4-radios)

Overlap still matters, because other Wi-Fi transmitters keep using the air while this chip is listening to Zigbee. Zigbee channel 13 at 2415 MHz sits inside Wi-Fi channel 1 (center 2412 MHz, about 20 MHz wide). It sits clear of Wi-Fi channel 6 (2437 MHz) and channel 11 (2462 MHz). An access point on channel 1 lands on this Zigbee channel. An access point on 6 or 11 does not.

The VINDSTYRKA coordinator source forms its network on Zigbee channel 13 only, the same mask as Espressif's gateway example (`ESP_ZB_PRIMARY_CHANNEL_MASK` is `1 << 13` in `esp32c6/main/vindstyrka_coord.c`). The sensor is already on that network. Moving it to a quieter Zigbee channel means forming again and joining again. The station cannot pick a channel of its own. It uses whatever channel the access point is on.

The same-channel rule in the Wi-Fi driver is a different rule. In station-plus-SoftAP mode the two Wi-Fi roles on one chip have to share one home channel, and the station wins. That is Wi-Fi sharing a channel with itself.

[Wi-Fi driver, ESP-IDF v5.5.6](https://docs.espressif.com/projects/esp-idf/en/v5.5.6/esp32c6/api-guides/wifi.html)

## Limits that apply to this coordinator

- One radio. While the station transmits or receives, the coordinator is deaf, and the other way around.
- The role we need is the unstable cell: Wi-Fi station connected, 802.15.4 router / coordinator, marked C1.
- Idle Zigbee receive loses to Wi-Fi. A sensor report is a short unsolicited frame. If a Wi-Fi slice covers that frame and the MAC retries, the report is gone.
- SoftAP plus this coordinator is marked X, and Espressif still called AP plus Zigbee unsupported in May 2026.
- BLE plus Wi-Fi plus Zigbee, all moving traffic, is not a supported combination.
- A gateway product, in Espressif's words, should be two SoCs and two antennas.
- Staying associated keeps a DTIM wake-up on the radio for as long as the station is up. Minimum modem sleep gives Zigbee the gaps. It does not give Zigbee the radio full time.
- Espressif does not document a `zigbee_pause` / `zigbee_resume` pair. [esp-zigbee-sdk#361](https://github.com/espressif/esp-zigbee-sdk/issues/361) asked for exactly that. The reply was coexistence, then two chips.

## If coexistence is too lossy

### Give Zigbee the radio, and visit Wi-Fi about every 10 minutes

Leave the station disconnected for most of the time. With software coexistence enabled, a disconnected station is built to release the radio, so the coordinator can listen. About every 10 minutes, associate, do the Wi-Fi transfer, and disconnect again. During that visit the chip is back in the C1 case for however long the visit lasts.

The coordinator source asks the VINDSTYRKA for reports on temperature (cluster 0x0402), humidity (0x0405), PM2.5 (0x042A), and the IKEA VOC index (0xFC7E). Each one is configured with minimum interval 10 and maximum interval 30. Zigbee2MQTT's reporting constants store one minute as 60 (`repInterval.MINUTE`), so these ZCL fields are seconds. The reportable change is 50 for temperature and humidity, which is 0.5 °C and 0.5 %RH on the cluster scale of hundredths, and 1.0 for the two float values. Zigbee2MQTT configures this sensor's PM2.5 and VOC index more loosely, minimum 1 minute and maximum 2 minutes. The intervals that matter here are the ones this coordinator wrote.

[Zigbee2MQTT reporting constants](https://github.com/Koenkk/zigbee-herdsman-converters/blob/master/src/lib/constants.ts)

[Zigbee2MQTT converter, PM2.5](https://github.com/Koenkk/zigbee-herdsman-converters/blob/master/src/devices/ikea.ts)

[Zigbee2MQTT converter, VOC index](https://github.com/Koenkk/zigbee-herdsman-converters/blob/master/src/lib/ikea.ts)

A report is one ZCL message. ZBOSS allows 3 MAC retries after a failed transmission (`ZB_MAC_MAX_FRAME_RETRIES` in esp-zboss-lib 1.6.4). That budget is milliseconds. It does not stretch across a visit that lasts seconds. The sensor does not store the skipped samples. The next report carries the value at that later time. A hole is a missing point, and the series continues from the next successful report.

If the reading is steady, the sensor reports each value at the maximum interval, every 30 seconds. A visit of T seconds then drops about T/30 reports per reading. A changing reading can report as often as the minimum, every 10 seconds, and the cost rises to about T/10.

| Wi-Fi visit, every 10 minutes | Steady reading (every 30 s) | Fast change (every 10 s) |
| --- | --- | --- |
| 15 seconds | usually zero or one missing sample per reading | one or two |
| 30 seconds | about one | about three |
| 60 seconds | about two | about six |

Over an hour that is six visits. A 15-second visit costs on the order of a few missing samples per reading per hour, out of about 120 samples at the 30-second pace. A 60-second visit costs about 12 steady samples per reading per hour, which is about one tenth of them.

There is a second cliff at 45 seconds. Zigbee routers send link status every `nwkLinkStatusPeriod`, and ZBOSS sets that to 15 seconds. `nwkRouterAgeLimit` is 3. The ZBOSS headers say both numbers are the Zigbee Specification revision 22, subclause 3.5.1, values. After 45 seconds without link status, the neighbor's link cost is reset. A visit that stays under that, such as 15 or 30 seconds, stays inside one or two link-status periods. A visit of a minute can age the link out. This is a one-hop network, sensor to coordinator, so the next link status after Wi-Fi drops can restore the neighbor. The reports that fell inside the visit are still gone.

The 10-minute gap between visits does not throw away 10 minutes of readings. It throws away the readings whose transmit time landed inside the visit. Keeping the visit short is the whole of the saving. Association, DHCP, and a TLS handshake already take several seconds, so a "quick" visit is realistically the 15-second row, and a slow server pushes it toward 30.

Leaving the station associated for the whole 10 minutes is the other regime. That is continuous C1 sharing. Espressif says loss goes up with Wi-Fi traffic and does not give a rate. The table above does not apply to that regime.

### Put Wi-Fi on a second device

Espressif's recommended gateway is two chips and two antennas. The IDF example is a Wi-Fi SoC plus an ESP32-H2 RCP, UART between them, and on the dedicated gateway board a 3-wire PTA grant so the two radios can be arbitrated without sharing one RF path. The C6 can play the RCP role in that split. Their stated gain is that Wi-Fi and 802.15.4 can receive at the same time.

The smaller split, for a network that is already joined, is to leave this C6 as the Zigbee coordinator it already is and do Wi-Fi somewhere else. The station then never takes this radio. The sensor's reports stay on the schedule the coordinator configured, and the 15-second holes above do not open. The C6 is already attached to the Pi 400 by USB, and that Pi has its own Wi-Fi, so the second device does not have to be another Espressif chip.

## Answer

It depends. One ESP32-C6 can run this Zigbee coordinator and a Wi-Fi station together: Espressif's gateway example does that on a C6, and their engineers say the chip supports it. They also mark that pair unstable, because a coordinator has to keep listening and the chip has one radio, and they tell gateway products to use two chips. For this joined VINDSTYRKA, a Wi-Fi visit of about 15 seconds every 10 minutes usually misses zero or one sample per reading, and a second device for Wi-Fi keeps every sample.

## Inverse schedule: Wi-Fi most of the time

The schedule Alex prefers keeps the ESP32-C6 on Wi-Fi for most of each ten minutes, and switches it to the Zigbee coordinator for a short window on each wall-clock mark, for example 23:50:00–23:51:00. Other devices can treat that mark as the time the C6 will not take Wi-Fi requests. The C6 is already the coordinator. The VINDSTYRKA (IKEA E2112) is already joined, and it is a mains-powered router.

This section uses the same ESP-IDF v5.5.6 tree, ESP Zigbee SDK 1.6.8 and ZBOSS from esp-zboss-lib 1.6.4 as installed for the coordinator, and the Zigbee Specification revision 23 (document 05-3474-23). No board was flashed and no serial port was opened. The times below are the published budgets and the retry arithmetic. They are not a measurement of this chip.

[Zigbee Specification revision 23, CSA, 15 March 2023](https://csa-iot.org/wp-content/uploads/2023/04/05-3474-23-csg-zigbee-specification-compressed.pdf)

### How long the switch takes

Espressif does not publish one duration for "stop Wi-Fi, run the coordinator, start Wi-Fi again." The published pieces are a driver stop, a scan budget, and a DHCP timer tick.

**Wi-Fi off.** `esp_wifi_stop()` stops the station and frees the station control block. When it returns `ESP_OK`, `WIFI_EVENT_STA_STOP` follows. The event task then releases the station IP address, stops the DHCP client, removes TCP and UDP connections, and clears the station netif. That is the moment the C6 cannot take a Wi-Fi request. The guide describes a driver stop, and it gives that stop no millisecond budget.

[Wi-Fi driver, ESP-IDF v5.5.6, `WIFI_EVENT_STA_STOP`](https://docs.espressif.com/projects/esp-idf/en/v5.5.6/esp32c6/api-guides/wifi.html)

**The coordinator returns as the same network.** A coordinator does not rejoin a network. Revision 23 says so in the beacon-survey procedure: a coordinator that receives `Mgmt_NWK_Beacon_Survey_req` rejects it, because "the coordinator does not perform rejoins" (section 2.4.3.3.12.3). The C6 is the network. Coming back means putting the same PAN on the air: the same extended PAN id, the same network key, channel 13, short address 0x0000.

`esp_zb_start(true)` loads NVRAM and then starts. In esp-zigbee-lib 1.6.8, `esp_zigbee_core.h` says startup is formation for a coordinator, or rejoin, or a discovery join, and the application hears the result in `esp_zb_app_signal_handler`. With NVRAM left intact, a later start raises `ESP_ZB_BDB_SIGNAL_DEVICE_REBOOT`, "joins or rejoins network from the configured network information." `esp_zb_factory_reset()` erases the `zb_storage` partition and restarts. `esp_zb_nvram_erase_at_start(true)` wipes NVRAM on every boot. Either one makes the next start factory-new. A factory-new formation, even with the channel mask still pinned to channel 13, creates a new PAN id and a new key. The VINDSTYRKA stays on the old PAN. The resume path is the one that still has the sensor.

SDK 1.6.8 has no `esp_zb_stop`. That same header exposes `esp_zb_start`, `esp_zb_is_started`, sleepy-end-device sleep, factory reset, and a local leave. [esp-zigbee-sdk#361](https://github.com/espressif/esp-zigbee-sdk/issues/361) asked for pause and resume. The reply, already cited above, was coexistence, then two chips. ESP-IDF v5.5.6 does have `esp_ieee802154_disable()`, which deinitializes the raw 802.15.4 subsystem. The Zigbee SDK does not say a running coordinator survives that call.

[`esp_ieee802154_disable` in ESP-IDF v5.5.6](https://github.com/espressif/esp-idf/blob/v5.5.6/components/ieee802154/include/esp_ieee802154.h)

Two shapes follow from that.

1. The Zigbee stack stays up for the life of the boot. The window is `esp_wifi_stop`, the poll below, then `esp_wifi_start` and `esp_wifi_connect`. The coordinator does not rejoin, and the sensor does not have to join again. The unpublished part on the front of the window is how long `esp_wifi_stop` takes to reach `WIFI_EVENT_STA_STOP`. For the other nine minutes the station is associated, and this is the C1 case from the first half of this note. Wi-Fi and the coordinator share the one radio. The coordinator is still on the air in the gaps the station leaves, so those nine minutes are not a hard Zigbee silence.
2. Wi-Fi runs with the Zigbee stack not started, and each window calls `esp_zb_start(true)` against the saved network, polls, then has to get the 802.15.4 radio off again. That is the shape that matches a coordinator which is off the air except on the mark. The SDK has no stop, so the documented way back to a Wi-Fi-only process is a reboot. Espressif does not publish that boot-plus-start time. The high-resolution timer does not survive a reset. The RTC timer does, except on a power-on reset. See the clock section.

**Wi-Fi back.** `esp_wifi_start` raises `WIFI_EVENT_STA_START`. `esp_wifi_connect` scans for the configured AP before it associates. That scan matches "scan for a specific AP," and a fast scan ends when the first match is found. Fast scan is the default (`WIFI_FAST_SCAN`). The default active scan waits at most 120 ms on a channel (`scan_time.active.max` in `esp_wifi_scan_start`), and the minimum is 0, so a channel can finish sooner when the probe response arrives. Those same defaults are what a connect-scan uses (`esp_wifi_set_scan_parameters`).

If the stored channel is 0, the station walks channel 1 through N. If the channel is set, it starts on that channel and walks the others only when the AP is not there. Thirteen 2.4 GHz channels at 120 ms is 1.56 seconds. That is the published ceiling for a walk that finds the AP on the last channel. A stored channel that still has the AP is one dwell, at most 120 ms.

Association has no published duration. `WIFI_EVENT_STA_CONNECTED` means the station can pass frames, and it is the event that starts the DHCP client. An application that needs an IP waits for the got-IP event. The DHCP coarse timer defaults to 1 second (`CONFIG_LWIP_DHCP_COARSE_TIMER_SECS`). That is how often the client advances its state machine. `CONFIG_LWIP_DHCP_RESTORE_LAST_IP` defaults off, and `WIFI_EVENT_STA_STOP` has already dropped the address, so the next connect does a full discover. Sockets from before the stop are gone. A client opens a new connection after the got-IP event.

The blackout other devices see is the Zigbee window plus this return. The scan on the way back is at most 1.56 seconds, or at most 120 ms when the channel is known and the AP answers. Association and DHCP sit after that, and Espressif does not bound them. A Wi-Fi client that tries at the first second after the Zigbee window can still meet a station that is scanning or waiting for DHCP.

[Wi-Fi scan defaults, `esp_wifi_scan_start`, ESP-IDF v5.5.6](https://github.com/espressif/esp-idf/blob/v5.5.6/components/esp_wifi/include/esp_wifi.h)

### Reports while the coordinator is off the air

A report is one ZCL message carrying the current value. The sensor keeps no queue of samples it failed to deliver. The next report, on the 10-second minimum and 30-second maximum this coordinator wrote, carries the value at that later time.

The attempt that hits a silent coordinator dies inside a few seconds:

- MAC. ZBOSS allows 3 retries after a failed transmission (`ZB_MAC_MAX_FRAME_RETRIES` in esp-zboss-lib 1.6.4). As the earlier section says, that budget is milliseconds.
- NWK. Revision 23 sets `nwkcUnicastRetries` to 3 and `nwkcUnicastRetryDelay` to 50 ms (NWK constants, section 3.5.1). That is a few hundred milliseconds inside one attempt.
- APS, when the frame asks for an APS acknowledgement. `apscMaxFrameRetries` is 3. `apscAckWaitDuration` is 1.6 seconds, from `0.05 * (2 * nwkcMaxDepth) + 0.1` with `nwkcMaxDepth` 15 (section 2.2.7.1). The sender waits, then transmits again, up to 3 retransmissions (section 2.2.8.4.4). The failure path is four attempts at up to 1.6 seconds, about 6.4 seconds, and then the APS sub-layer tells the next layer the transmission failed. The report is dropped. ZBOSS, on a command this coordinator sends to a non-sleepy device, waits 3 seconds instead of 1.6 (`ZB_N_APS_ACK_WAIT_DURATION_FROM_NON_SLEEPY`), so the failure path of a read below is about 12 seconds. The sensor's own stack may use the 1.6 second spec value. Both numbers are seconds, and the nine minutes of Wi-Fi are longer than either.

Link status does not save the report. A router or coordinator sends a link status every `nwkLinkStatusPeriod` seconds, default 15 (`0x0f`), as a one-hop broadcast without retries (section 3.6.4.4.1). `nwkRouterAgeLimit` is 3 (section 3.5.2, NIB attribute `0xa7`). ZBOSS cites the same two numbers as Zigbee Specification revision 22, subclause 3.5.1, and the values match revision 23. After 45 seconds with no link status from the coordinator, the VINDSTYRKA sets that neighbor's outgoing cost to 0. The specification calls the entry stale, and says it may be reused if the neighbor table needs the slot (section 3.6.4.4.4). Stale is a routing cost.

Leave is `NLME-LEAVE`. A channel change is `Mgmt_NWK_Update_req` with `ScanDuration` `0xFE`, sent by the network manager (section 2.4.3.3.9). The coordinator is off the air, so it is not sending that command. The router's channel stays the channel in its NIB. This coordinator formed the network on Zigbee channel 13 only. Revision 23 also requires a router to be able to rejoin if communication is lost (section 2.5.2.4). That sentence is a capability the stack must have. It does not name nine minutes of silence as the event that starts a channel scan. This note did not watch the E2112.

When the coordinator returns with the same PAN, the same key, and channel 13, the sensor is still a member. The first poll can pay for a route discovery, because the outgoing cost was zeroed. On 2.4 GHz the route-request retry interval is 254 ms (`nwkcRREQRetryInterval`, `0xfe` ms), and the first broadcast is retried 3 times (`nwkcInitialRREQRetries`). On this one-hop link that still fits in the window below.

### Polling with Read Attributes

The coordinator can read the current values in the window. Always-on reporting is optional.

ZCL general command `0x00` is Read Attributes (`ZB_ZCL_CMD_READ_ATTRIB` in esp-zboss-lib 1.6.4, `zcl/zb_zcl_commands.h`). SDK 1.6.8 sends it with `esp_zb_zcl_read_attr_cmd_req()`. The coordinator firmware already sends that command once during setup, for attribute `measuredValue` (`0x0000`) on temperature (cluster `0x0402`), humidity (`0x0405`), PM2.5 (`0x042A`), and the IKEA VOC index (`0xFC7E`, manufacturer code `0x117C`). Those four reads are the poll. The VOC read is a manufacturer-specific frame. The others are standard. The call takes the manufacturer flag and the manufacturer code, which the setup path already fills in.

The VINDSTYRKA is a mains-powered router, so its receiver stays on. It can answer a unicast while the coordinator is on channel 13. Read Attributes returns the value the sensor holds at that moment. The nine minutes of missed reports are not in that response.

Reporting can stay at minimum 10 and maximum 30. The reports that land in the Wi-Fi period are still dropped, as above. A later Configure Reporting can set the maximum reporting interval to `0xFFFF`. ZBOSS names that value `ZB_ZCL_REPORTING_NOT_NEEDED` and says reporting is not needed for the attribute (`zcl/zb_zcl_reporting.h`). The poll works with reporting left as it is, and it works after that `0xFFFF` write.

Four clusters means four commands. The setup code sends them one at a time and arms a 5 second application timeout (`SETUP_TIMEOUT_MS` in `esp32c6/main/vindstyrka_coord.c`). On a healthy link each one is a request and a response, and four of them finish in well under a second of airtime. A read that never gets an APS acknowledgement can sit in this ZBOSS for about 12 seconds, four attempts at 3 seconds, before the stack gives up. Serializing four reads that each burn that whole budget would be about 48 seconds, and the window would still have no sample. The useful budget is one healthy pass, plus room for one of those 12 second misses.

### Clock drift, and SNTP as a later step

While the chip is awake, system time uses the high-resolution timer. ESP-IDF v5.5.6 says that timer runs from APB_CLK, typically 80 MHz, with a frequency deviation of less than ±10 ppm, at 1 µs resolution. Ten parts per million across the ten minutes between marks is 6 ms. Across the default SNTP period of one hour it is 36 ms. Espressif's hardware design guidelines for the ESP32-C6 require the 40 MHz crystal to be within ±10 ppm, which is the same order. A 15 second window does not move under that error.

[System Time, ESP-IDF v5.5.6 for ESP32-C6](https://docs.espressif.com/projects/esp-idf/en/v5.5.6/esp32c6/api-reference/system/system_time.html)

[ESP32-C6 schematic checklist, external 40 MHz crystal](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32c6/schematic-checklist.html)

The RTC is the other timer. It keeps time in sleep, and it persists across resets other than a power-on reset. The high-resolution timer does neither. On the C6 the default RTC source is the internal slow RC, about 136 kHz. The datasheet lists that oscillator next to the 40 MHz crystal and the 480 MHz PLL. ESP-IDF says the RC's frequency moves with temperature, and that this deviation shows up in light sleep and deep sleep. The same release's BLE guide says this 136 kHz RC, used as a sleep clock, has a sleep-clock accuracy exceeding 500 ppm. Five hundred parts per million across ten minutes is 0.3 seconds. This schedule is awake on Wi-Fi, so the high-resolution timer is the clock that hits the mark. The RC is the clock that matters if a later version sleeps, or if each window reboots and the time has to cross that reset on the RTC.

[ESP32-C6 Series Datasheet, section 4.1.3.3 Clock](https://documentation.espressif.com/esp32-c6_datasheet_en.html)

[Low-power BLE clock sources, ESP-IDF v5.5.6 for ESP32-C6](https://docs.espressif.com/projects/esp-idf/en/v5.5.6/esp32c6/api-guides/low-power-mode/low-power-mode-ble.html)

The wall-clock marks need civil time. After boot, `gettimeofday` is not 23:50 until something sets it. SNTP over the station does that, and it belongs in a later step, once the radio schedule is chosen. `esp_netif_sntp_init()` with a server such as `pool.ntp.org` starts the client. `esp_netif_sntp_sync_wait()` blocks until a reply, or until its timeout. The default mode writes the new time immediately (`SNTP_SYNC_MODE_IMMED`). The update period defaults to one hour (`CONFIG_LWIP_SNTP_UPDATE_DELAY` is 3600000 ms). The Kconfig minimum is 15 seconds, which is the SNTPv4 floor from RFC 4330. With the startup delay left on, the first request waits a random time up to 5 seconds (`CONFIG_LWIP_SNTP_MAXIMUM_STARTUP_DELAY`). That delay keeps a herd of devices off the server at once. One C6 can turn it off when this step is written. The example Espressif ships is `examples/protocols/sntp`.

An uptime timer can prove the radio switch before any of that. The marks at :00, :10, :20, :30, :40, and :50 wait until the station has an IP and one SNTP reply. Other devices that avoid the window need a time source of their own. After this C6 has synced, its own error is the ±10 ppm above. A partner whose clock is off by many seconds will miss a 15 second window and still land inside a 60 second one.

### Verdict

It depends. The inverse plan works as a way to take one current reading from the VINDSTYRKA every ten minutes, by Read Attributes, with the coordinator brought back as the same network. Reports sent while the coordinator is off the air are dropped after a few seconds of MAC, NWK, and APS retries. The sensor stays joined, and it stays on channel 13.

The Zigbee airtime for the poll is 15 to 20 seconds when the stack is already running: stop Wi-Fi, read the four attributes, start Wi-Fi. That covers a healthy poll, one ZBOSS APS-acknowledgement miss of about 12 seconds, and the route discovery that can follow 45 seconds of silence. `esp_wifi_stop` on the front of that window has no published duration. On the way back, the scan is at most 1.56 seconds, or at most 120 ms on a known channel, and association plus DHCP are unbounded beyond the 1 second DHCP timer tick. That 15 to 20 seconds is the poll. It leaves the coordinator sharing the radio for the other nine minutes.

A coordinator that is actually off the air except on the mark has to boot the Zigbee stack for the window and shut it down afterwards. SDK 1.6.8 has no pause, so that shutdown is a reboot, and Espressif does not publish the boot-plus-start time. Until that cycle is measured, keep the Zigbee window at the full minute.

Advertise that same minute, 23:50:00–23:51:00, to anything that uses the C6 over Wi-Fi. It holds a 15 to 20 second poll, the Wi-Fi return, and a few seconds of skew on the other device's clock. It also has room for the unmeasured cold start. The minute does not bring back the readings from the other nine minutes.
