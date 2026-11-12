-- Copyright (c) 2026 Al Ruiz. All rights reserved.
--
-- SQL integration sensor for the Weather dashboard's wind direction charts.
-- Settings -> Devices & services -> Add integration -> SQL:
--   Name:          Wind direction history   (entity sensor.wind_direction_history)
--   Database URL:  leave empty (the default recorder SQLite database)
--   Column:        points                   (state = number of 5-minute buckets)
--   Query:         the statement below
-- The other selected column, samples, becomes an attribute holding
-- "bucket:direction:max_wind_mph,..." where bucket = unix time / 300.
-- Covers the last 6 h + 5 min (21900 s) of sensor.acurite_5n1_c_364_*.
WITH d AS (
  SELECT CAST(s.last_updated_ts / 300 AS INTEGER) AS b, s.state AS v, MAX(s.last_updated_ts) AS t
  FROM states s JOIN states_meta m ON s.metadata_id = m.metadata_id
  WHERE m.entity_id = 'sensor.acurite_5n1_c_364_wind_direction'
    AND s.last_updated_ts > CAST(strftime('%s','now') AS INTEGER) - 21900
    AND s.state GLOB '[0-9]*'
  GROUP BY b
), w AS (
  SELECT CAST(s.last_updated_ts / 300 AS INTEGER) AS b, MAX(CAST(s.state AS REAL)) AS v
  FROM states s JOIN states_meta m ON s.metadata_id = m.metadata_id
  WHERE m.entity_id = 'sensor.acurite_5n1_c_364_wind_average'
    AND s.last_updated_ts > CAST(strftime('%s','now') AS INTEGER) - 21900
    AND s.state GLOB '[0-9]*'
  GROUP BY b
)
SELECT COUNT(*) AS points,
       GROUP_CONCAT(d.b || ':' || d.v || ':' || IFNULL(ROUND(w.v, 1), ''), ',') AS samples
FROM d LEFT JOIN w ON d.b = w.b
LIMIT 1;
