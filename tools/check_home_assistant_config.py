#!/usr/bin/env python3
# Copyright (c) 2026 Al Ruiz. All rights reserved.
"""Checks the Home Assistant files in contrib/home-assistant.

* Every .yaml file parses (HA's !include style tags are accepted).
* weather_rest.yaml defines the sensors the Weather dashboard uses.
* shade_automations.yaml raises shades above 8 mph, lowers only below 4 mph, and
  lowers the living room shade (id 3) when sunny, every 30 min between noon and 4 pm.
* espsomfy_stats.py reads the shade board's Wi-Fi signal and memory.
* freeze_last_7_days.sql counts dips to 32 F or below and their minutes.
* wind_direction_history.sql runs against a minimal recorder schema and returns
  samples as "bucket:direction:max_mph,...", only for the last 6 hours.

Run: python tools/check_home_assistant_config.py   (needs PyYAML)
"""

import pathlib
import sqlite3
import sys
import time

import yaml

HA_DIR = pathlib.Path(__file__).resolve().parent.parent / "contrib" / "home-assistant"


class _Loader(yaml.SafeLoader):
    pass


_Loader.add_multi_constructor("!", lambda loader, suffix, node: None)


def check_yaml():
    for path in sorted(HA_DIR.glob("*.yaml")):
        with open(path, encoding="utf-8") as f:
            yaml.load(f, Loader=_Loader)
        print(f"ok  {path.name} parses")


def check_rest_sensors():
    with open(HA_DIR / "weather_rest.yaml", encoding="utf-8") as f:
        feeds = yaml.load(f, Loader=_Loader)
    ids = {s["unique_id"] for feed in feeds for s in feed["sensor"]}
    want = {"nws_alert_count", "nws_alert_events", "nws_alert_headline",
            "open_meteo_us_aqi", "open_meteo_pm25", "open_meteo_ozone",
            "shade_board_firmware", "freeze_forecast_14_days",
            "snowfall_past_7_next_14", "snowfall_history_365_days"}
    assert want <= ids, f"missing REST sensors: {want - ids}"
    for feed in feeds:
        feed.setdefault("resource", feed.get("resource_template", ""))
        local = feed["resource"].startswith("http://192.168.1.")
        assert local or feed["resource"].startswith("https://"), feed["resource"]
    text = (HA_DIR / "weather_rest.yaml").read_text(encoding="utf-8")
    assert "'None'" not in text, "use 'No alerts': HA shows 'None' as unknown"
    print("ok  weather_rest.yaml defines all dashboard sensors")


def check_shade_automations():
    with open(HA_DIR / "shade_automations.yaml", encoding="utf-8") as f:
        autos = {a["alias"]: a for a in yaml.load(f, Loader=_Loader)}
    wind = autos["Wind > 8 mph: raise all shades"]
    assert wind["triggers"][0]["above"] == 8, wind["triggers"]
    heat = autos["Heat 80F+: lower all shades"]
    assert any("< 4" in c.get("value_template", "") for c in heat["conditions"])
    sun = autos["Sunny noon to 4 pm: lower living room shade"]
    assert sun["triggers"] == [{"trigger": "time_pattern", "minutes": "/30"}]
    conds = sun["conditions"]
    assert {"condition": "time", "after": "12:00:00", "before": "16:00:00"} in conds
    assert any(c.get("state") == "sunny" for c in conds), conds
    assert any("< 4" in c.get("value_template", "") for c in conds), conds
    assert sun["actions"] == [{"action": "mqtt.publish", "data": {
        "topic": "somfy/shades/3/direction/set", "payload": "1"}}], sun["actions"]
    sunset = autos["1 hour before sunset: raise all shades"]
    assert sunset["triggers"] == [{"trigger": "sun", "event": "sunset",
                                   "offset": "-01:00:00"}], sunset["triggers"]
    print("ok  shade_automations.yaml: sunset -1 h, raise > 8 mph, lower only < 4 mph, sunny rule")


