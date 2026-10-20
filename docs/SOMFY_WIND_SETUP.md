# Somfy RTS shade control + AcuRite wind protection

Copyright (c) 2026 Al Ruiz. All rights reserved.

A low-cost, local-only setup that receives live weather from an AcuRite 5-in-1
sensor and automatically moves four Somfy RTS shades to protect them (wind,
rain, sunset, heat). It uses two ESP32 + CC1101 boards and Home Assistant.

```text
AcuRite 5n1 --433.92 MHz--> Board 2: ESP32+CC1101 (OpenMQTTGateway + rtl_433_ESP)
                                        | MQTT
                                        v
                          Home Assistant + Mosquitto  --MQTT-->  Board 1: ESP32+CC1101
                          (automations, phone push)              (ESPSomfy-RTS) --433.42 MHz--> 4 Somfy shades
```

This is documentation for a downstream setup built on this repository's
`rtl_433_ESP` library. The upstream project is unchanged; the only code change
is the extra `esp32_cc1101_acurite` PlatformIO environment in
`examples/OOK_Receiver/platformio.ini`.

## Hardware

Two identical boards:

- 1 x classic ESP32 DevKit (dual core)
- 1 x CC1101 433 MHz module with SMA antenna
- Jumper wires, USB data cable

The AcuRite Iris / 5-in-1 sensor, and a computer to run Home Assistant.

### Wiring (both boards)

| CC1101 | ESP32 | Notes |
|---|---|---|
| VCC | 3.3V | Never 5V |
| GND | GND | |
| SCK | GPIO 18 | |
| MOSI | GPIO 23 | |
| MISO | GPIO 19 | |
| CSN / CS | GPIO 5 | |
| GDO0 | GPIO 4 | Important |
| Antenna | SMA | Attach firmly; keep SPI wires short |

## Board 1: ESPSomfy-RTS (shade controller)

1. Flash `SomfyController.onboard.esp32.bin` from
   <https://github.com/rstrouse/ESPSomfy-RTS/releases> using
   <https://web.esphome.io>.
2. Join the `ESPSomfy-RTS` Wi-Fi network, open `http://192.168.4.1`, and give it
   your home Wi-Fi.
3. Radio settings: CSN 5, GDO0 4, SCK 18, MOSI 23, MISO 19, RX pin 4, TX pin 4,
   frequency 433.42 MHz. Save and restart.
4. Add each shade (Shades -> Add / Link remote) and press the physical remote.
5. **Network -> MQTT:** enable the MQTT client, host = your Home Assistant
   address, port 1883, the MQTT user, **root topic `somfy`**. Commands are then
   published to `somfy/shades/<id>/direction/set` (`-1` up, `1` down, `0` stop).

ESPSomfy allows only about five simultaneous browser connections. If the UI says
"too many clients", close other tabs. The REST API (`/controller`, `/shades`)
still works.

## Board 2: weather receiver

Verify reception first with the example in this repo:

```bash
cd examples/OOK_Receiver
pio run -e esp32_cc1101_acurite -t upload --upload-port COMx
```

The serial monitor (921600 baud) should show decoded JSON such as
`"model":"Acurite-5n1"` with `wind_avg_km_h` and `wind_dir_deg`.

For Home Assistant integration use
[OpenMQTTGateway](https://github.com/1technophile/OpenMQTTGateway) with its
`rtl_433` module. **The prebuilt `esp32dev-rtl_433` binary expects GDO0 on
GPIO 12 and GDO2 on GPIO 27, which does not match the wiring above.** Build it
yourself with our pins (no rewiring needed):

1. Clone OpenMQTTGateway (tested with v1.8.1).
2. In `environments.ini`, section `[env:esp32dev-rtl_433]`, change
   `-DRF_MODULE_GDO0=12` and `-DRF_MODULE_GDO2=27` to `-DRF_MODULE_GDO0=4` and
   `-DRF_MODULE_GDO2=4`.
3. `pio run -e esp32dev-rtl_433 -t upload --upload-port COMx`.
4. Join the `OMG_rtl_433_ESP` Wi-Fi network (password `OMGSecured`), choose
   *Configure WiFi*, and enter your Wi-Fi plus the MQTT server (Home Assistant),
   port 1883, and the MQTT user and password.
5. The OMG web UI login is user `admin` and the gateway password (default `OMGSecured` if the portal does not ask). If the board reaches Wi-Fi but Home Assistant shows it unavailable, MQTT auth failed: re-enter the MQTT user/password under Configuration -> MQTT. To reset it,
   erase flash (`pio run -t erase`) and reflash.

Home Assistant then discovers the sensors automatically
(e.g. `sensor.acurite_5n1_c_364_wind_average`, `_temperature`, `_rain`,
`binary_sensor.acurite_5n1_c_364_battery`).

## Home Assistant

- Home Assistant OS in a VirtualBox VM (bridged adapter) with the Mosquitto
  broker add-on, or any Home Assistant install on an always-on machine.
- Create a dedicated Home Assistant user (e.g. `mqtt`) for the broker; use it in
  ESPSomfy and OpenMQTTGateway.
- Install the Home Assistant Companion app on your phone for push alerts.

Automations are in
[contrib/home-assistant/shade_automations.yaml](../contrib/home-assistant/shade_automations.yaml):

| Rule | Trigger | Action |
|---|---|---|
| Wind | wind average rises above 4 mph | raise all shades |
| Rain | 5n1 rain total increases (max once an hour) | raise all shades, push "It's raining" |
| Sunset | sunset | raise all shades |
| Heat | temperature crosses above 80 F, in daylight, wind at or below 4 mph, no rain for 30 min | lower all shades |
| Sensor health | 5n1 battery low, or no signal for 2 hours | push alert |
| Board offline | weather receiver or Somfy controller offline 5 min (and back online) | push alert |

Notes: the heat rule fires on the crossing only and does not lower again after
wind or rain clears. The AcuRite 5n1 does not report cloud cover; use a Home
Assistant weather integration if you need it.

## Gotchas

- **Wi-Fi VM bridging is unreliable.** Bridge the VM to a wired adapter. After
  changing the host's network, re-attach the VM adapter if it drops off the LAN.
- **The host must stay on.** Automations run in Home Assistant, so a sleeping PC
  disables the protection.
- Reserve fixed IPs (DHCP reservations) for Home Assistant and both ESP boards.
  Prefer an IP over `homeassistant.local` on the ESP boards, which often cannot
  resolve mDNS names.
- ESPSomfy's Home Assistant auto-discovery covers may be rejected on some
  versions; the automations avoid this by publishing MQTT commands directly.
- The `notify.mobile_app_<name>` slug drops punctuation from the device name
  (`Al's iPhone` becomes `mobile_app_als_iphone`).
- Windows Smart App Control can block freshly built unsigned tools.

## Verifying

```bash
cd examples/OOK_Receiver
pio run -e esp32_cc1101_acurite        # builds the receiver firmware
python -c "import yaml,sys; yaml.safe_load(open('../../contrib/home-assistant/shade_automations.yaml'))"
```

Then confirm in Home Assistant that the wind sensor updates, and publish
`1` then `-1` to `somfy/shades/1/direction/set` to watch a shade move.
