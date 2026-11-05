# Home Assistant setup: current state and how to pick it back up

Copyright (c) 2026 Al Ruiz. All rights reserved.

Snapshot as of 2026-11-05 of the live system described in
[SOMFY_WIND_SETUP.md](SOMFY_WIND_SETUP.md). Read this first when coming back to
the project. No passwords are stored here; they live only in Home Assistant,
ESPSomfy and the OpenMQTTGateway portal.
This GitHub repository is public, so the home's latitude/longitude appear as
`LAT`/`LON` placeholders; the real values are in HA (Settings -> System -> General).

## Machines and addresses

| What | Address | Notes |
|---|---|---|
| Home Assistant OS (VirtualBox VM on the PC) | <http://homeassistant.local> | Browser access by IP or `:8123` can be refused; use the `.local` name. The PC must stay on. |
| Board 1: ESPSomfy-RTS shade controller | 192.168.1.38 | Online. Shade movement not retested after the module reseat; shades may need physical re-pairing. |
| Board 2: weather receiver (new ESP32, MAC ends `bc:ac`) | 192.168.1.64 | OpenMQTTGateway built from `~/omg-build` with this library; decodes the AcuRite 5n1 (id 364) and the second AcuRite sensor. Reserve this IP in the router (still to do). |
| Old ESP32 (MAC ends `d6:48`) | - | Faulty (`pulses: 0`). Do not reuse. |
| TP-Link Kasa HS220 dimmer | 192.168.1.22 | Discovered by HA; press **Add** under Settings -> Devices & services to finish. |

Backup plan for the receiver: a Nooelec NESDR Mini (RTL-SDR) with `rtl_433`.
Only set it up if Board 2 fails again.

## Home Assistant configuration

Files on the HA box (edit with the **File editor** app, or over Samba below):

- `/homeassistant/configuration.yaml` ends with `rest: !include weather_rest.yaml`.
- `/homeassistant/weather_rest.yaml` = [contrib/home-assistant/weather_rest.yaml](../contrib/home-assistant/weather_rest.yaml):
  NWS alerts (`sensor.nws_alert_count`, `sensor.nws_alerts`,
  `sensor.nws_alert_headline`) and Open-Meteo air quality
  (`sensor.air_quality_index`, `sensor.pm2_5`, `sensor.ozone`). Loaded and live
  since the 2026-11-03 restart. Changes to it need a full HA restart.
- Automations: [contrib/home-assistant/shade_automations.yaml](../contrib/home-assistant/shade_automations.yaml).
  All push alerts are on (5n1 battery/no data, board offline, no readings 30 min).

Set up through the UI (not in YAML):

- **SQL integration** -> `sensor.wind_direction_history`, query in
  [contrib/home-assistant/wind_direction_history.sql](../contrib/home-assistant/wind_direction_history.sql).
- **NWS weather** -> `weather.nws_LAT_LON_kapa` (forecast, visibility).
- **MQTT** (Mosquitto broker app) for both boards. Board 2's connectivity entity
  is `binary_sensor.omg_rtl_433_esp_sys_connectivity`.

Apps (add-ons) installed: Mosquitto broker, File editor. There is no HACS, so
dashboards use built-in cards only.

## Dashboards

| Dashboard | Path | Contents |
|---|---|---|
| Weather & Shades | default | Weather only now (see below) |
| Shades | `/dashboard-shades` | Shade controls |
| Hardware | `/dashboard-hardware` | Board status, battery, signal |

Weather dashboard, top to bottom:

1. **Right now**: NWS alert banner (only when an alert is active), thermometer,
   humidity gauge, entities card (Feels like, Dew point, Snow, AQI, PM2.5,
   Ozone, NWS alerts, Visibility), wind compass.
2. Forecast.
3. Barometer, then Sun & sky.
4. Rain & lightning.
5. Wind direction over the last 6 hours (dot timeline coloured by speed, plus a
   wind rose), then separate 6-hour wind speed and 6-hour temperature graphs.
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
- Reserve 192.168.1.64 (Board 2) in the router.
- Watchdog/auto-restart plan for the HA VM, Mosquitto and the PC (e.g. HASS.Agent).
- Xcel electric meter: no ready-made HA integration found yet.
- Samba share (above), if wanted.

## Checking the contrib files

```bash
python tools/check_home_assistant_config.py
```

This parses every YAML file in `contrib/home-assistant` and runs
`wind_direction_history.sql` against a small in-memory copy of the recorder
schema to confirm the `samples` format the dashboard expects.