def check_sql():
    db = sqlite3.connect(":memory:")
    db.executescript(
        "CREATE TABLE states_meta (metadata_id INTEGER PRIMARY KEY, entity_id TEXT);"
        "CREATE TABLE states (state TEXT, last_updated_ts REAL, metadata_id INTEGER);"
        "INSERT INTO states_meta VALUES (1, 'sensor.acurite_5n1_c_364_wind_direction'),"
        " (2, 'sensor.acurite_5n1_c_364_wind_average');")
    now = time.time()
    t = (int(now) // 300 - 1) * 300 + 10  # inside the previous 5-minute bucket
    rows = [
        ("270.0", t, 1), ("3.5", t, 2), ("6.0", t + 30, 2),
        ("90.0", now - 3600, 1),  # no matching speed -> empty speed field
        ("unavailable", now - 120, 1),  # ignored: not numeric
        ("180.0", now - 8 * 3600, 1),  # ignored: older than 6 hours
    ]
    db.executemany("INSERT INTO states VALUES (?, ?, ?)", rows)
    sql = (HA_DIR / "wind_direction_history.sql").read_text(encoding="utf-8")
    sql = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))
    points, samples = db.execute(sql).fetchone()
    parts = sorted(samples.split(","))
    assert points == 2, (points, samples)
    got = sorted((p.split(":")[1], p.split(":")[2]) for p in parts)
    assert got == [("270.0", "6.0"), ("90.0", "")], samples
    for p in parts:
        bucket = int(p.split(":")[0])
        assert abs(bucket - now / 300) < 13, p
    print(f"ok  wind_direction_history.sql -> {points} points: {samples}")


def check_freeze_sql():
    db = sqlite3.connect(":memory:")
    db.executescript(
        "CREATE TABLE states_meta (metadata_id INTEGER PRIMARY KEY, entity_id TEXT);"
        "CREATE TABLE states (state TEXT, last_updated_ts REAL, metadata_id INTEGER);"
        "CREATE TABLE statistics_meta (id INTEGER PRIMARY KEY, statistic_id TEXT);"
        "CREATE TABLE statistics (metadata_id INTEGER, start_ts REAL, min REAL);"
        "INSERT INTO statistics_meta VALUES (1, 'sensor.acurite_5n1_c_364_temperature');"
        "INSERT INTO states_meta VALUES (1, 'sensor.acurite_5n1_c_364_temperature'),"
        " (2, 'sensor.other');")
    now = int(time.time())
    h = 3600
    rows = [
        ("20.0", now - 9 * 24 * h, 1),   # older than 7 days: ignored
        ("31.0", now - 6 * 24 * h, 1),   # freeze 1 starts (counts at window start)
        ("33.0", now - 6 * 24 * h + h, 1),  # ends after 60 min
        ("32.0", now - 3 * 24 * h, 1),   # freeze 2: exactly 32 counts
        ("unavailable", now - 3 * 24 * h + 30 * 60, 1),  # ends stretch after 30 min
        ("30.5", now - 3 * 24 * h + 40 * 60, 1),  # same dip resumes: not a new time
        ("40.0", now - 3 * 24 * h + 50 * 60, 1),  # +10 min
        ("-2.0", now - 10 * h, 1),       # freeze 3, negative value
        ("45.0", now - 10 * h + 5 * h, 1),  # gap capped at 3 h = 180 min
        ("10.0", now - h, 2),            # other entity: ignored
    ]
    db.executemany("INSERT INTO states VALUES (?, ?, ?)", rows)
    sql = (HA_DIR / "freeze_last_7_days.sql").read_text(encoding="utf-8")
    sql = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))
    db.executemany("INSERT INTO statistics VALUES (1, ?, ?)",
                   [(now - 300 * 24 * h, 40.0), (now - 200 * 24 * h, 25.0),
                    (now - 100 * 24 * h, 50.0)])
    count, minutes, last, ever, since = db.execute(sql).fetchone()
    assert (count, minutes) == (3, 60 + 30 + 10 + 180), (count, minutes)
    assert last == now - 10 * h, (last, now - 10 * h)
    assert ever == now - 10 * h, ever  # the latest freezing state reading
    assert since == now - 300 * 24 * h, since
    db.execute("DELETE FROM states")
    count, minutes, last, ever, since = db.execute(sql).fetchone()
    assert (count, minutes, last) == (0, 0, None), (count, minutes, last)
    assert ever == now - 200 * 24 * h, ever  # falls back to long-term statistics
    print(f"ok  freeze_last_7_days.sql -> {count} times, {minutes} min on empty data; test data ok")


