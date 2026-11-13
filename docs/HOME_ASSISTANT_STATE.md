# Home Assistant setup: current state and how to pick it back up

Copyright (c) 2026 Al Ruiz. All rights reserved.

Snapshot as of 2026-11-12 of the live system described in
[SOMFY_WIND_SETUP.md](SOMFY_WIND_SETUP.md). Read this first when coming back to
the project. No passwords are stored here; they live only in Home Assistant,
ESPSomfy and the OpenMQTTGateway portal.
This GitHub repository is public, so the home's latitude/longitude appear as
`LAT`/`LON` placeholders; the real values are in HA (Settings -> System -> General).

## Rules: read before changing anything

### Do not rename things

**Never rename entities, devices, automations, dashboards, MQTT topics or
shades.** Automations, dashboard cards, the SQL sensors and the files in
`contrib/home-assistant` all refer to things by their exact ID, for example
`sensor.acurite_5n1_c_364_wind_average`, `cover.somfy_shades_living_room_shade`,
`somfy/shades/3/direction/set` and `/dashboard-hardware`. A rename does not
update those references: the wind, rain and heat shade protection silently
stops working, and cards show "unavailable" or errors.

- Do not rename in Settings -> Devices & services, Settings -> Entities, the
  ESPSomfy web page (shade names and IDs), or the OpenMQTTGateway portal
  (gateway name `OMG_rtl_433_ESP`, MQTT base topic).
- Do not use "Recreate entity IDs" or let HA rename entities when a device is
  re-added. If a device has to be removed and re-added, make sure every entity
  ID comes back exactly as before.
- Automation entity IDs never change when their display name changes, so they
  can lag behind: `automation.wind_4_mph_raise_all_shades` is the entity of the
  "Wind > 8 mph" rule. Leave it as is; the Shades dashboard uses that ID.
- If something truly must be renamed, search this repo and every dashboard's
  raw configuration for the old ID and change them all in the same sitting.

### Updates: what not to upgrade

| Update | What to do |
|---|---|
| Board 2 (weather receiver) OpenMQTTGateway firmware | **Never update** from the OMG web page or over the air. It is a custom build from `~/omg-build` with this library and the CC1101/AcuRite settings; a stock OMG image removes AcuRite decoding. Only rebuild from `~/omg-build`. |
| Board 1 ESPSomfy-RTS firmware (v2.4.6) | **Do not update** unless a fix is needed. Shade pairing and rolling codes live on the board; first download a backup from the ESPSomfy web page (Settings -> Backup). |
| Home Assistant OS / Core / Supervisor | Safe after a backup (Settings -> System -> Backups -> Backup now). Prefer patch releases (x.y.**1**); for a new monthly release (x.**y**.0) wait about a week and read the release notes' "Backward-incompatible changes" for MQTT, SQL, REST, System Monitor and template. Restart HA only when nobody depends on the shades. |
| Apps (add-ons): Mosquitto broker, File editor, Matter Server | Safe after a backup. Read the Mosquitto changelog first: a broken broker stops both boards. |
| AcuRite sensors, Kasa, printer | Nothing to update from HA. |

As of 2026-11-12 the pending updates are Home Assistant Core 2026.11.0 ->
2026.11.1 (bug-fix release) and File editor 6.3.0 -> 6.3.1. Both are fine to
install after a backup.

## Machines and addresses

Use the `.local` names below instead of IP addresses; they keep working when the
router changes a board's IP. Home Assistant itself talks to both boards through
the MQTT broker, so a board IP change never breaks the shades or the weather data.

Both boards connect to the MQTT broker at **192.168.1.60**, so Home Assistant's
address must never change. It is set twice: static IPv4 in HA (Settings ->
System -> Network) and an Address Reservation in the router (Setup -> LAN Setup)
for MAC `08:00:27:4D:8D:FD`.

Router Address Reservations (Setup -> LAN Setup):

| IP | Device name | MAC |
|---|---|---|
| 192.168.1.47 | esp32-5FBCAC (Board 2, weather receiver) | `68:09:47:5F:BC:AC` |
| 192.168.1.38 | ESPSomfyRTS (Board 1, shades) | `8C:94:DF:6E:41:B0` |
| 192.168.1.60 | Home Assistant VM | `08:00:27:4D:8D:FD` |

If a board is ever replaced, update its reservation to the new board's MAC
(the old weather board's reservation was left on the dead ESP32 for weeks, so
the new board kept changing IP). Restart Board 2 from HA without unplugging it:
Developer tools -> Actions -> `mqtt.publish`, topic
`home/OMG_rtl_433_ESP/commands/MQTTtoSYS/config`, payload `{"cmd":"restart"}`.

