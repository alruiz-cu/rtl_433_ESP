-- Copyright (c) 2026 Al Ruiz. All rights reserved.
--
-- SQL integration sensor for the Information dashboard: how many times the
-- outdoor temperature reached 32 F or below in the last 7 days, and for how long.
-- Settings -> Devices & services -> Add integration -> SQL:
--   Name:          Freezing last 7 days     (entity sensor.freezing_last_7_days)
--   Database URL:  leave empty (the default recorder SQLite database)
--   Column:        freeze_count             (state = number of times it dropped to 32 F or below)
--   Query:         the statement below (HA requires it to start with SELECT)
-- The other column, freeze_minutes, becomes an attribute: total minutes at or
-- below 32 F in the window. A dip that is already under way when the window
-- starts counts as one time. Unavailable readings end a freezing stretch, and
-- one gap between readings counts for at most 3 hours.
-- The third column, last_freeze_start, is the unix time the most recent
-- freezing stretch began (NULL if none in the window).
-- last_freeze_ever is the latest time the temperature was at or below 32 F in
-- all recorded history: detailed states (kept 10 days) or the hourly long-term
-- statistics (kept forever; an hour counts if its minimum was 32 F or below,
-- and the time is that hour's start). history_since is when the long-term
-- statistics for the sensor begin.
SELECT
  (SELECT COUNT(*) FROM (
     SELECT v <= 32 AS frz, LAG(v <= 32) OVER (ORDER BY ts) AS prev
     FROM (SELECT s.last_updated_ts AS ts,
           CASE WHEN s.state GLOB '[0-9-]*' THEN CAST(s.state AS REAL) END AS v
    FROM states s JOIN states_meta m ON s.metadata_id = m.metadata_id
    WHERE m.entity_id = 'sensor.acurite_5n1_c_364_temperature'
      AND s.last_updated_ts > CAST(strftime('%s','now') AS INTEGER) - 604800) WHERE v IS NOT NULL)
   WHERE frz = 1 AND (prev IS NULL OR prev = 0)) AS freeze_count,
  (SELECT CAST(ROUND(IFNULL(SUM(MIN(nxt - ts, 10800)), 0) / 60.0) AS INTEGER) FROM (
     SELECT ts, CASE WHEN v IS NOT NULL AND v <= 32 THEN 1 ELSE 0 END AS frz,
            LEAD(ts, 1, CAST(strftime('%s','now') AS REAL)) OVER (ORDER BY ts) AS nxt
     FROM (SELECT s.last_updated_ts AS ts,
           CASE WHEN s.state GLOB '[0-9-]*' THEN CAST(s.state AS REAL) END AS v
    FROM states s JOIN states_meta m ON s.metadata_id = m.metadata_id
    WHERE m.entity_id = 'sensor.acurite_5n1_c_364_temperature'
      AND s.last_updated_ts > CAST(strftime('%s','now') AS INTEGER) - 604800))
   WHERE frz = 1) AS freeze_minutes,
  (SELECT CAST(MAX(ts) AS INTEGER) FROM (
     SELECT ts, v <= 32 AS frz, LAG(v <= 32) OVER (ORDER BY ts) AS prev
     FROM (SELECT s.last_updated_ts AS ts,
           CASE WHEN s.state GLOB '[0-9-]*' THEN CAST(s.state AS REAL) END AS v
    FROM states s JOIN states_meta m ON s.metadata_id = m.metadata_id
    WHERE m.entity_id = 'sensor.acurite_5n1_c_364_temperature'
      AND s.last_updated_ts > CAST(strftime('%s','now') AS INTEGER) - 604800) WHERE v IS NOT NULL)
   WHERE frz = 1 AND (prev IS NULL OR prev = 0)) AS last_freeze_start,
  (SELECT CAST(MAX(t) AS INTEGER) FROM (
     SELECT MAX(s.last_updated_ts) AS t
     FROM states s JOIN states_meta m ON s.metadata_id = m.metadata_id
     WHERE m.entity_id = 'sensor.acurite_5n1_c_364_temperature'
       AND s.state GLOB '[0-9-]*' AND CAST(s.state AS REAL) <= 32
     UNION ALL
     SELECT MAX(st.start_ts) AS t
     FROM statistics st JOIN statistics_meta sm ON st.metadata_id = sm.id
     WHERE sm.statistic_id = 'sensor.acurite_5n1_c_364_temperature' AND st.min <= 32)) AS last_freeze_ever,
  (SELECT CAST(MIN(st.start_ts) AS INTEGER)
     FROM statistics st JOIN statistics_meta sm ON st.metadata_id = sm.id
     WHERE sm.statistic_id = 'sensor.acurite_5n1_c_364_temperature') AS history_since
LIMIT 1;