def check_espsomfy_stats():
    """Run espsomfy_stats.py against a fake ESPSomfy websocket server."""
    import importlib.util
    import json
    import socket
    import struct
    import threading

    spec = importlib.util.spec_from_file_location(
        "espsomfy_stats", HA_DIR / "espsomfy_stats.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    def frame(text):
        data = text.encode()
        if len(data) < 126:
            return bytes([0x81, len(data)]) + data
        return bytes([0x81, 126]) + struct.pack(">H", len(data)) + data

    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def serve():
        conn, _ = srv.accept()
        req = b""
        while b"\r\n\r\n" not in req:
            req += conn.recv(1024)
        conn.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                     b"Connection: Upgrade\r\n\r\n")
        conn.sendall(frame("42[shadeState," + json.dumps({"name": "x" * 200}) + "]"))
        conn.sendall(frame('42[wifiStrength,{"ssid":"s","strength":-16,"channel":6}]'))
        conn.sendall(frame('42[memStatus,{"max":110580,"free":151600,"min":105412,"total":259828}]'))
        conn.close()

    threading.Thread(target=serve, daemon=True).start()
    # collect() connects to port 8080; patch it to the test port.
    orig = mod.socket.create_connection
    mod.socket.create_connection = lambda addr, timeout: orig(("127.0.0.1", port), timeout)
    try:
        found = mod.collect("127.0.0.1", 5)
    finally:
        mod.socket.create_connection = orig
        srv.close()
    out = mod.to_result(found)
    assert out == {"online": True, "rssi": -16, "channel": 6, "free": 151600,
                   "min_free": 105412, "max_block": 110580, "total": 259828}, out
    with open(HA_DIR / "shade_board_sensors.yaml", encoding="utf-8") as f:
        sensors = yaml.load(f, Loader=_Loader)
    ids = {s["sensor"]["unique_id"] for s in sensors}
    assert ids == {"shade_board_wifi_signal", "shade_board_free_memory"}, ids
    print("ok  espsomfy_stats.py parses wifiStrength and memStatus from a fake board")


def check_freeze_forecast():
    with open(HA_DIR / "weather_rest.yaml", encoding="utf-8") as f:
        feeds = yaml.load(f, Loader=_Loader)
    feed = next(x for x in feeds
                if any(s["unique_id"] == "freeze_forecast_14_days" for s in x["sensor"]))
    url = feed["resource"]
    assert "forecast_days=14" in url and "temperature_unit=fahrenheit" in url, url
    assert feed["scan_interval"] == 86400, feed["scan_interval"]
    sensor = feed["sensor"][0]
    assert sensor["json_attributes"] == ["time", "temperature_2m"], sensor
    print("ok  freeze forecast: Open-Meteo 14 days hourly, refreshed daily")
    snow = next(x for x in feeds
                if any(s["unique_id"] == "snowfall_past_7_next_14" for s in x["sensor"]))
    for part in ("hourly=snowfall", "precipitation_unit=inch", "past_days=7", "forecast_days=14"):
        assert part in snow["resource"], (part, snow["resource"])
    assert snow["scan_interval"] == 86400, snow["scan_interval"]
    assert snow["sensor"][0]["json_attributes"] == ["time", "snowfall"], snow["sensor"][0]
    with open(HA_DIR / "information_automations.yaml", encoding="utf-8") as f:
        retry = yaml.load(f, Loader=_Loader)[0]
    targets = retry["actions"][0]["target"]["entity_id"]
    assert set(targets) == {"sensor.freeze_forecast_14_days",
                            "sensor.snowfall_past_7_and_next_14_days",
                            "sensor.snowfall_history_365_days"}, targets
    hist = next(x for x in feeds
                if any(s["unique_id"] == "snowfall_history_365_days" for s in x["sensor"]))
    url = hist["resource_template"]
    assert "archive-api.open-meteo.com" in url and "daily=snowfall_sum" in url, url
    assert "timedelta(days=365)" in url and hist["scan_interval"] == 86400, url
    print("ok  snowfall: Open-Meteo past 7 + next 14 days hourly (inches), daily, retried")


def main():
    check_yaml()
    check_rest_sensors()
    check_shade_automations()
    check_sql()
    check_freeze_sql()
    check_freeze_forecast()
    check_espsomfy_stats()
    print("all Home Assistant config checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
