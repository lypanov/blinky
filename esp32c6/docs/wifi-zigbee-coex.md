# Wi-Fi and Zigbee on one ESP32-C6

Can one ESP32-C6 run a Zigbee coordinator, with the VINDSTYRKA already joined, and a Wi-Fi station at the same time?

This note uses Espressif's ESP-IDF v5.5.6, which is the tree installed on this machine, the ESP Zigbee SDK introduction, and Espressif's replies on their own issue trackers. No board was flashed and no serial port was opened for this note. The miss counts below follow from the reporting intervals and the retry rules. They are not a measurement from the air.

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
