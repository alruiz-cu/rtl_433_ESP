#!/usr/bin/env python3
# Copyright (c) 2026 Al Ruiz. All rights reserved.
"""Checks the Home Assistant files in contrib/home-assistant.

* Every .yaml file parses (HA's !include style tags are accepted).
* weather_rest.yaml defines the sensors the Weather dashboard uses.
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
    print("ok  weather_rest.yaml defines all dashboard sensors")


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


def main():
    check_yaml()
    check_rest_sensors()
    check_sql()
    print("all Home Assistant config checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