| What | Address | Notes |
|---|---|---|
| Home Assistant OS (VirtualBox VM on the PC) | <http://homeassistant.local> = 192.168.1.60 (static in HA and reserved in the router) | Browser access by IP or `:8123` can be refused; use the `.local` name. The PC must stay on. |
| Board 1: ESPSomfy-RTS shade controller | <http://ESPSomfyRTS.local> = 192.168.1.38 (reserved in the router) | Online. Shade movement not retested after the module reseat; shades may need physical re-pairing. |
| Board 2: weather receiver (new ESP32, MAC ends `bc:ac`) | <http://OMG_rtl_433_ESP.local> = 192.168.1.47 (reserved in the router since 2026-11-12) | OpenMQTTGateway built from `~/omg-build` with this library; decodes the AcuRite 5n1 (id 364), lightning detector (6045M id 183) and rain gauge (Rain899 id 728). The page asks for the OMG portal login. |
| Old ESP32 (MAC ends `d6:48`) | - | Faulty (`pulses: 0`). Do not reuse. |
| TP-Link Kasa HS220 dimmer | 192.168.1.22 | Discovered by HA; press **Add** under Settings -> Devices & services to finish. |

Backup plan for the receiver: a Nooelec NESDR Mini (RTL-SDR) with `rtl_433`.
Only set it up if Board 2 fails again.

## Home Assistant configuration

Files on the HA box (edit with the **File editor** app, or over Samba below):

- `/homeassistant/configuration.yaml` ends with `rest: !include weather_rest.yaml`
  and `command_line: !include shade_board_sensors.yaml`.
- `/homeassistant/shade_board_sensors.yaml` = [contrib/home-assistant/shade_board_sensors.yaml](../contrib/home-assistant/shade_board_sensors.yaml)
  and `/homeassistant/espsomfy_stats.py` = [contrib/home-assistant/espsomfy_stats.py](../contrib/home-assistant/espsomfy_stats.py):
  the shade board's Wi-Fi signal (`sensor.shade_board_wi_fi_signal`) and free
  memory (`sensor.shade_board_free_memory`), read every minute from the
  websocket the ESPSomfy web page uses (the board publishes them nowhere else).
  `weather_rest.yaml` also reads its firmware version and whether an update
  exists (`sensor.shade_board_firmware`). ESPSomfy-RTS has no temperature or
  uptime reading.
- `weather_rest.yaml` also holds the 14-day freeze forecast
  (`sensor.freeze_forecast_14_days`, Open-Meteo hourly temperature, refreshed
  once a day; NWS only forecasts about 7 days). If a fetch fails, the
  automation in [contrib/home-assistant/information_automations.yaml](../contrib/home-assistant/information_automations.yaml)
  retries every 15 minutes until it has data.
- `weather_rest.yaml` also holds hourly snowfall in inches for the past 7 days
  and the next 14 (`sensor.snowfall_past_7_and_next_14_days`, Open-Meteo,
  refreshed once a day, same retry automation). The past 7 days are Open-Meteo's
  estimate for this location: the weather station has no snow gauge.
- `weather_rest.yaml` also holds `sensor.snowfall_history_365_days` (Open-Meteo
  archive, daily snowfall for the past year, refreshed once a day, same retry
  automation) so "Last snowfall" works even when it was months ago.
- `/homeassistant/weather_rest.yaml` = [contrib/home-assistant/weather_rest.yaml](../contrib/home-assistant/weather_rest.yaml):
  NWS alerts (`sensor.nws_alert_count`, `sensor.nws_alerts`,
  `sensor.nws_alert_headline`) and Open-Meteo air quality
  (`sensor.air_quality_index`, `sensor.pm2_5`, `sensor.ozone`). Loaded and live
  since the 2026-11-03 restart. After editing it, reload with Developer tools
  -> YAML -> **REST entities and notify services** (no restart needed). With no
  active alerts the alert sensors read `No alerts`.
- Automations: [contrib/home-assistant/shade_automations.yaml](../contrib/home-assistant/shade_automations.yaml).
  All push alerts are on (5n1 battery/no data, board offline, no readings 30 min).
  Shade rules as of 2026-11-12: raise all shades when the wind average is above
  8 mph, on rain, and 1 hour before sunset; lower only when the wind is below
  4 mph and it has been dry 30 minutes (all shades above 80 F in daylight; the
  living room shade, ESPSomfy id 3, every 30 minutes from noon to 4 pm when NWS
  says sunny).

Set up through the UI (not in YAML):

- **SQL integration** -> `sensor.wind_direction_history`, query in
  [contrib/home-assistant/wind_direction_history.sql](../contrib/home-assistant/wind_direction_history.sql).
- **SQL integration** -> `sensor.freezing_last_7_days` (state = times the
  outdoor temperature reached 32 F or below in the last 7 days, attribute
  `freeze_minutes` = total minutes, `last_freeze_start` = unix time the last
  freezing stretch began, `last_freeze_ever` = last time at or below 32 F in all
  recorded history including HA's hourly long-term statistics,
  `history_since` = when that history starts, 2026-10-19), query in
  [contrib/home-assistant/freeze_last_7_days.sql](../contrib/home-assistant/freeze_last_7_days.sql).
  HA's SQL form requires the query to start with `SELECT`.
