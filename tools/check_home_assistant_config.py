#!/usr/bin/env python3
# Copyright (c) 2026 Al Ruiz. All rights reserved.
"""Checks the Home Assistant files in contrib/home-assistant.

* Every .yaml file parses (HA's !include style tags are accepted).
* weather_rest.yaml defines the sensors the Weather dashboard uses.
* shade_automations.yaml raises shades above 8 mph, lowers only below 4 mph, and
  lowers the living room shade (id 3) when sunny, every 30 min between noon and 4 pm.
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
            "open_meteo_us_aqi", "open_meteo_pm25", "open_meteo_ozone"}
    assert want <= ids, f"missing REST sensors: {want - ids}"
    for feed in feeds:
        assert feed["resource"].startswith("https://"), feed["resource"]
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
    count, minutes = db.execute(sql).fetchone()
    assert (count, minutes) == (3, 60 + 30 + 10 + 180), (count, minutes)
    db.execute("DELETE FROM states")
    count, minutes = db.execute(sql).fetchone()
    assert (count, minutes) == (0, 0), (count, minutes)
    print(f"ok  freeze_last_7_days.sql -> {count} times, {minutes} min on empty data; test data ok")


def main():
    check_yaml()
    check_rest_sensors()
    check_shade_automations()
    check_sql()
    check_freeze_sql()
    print("all Home Assistant config checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
