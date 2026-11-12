# Netatmo setup

Steps to create a Netatmo app, get a token for the weather station, and call the API from the ESP32-C6.

Do not put the Netatmo account password in git, in this file, or on the C6. Type it only on Netatmo's own login page. The client secret is entered later, on the device. It is not in this PR and it does not go in git.

Sources, checked 2026-11-12:

- Account and app: [dev.netatmo.com](https://dev.netatmo.com/), [create an app](https://dev.netatmo.com/apps/createanapp), [your apps](https://dev.netatmo.com/apps/), [guidelines](https://dev.netatmo.com/guideline)
- OAuth and scopes: [Authentication](https://dev.netatmo.com/apidocumentation/oauth)
- Weather calls: [Weather](https://dev.netatmo.com/apidocumentation/weather) and the Weather OpenAPI on that page
- `homestatus` scope: [Energy](https://dev.netatmo.com/apidocumentation/energy) and [Home + Security](https://dev.netatmo.com/apidocumentation/security)
- HTTP 429: [API glossary](https://dev.netatmo.com/apidocumentation/general)

## 1. Developer account and app

1. Open [https://dev.netatmo.com/](https://dev.netatmo.com/).
2. Sign in. The app pages send you to [https://auth.netatmo.com/](https://auth.netatmo.com/). If you have no Netatmo login, create it there. The password stays on that page.
3. Open [https://dev.netatmo.com/apps/createanapp](https://dev.netatmo.com/apps/createanapp#form) and create the app. That is the link in the guidelines.
4. Open [https://dev.netatmo.com/apps/](https://dev.netatmo.com/apps/) and open the new app.
5. Copy the client ID.
6. Set a redirect URI in the app settings. Use that exact string from here on. It has to match character for character, including `http` versus `https`. If nothing is listening on that URI, the browser may show a connection error after approval. The `code` is still in the address bar.
7. Copy the client secret into a private note. Do not commit it.

When you approve the app in the next section, sign in as the Netatmo account that owns the weather station. `getstationsdata` returns that account's stations.

## 2. Scope

Request `read_station`.

That is the read scope for the station family. The gateway type on the scope table is `NAMain` (the weather station's main module). The [Authentication](https://dev.netatmo.com/apidocumentation/oauth) page also lists `write_station` for that family. The Weather OpenAPI does not attach `write_station` to any call. Do not request it for reading.

Do not request scopes for other products. Thermostat, camera, Home Coach, smoke, and the rest are other devices. This account's task is the weather station. The weather page lists these module types, and `getstationsdata` returns whichever of them are actually on the account:

| Type | What the weather page calls it |
| --- | --- |
| `NAMain` | Main indoor module |
| `NAModule1` | Outdoor module |
| `NAModule2` | Anemometer |
| `NAModule3` | Rain gauge |
| `NAModule4` | Additional indoor module |

If no scope is sent on the token request, Netatmo's default is `read_station`. Send `read_station` anyway.

## 3. Get the tokens

Do this once, in a browser on a computer. The C6 does not do this step. The flow is the OAuth 2.0 authorization code grant on the [Authentication](https://dev.netatmo.com/apidocumentation/oauth) page. There is no password grant.

1. Make a random `state` string and keep it.
2. Open this URL. Percent-encode `REDIRECT_URI` so it matches the app settings character for character.

```
https://api.netatmo.com/oauth2/authorize?client_id=CLIENT_ID&redirect_uri=REDIRECT_URI&scope=read_station&state=STATE
```

3. Approve `read_station` on Netatmo's page. If you refuse, the redirect has `error=access_denied`.
4. The browser returns to your redirect URI:

```
REDIRECT_URI?state=STATE&code=CODE
```

Check that `state` matches. Copy `code`. Exchange it once, right away. Do not reuse it.

5. POST the form below. `Content-Type` is `application/x-www-form-urlencoded`, not JSON. `redirect_uri` is the same string as in the app settings.

```
curl -sS https://api.netatmo.com/oauth2/token \
  --data-urlencode grant_type=authorization_code \
  --data-urlencode client_id=CLIENT_ID \
  --data-urlencode client_secret=CLIENT_SECRET \
  --data-urlencode code=CODE \
  --data-urlencode redirect_uri=REDIRECT_URI \
  --data-urlencode scope=read_station
```

6. A 200 response is JSON with `access_token`, `expires_in`, and `refresh_token`. The documented example of `expires_in` is `10800` (seconds). Use the number in the response.

`redirect_uri_mismatch` means the redirect URI does not match the app. `invalid_grant` means the code is invalid, already used, or the redirect URI differed between the authorize step and this POST.

## 4. How refresh tokens rotate

When `access_token` expires, POST:

```
curl -sS https://api.netatmo.com/oauth2/token \
  --data-urlencode grant_type=refresh_token \
  --data-urlencode refresh_token=CURRENT_REFRESH_TOKEN \
  --data-urlencode client_id=CLIENT_ID \
  --data-urlencode client_secret=CLIENT_SECRET
```

The response again has `access_token`, `expires_in`, and `refresh_token`.

Netatmo's auth page says to store the new `access_token` and the new `refresh_token`. They replace the previous ones. The old values are invalidated immediately and cannot be reused. Write the new refresh token to storage before you drop the old one. If that write fails, the next refresh fails and you must redo section 3.

Netatmo does not publish a refresh-token lifetime. They do say that an expired or revoked refresh token cannot be used, and the user must authorize again from section 3.

Only one place should refresh a given token. A second refresh with the old token fails, because that token is already dead.

## 5. What the C6 must store

Store these in flash that survives reboot (NVS), not in the source tree:

- `client_id`
- `client_secret` (entered later, not in git)
- the latest `refresh_token` only
- the latest `access_token`
- when that access token expires (time of the response, plus `expires_in` seconds)
- the granted scope (`read_station`)

The [guidelines](https://dev.netatmo.com/guideline) say you must never store the user's credentials. You store tokens. The password is not a token.

The [Authentication](https://dev.netatmo.com/apidocumentation/oauth) page also says the client secret must stay server-side and must not be put in on-device firmware. The C6 is the client that will refresh tokens, and the refresh call requires the secret, so the secret will be entered on the C6 later. It is still not committed.

Send the access token on API calls as a Bearer token ([RFC 6750](https://tools.ietf.org/html/rfc6750)):

```
Authorization: Bearer ACCESS_TOKEN
```

## 6. Which endpoints to call

Base URL from the Weather OpenAPI: `https://api.netatmo.com/api`

All three Weather calls are GET, scope `read_station`.

### getstationsdata

```
GET https://api.netatmo.com/api/getstationsdata
```

Scope `read_station`. Returns the account's weather stations: measures and device data (firmware, Wi-Fi, battery, radio, reachability).

Optional query parameters:

- `device_id` — station MAC address. Omit it to get the stations on the account.
- `get_favorites` — favorite stations. Default false. Omit it.

The [Weather](https://dev.netatmo.com/apidocumentation/weather) page says this call reads the cloud copy, updated about every 10 minutes. One sentence on that page writes the path as `/gestationsdata`. That is a typo. The path in the same page's table and in the OpenAPI is `/getstationsdata`.

### getmeasure

```
GET https://api.netatmo.com/api/getmeasure
```

Scope `read_station`. History for one station or one module.

Required query parameters:

- `device_id` — station MAC
- `scale` — one of `30min`, `1hour`, `3hours`, `1day`, `1week`, `1month`
- `type` — measurements to return. Documented names:
  - temperature: `temperature`, `min_temp`, `max_temp`, `date_min_temp`, `date_max_temp`
  - humidity: `humidity`, `min_hum`, `max_hum`, `date_min_hum`, `date_max_hum`
  - CO2: `co2`, `min_co2`, `max_co2`, `date_min_co2`, `date_max_co2`
  - pressure: `pressure`, `min_pressure`, `max_pressure`, `date_min_pressure`, `date_max_pressure`
  - noise: `noise`, `min_noise`, `max_noise`, `date_min_noise`, `date_max_noise`
  - rain: `rain`, `min_rain`, `max_rain`, `sum_rain`, `date_min_rain`, `date_max_rain`
  - wind: `windstrength`, `windangle`, `guststrength`, `gustangle`, `date_min_gust`, `date_max_gust`

The date fields exist only for scales from `1day` to `1month`. The weather page lists pressure in mbar. The `getmeasure` parameter text says bar. Read the units off the live JSON.

Optional:

- `module_id` — module MAC. Omit it for the main module.
- `date_begin`, `date_end` — local Unix time in seconds. Default for `date_begin` is the oldest stored data.
- `limit` — max measurements. Default and maximum are 1024.
- `optimize` — default true.
- `real_time` — default false. True gives exact timestamps.

### getpublicdata

```
GET https://api.netatmo.com/api/getpublicdata
```

Scope on the operation is `read_station`. The description text also says `scope/none_required`. This is public outdoor data inside a map rectangle, not this account's station. Skip it unless you want the public map.

Required query: `lat_ne`, `lon_ne`, `lat_sw`, `lon_sw`. Optional: `required_data` (`temperature`, `pressure`, `humidity`, `rain`, `wind`), `filter` (default false).

### homestatus

```
GET https://api.netatmo.com/api/homestatus?home_id=HOME_ID
```

Do not call this with only `read_station`.

The weather page says station data can come from `getstationsdata` (cloud, about every 10 minutes) or `homestatus` (near real time, under 10 seconds). The data table on that page still points each measurement at `getstationsdata`. The OpenAPI files that actually define `homestatus` require other scopes:

- [Energy](https://dev.netatmo.com/apidocumentation/energy): scope `read_thermostat`. Required query `home_id`. Optional `device_types`: `NAPlug`, `OTH`, `BNS`. Those are thermostat gateways, not `NAMain`.
- [Home + Security](https://dev.netatmo.com/apidocumentation/security): camera, presence, doorbell, smoke, and related scopes. Not `read_station`.

`read_thermostat` is for thermostats. Do not request it for the weather station.

`homesdata` is the same kind of mismatch. The weather page names it for "owned / friend / favorite". The Energy OpenAPI requires `read_thermostat`. The Security OpenAPI requires camera and related scopes. It is not a `read_station` call.

`gethomecoachsdata` is the Home Coach (aircare) call, scope `read_homecoach`. That is a different product.

For this station, call `getstationsdata` and, for history, `getmeasure`.

## 7. Rate limits

From the [guidelines](https://dev.netatmo.com/guideline). Two caps apply at once.

Per user (this account):

- 50 requests every 10 seconds
- 500 requests every hour

Per application, every 10 seconds: `(2 * number of users in limit of 200)` requests.

Per application, every hour, by how many users the app has:

- under 500 users: 2000
- more than 500: 10000
- more than 1500: 30000
- more than 5000: 100000
- more than 20000: 400000
- more than 60000: 1200000
- more than 80000: 1600000

For this one account, the per-user cap is the tight one: 50 every 10 seconds, and 500 every hour. A station poll every few minutes stays far under that. `getstationsdata` is a cloud copy that the weather page says moves about every 10 minutes, so polling faster than that does not get newer cloud data.

Over the limit, the API returns HTTP 429. The [glossary](https://dev.netatmo.com/apidocumentation/general) says a `Retry-After` header may be set. The JSON error `code` is:

- `26` — API limit exceeded (application limit or user limit)
- `28` — rate limit exceeded; slow down

Wait, then retry. Do not retry in a tight loop.

## 8. HTTPS from the ESP32-C6

Yes. ESP-IDF `esp_http_client` with mbedTLS is enough.

`api.netatmo.com` accepts TLS 1.2 and TLS 1.3. Checked 2026-11-12: the certificate is `CN=api.netatmo.com`, issued by GeoTrust TLS RSA CA G1, which chains to DigiCert Global Root G2. That root is in the ESP-IDF v5.5.6 certificate bundle (`components/mbedtls/esp_crt_bundle`).

In ESP-IDF v5.5.6, `esp_http_client` does HTTPS through mbedTLS when the URL starts with `https://`. `CONFIG_ESP_HTTP_CLIENT_ENABLE_HTTPS` is on by default. Set `crt_bundle_attach` to `esp_crt_bundle_attach` so the bundle verifies the server. No other TLS stack is required.

Doc: [esp_http_client](https://docs.espressif.com/projects/esp-idf/en/v5.5.6/esp32c6/api-reference/protocols/esp_http_client.html).

## 9. Zigbee and Wi-Fi on the one radio

The ESP32-C6 has one 2.4 GHz radio, shared by Wi-Fi and 802.15.4. A Zigbee coordinator and a Wi-Fi STA can coexist. ESP-IDF software coexistence time-slices that radio: enable `CONFIG_ESP_COEX_SW_COEXIST_ENABLE` (on by default for the C6 in the Zigbee gateway example) and call `esp_coex_wifi_i154_enable()` before the STA connects. The IDF v5.5.6 Zigbee gateway example does that, connects as a Wi-Fi STA, sets `WIFI_PS_MIN_MODEM`, then forms the Zigbee network. Espressif's table marks Wi-Fi STA connected plus a Zigbee router as C1: supported, but unstable, because a router has to keep receiving and the radio cannot receive Wi-Fi and 802.15.4 at the same time. A coordinator is that router case. An end device is the case they mark stable. They recommend two chips for a gateway product.

Docs: [RF coexistence](https://docs.espressif.com/projects/esp-idf/en/v5.5.6/esp32c6/api-guides/coexist.html) and the [Zigbee gateway example](https://github.com/espressif/esp-idf/blob/v5.5.6/examples/zigbee/esp_zigbee_gateway/README.md).