- **NWS weather** -> `weather.nws_LAT_LON_kapa` (forecast, visibility).
- **System Monitor** (added 2026-11-12) for the HA VM. Enabled sensors:
  `sensor.system_monitor_processor_use`, `_memory_usage`, `_memory_use`,
  `_disk_usage`, `_swap_usage`, `_load_15_min`, `_uptime` (boot time),
  `_network_throughput_in_enp0s3`, `_network_throughput_out_enp0s3`. The VM has
  no processor temperature sensor.
- **MQTT** (Mosquitto broker app) for both boards. Board 2's connectivity entity
  is `binary_sensor.omg_rtl_433_esp_sys_connectivity`.

Apps (add-ons) installed: Mosquitto broker, File editor. There is no HACS, so
dashboards use built-in cards only.

## Dashboards

| Dashboard | Path | Contents |
|---|---|---|
| Weather & Shades | default | Weather only now (see below) |
| Shades | `/dashboard-shades` | Shade controls |
| Hardware | `/dashboard-hardware` | Shade board signal, free memory and firmware; chip temperatures (weather board ESP32, PC graphics card, PC motherboard), uptime as yrs:mos:wks:days:hh:mm:ss (weather board, PC, HA machine), HA machine CPU/memory/disk/network, sensor batteries and signal, PC load and disk space |
| Information | `/dashboard-information` | Freezing temperatures in the last 7 days (how many times it reached 32 F or below, total time, and the last time it was at or below 32 F in all recorded history) the freeze forecast for today and the next 14 days (dates, hours and lows), and snowfall for the last 7 days (count, total, amounts by day, and the last snowfall even if it was months ago) and the next 14 days (dates, hours, amounts). Config in [contrib/home-assistant/information_dashboard.yaml](../contrib/home-assistant/information_dashboard.yaml). |

Weather dashboard, top to bottom:

1. **Right now**: NWS alert banner (only when an alert is active), thermometer,
   humidity gauge, entities card (Feels like, Dew point, Snow, AQI, PM2.5,
   Ozone, NWS alerts, Visibility), wind compass.
2. Forecast.
3. Barometer, then Sun & sky.
4. Rain & lightning.
5. Wind direction over the last 6 hours (dot timeline coloured by speed, plus a
   wind rose; colours: green under 4 mph, orange 4 to 8 mph, red over 8 mph,
  matching the shade rules), then separate 6-hour wind speed and 6-hour temperature graphs.
   There is deliberately **no** combined wind + temperature graph.

The cards added on 2026-11-03 are in
[contrib/home-assistant/weather_dashboard_cards.yaml](../contrib/home-assistant/weather_dashboard_cards.yaml).

How the custom graphics work: they are markdown cards whose Jinja template
builds an SVG and shows it as a `data:image/svg+xml` `<img>`. Home Assistant
strips raw `<svg>` and inline styles from markdown, so the data-URI image is
required.

Editing tips:

- Edit a sections dashboard with three dots -> Edit dashboard -> three dots ->
  Raw configuration editor. HA re-wraps long lines on save, so keep the card
  templates in the contrib file and paste from there rather than editing the
  re-wrapped copy.
- Test templates first in Developer tools -> Template.
- HA backup named "Before weather dashboard update" (id `ca439d58`) predates
  the dashboard rework.

## Seeing the HA files from Windows (network share)

1. In HA: Settings -> Apps -> App store -> **Samba share** -> Install. On its
   Configuration tab set a username and password, save, then Start (turn on
   Start on boot).
2. On the PC: make the network profile **Private** and turn on **Network
   discovery** (Settings -> Network & internet -> Advanced sharing settings).
3. File Explorer -> Network -> **HOMEASSISTANT**, or type
   `\\homeassistant.local` in the address bar. Map `\\homeassistant.local\config`
   as a drive with Reconnect at sign-in.

Not installed yet as of this snapshot.

## Open items

- Weather dashboard: further regrouping/reordering if wanted (current order is above).
- Shades: retest movement; physical re-pairing may be needed. Offer of
  `repeats=2` for ESPSomfy commands is awaiting a decision.
- Vendor integrations requested (Kasa/Tapo, Alexa thermostat, B-hyve, Smart
  Life/Treatlife (Tuya), JellyFish, VeSync, Modern Forms): each needs the
  owner's own vendor sign-in in Settings -> Devices & services. "Revolo" and
  "smart control" still need clarifying.
- Watchdog/auto-restart plan for the HA VM, Mosquitto and the PC (e.g. HASS.Agent).
- Xcel electric meter: no ready-made HA integration found yet.
- Samba share (above), if wanted.

## Checking the contrib files

```bash
python tools/check_home_assistant_config.py
```

This parses every YAML file in `contrib/home-assistant`, checks the shade rule
thresholds and sunset offset, and runs `wind_direction_history.sql` and
`freeze_last_7_days.sql` against a small in-memory copy of the recorder schema.
