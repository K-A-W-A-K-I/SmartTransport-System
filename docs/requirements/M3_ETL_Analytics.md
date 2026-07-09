# Requirements Document — Milestone 3: ETL Pipeline and Analytics

## Introduction

This document defines the requirements for Milestone 3 of the SmartTransport platform: the ETL (Extract, Transform, Load) pipeline and analytics layer. By the end of Milestone 2, the `smart_transport` database contains two categories of data:

- **Master Data** — lines, drivers, buses, stations (relatively static)
- **Transactional Data** — sessions and passenger_events (high-volume, append-only)

The transactional tables are optimized for fast writes from the computer vision pipeline. They are **not** optimized for analytical queries. Milestone 3 introduces an ETL pipeline that reads from the transactional tables, aggregates the data, and loads it into analytics-ready tables. These analytics tables are what Power BI and the prediction engine will consume.

The guiding principle is: **the CV pipeline writes raw events; the ETL pipeline produces meaning from those events.**

---

## Glossary

- **ETL**: Extract, Transform, Load — the process of reading raw data, applying business logic, and writing aggregated results.
- **Source Tables**: The transactional tables written by the CV pipeline: `sessions` and `passenger_events`.
- **Analytics Tables**: Aggregated tables produced by the ETL pipeline, optimized for BI queries.
- **KPI**: Key Performance Indicator — a measurable value used to evaluate performance (e.g., occupancy rate, peak hour).
- **Occupancy Rate**: `(current_occupancy / bus_capacity) × 100` — the percentage of seats filled.
- **Peak Hour**: The one-hour window during which the highest average occupancy was recorded on a given line or station.
- **Aggregation**: The process of grouping raw events by time window, bus, line, or station and computing summary statistics.
- **Granularity**: The time resolution of an aggregation (e.g., per minute, per hour, per day).
- **ETL_Runner**: The Python module (`etl/runner.py`) responsible for orchestrating the ETL pipeline.
- **Fact Table**: An analytics table that stores aggregated measurements (e.g., `fact_hourly_occupancy`).
- **Dimension**: A master data entity used to slice facts (e.g., bus, line, station, time).
- **Idempotent**: A process that produces the same result when run multiple times without creating duplicates.

---

## Requirements

### Requirement 1: ETL Module Structure

**User Story:** As a developer, I want the ETL code to be organized in the `etl/` folder with clear separation of concerns, so that each transformation step is independently testable and maintainable.

#### Acceptance Criteria

1. THE System SHALL place all ETL code in the `etl/` directory.
2. THE System SHALL provide the following modules:

   | Module | Responsibility |
   |--------|---------------|
   | `etl/runner.py` | Orchestrates the full ETL pipeline — calls extract, transform, load in order |
   | `etl/extract.py` | Reads raw data from `sessions` and `passenger_events` |
   | `etl/transform.py` | Applies business logic and computes aggregations |
   | `etl/load.py` | Writes aggregated results into analytics tables |
   | `etl/models.py` | SQLAlchemy ORM definitions for analytics tables |

3. THE ETL_Runner SHALL be executable as a standalone script: `python -m etl.runner`
4. THE ETL_Runner SHALL log the start time, end time, and row counts for each step.

---

### Requirement 2: Analytics Tables

**User Story:** As a data analyst, I want pre-aggregated analytics tables in the database, so that Power BI dashboards load instantly without running expensive queries on raw event data.

#### Acceptance Criteria

1. THE System SHALL create a `fact_hourly_occupancy` table with the following columns:
   - `id` — auto-incrementing primary key
   - `hour_start` — timestamp with time zone (start of the one-hour window), not null
   - `bus_id` — integer, FK → `buses.bus_id`, not null
   - `line_id` — integer, FK → `lines.line_id`, nullable
   - `station_id` — integer, FK → `stations.station_id`, nullable
   - `avg_occupancy` — NUMERIC(5,2), average passenger count during the hour
   - `max_occupancy` — integer, peak passenger count during the hour
   - `avg_occupancy_rate` — NUMERIC(5,2), average occupancy rate (%) during the hour
   - `max_occupancy_rate` — NUMERIC(5,2), peak occupancy rate (%) during the hour
   - `total_boardings` — integer, total IN events during the hour
   - `total_alightings` — integer, total OUT events during the hour
   - `updated_at` — timestamp with time zone, set at insert/update time

2. THE System SHALL create a `fact_daily_summary` table with the following columns:
   - `id` — auto-incrementing primary key
   - `date` — date, not null
   - `bus_id` — integer, FK → `buses.bus_id`, not null
   - `line_id` — integer, FK → `lines.line_id`, nullable
   - `total_boardings` — integer
   - `total_alightings` — integer
   - `avg_occupancy_rate` — NUMERIC(5,2)
   - `peak_occupancy_rate` — NUMERIC(5,2)
   - `peak_hour` — integer (0–23), the hour with highest average occupancy
   - `updated_at` — timestamp with time zone

3. THE System SHALL create a `fact_station_activity` table with the following columns:
   - `id` — auto-incrementing primary key
   - `hour_start` — timestamp with time zone
   - `station_id` — integer, FK → `stations.station_id`, not null
   - `line_id` — integer, FK → `lines.line_id`, nullable
   - `total_boardings` — integer
   - `total_alightings` — integer
   - `avg_occupancy_rate` — NUMERIC(5,2)
   - `updated_at` — timestamp with time zone

4. ALL analytics tables SHALL have a unique constraint on their natural key (e.g., `hour_start + bus_id` for `fact_hourly_occupancy`) so re-running the ETL is idempotent.
5. THE System SHALL create indexes on `hour_start`, `date`, `bus_id`, `line_id`, and `station_id` in all analytics tables.

---

### Requirement 3: Extract Step

**User Story:** As a data engineer, I want the extract step to read only new or updated data since the last ETL run, so that the pipeline is efficient and does not reprocess the entire dataset on every execution.

#### Acceptance Criteria

1. THE ETL_Runner SHALL track the last successful run timestamp in a `etl_watermark` table (columns: `pipeline_name`, `last_run_at`).
2. WHEN the ETL runs, THE extract step SHALL read only `passenger_events` rows where `timestamp > last_run_at`.
3. IF no watermark exists (first run), THE extract step SHALL read all rows.
4. THE extract step SHALL return a pandas DataFrame or equivalent in-memory structure.
5. IF the source tables are empty, THE extract step SHALL return an empty result and the pipeline SHALL exit cleanly without error.

---

### Requirement 4: Transform Step

**User Story:** As a data analyst, I want the transform step to apply consistent business logic, so that all KPIs in the dashboard are computed the same way regardless of when the ETL runs.

#### Acceptance Criteria

1. THE transform step SHALL group `passenger_events` by `(bus_id, line_id, hour_start)` to produce rows for `fact_hourly_occupancy`.
2. THE transform step SHALL group `passenger_events` by `(bus_id, line_id, date)` to produce rows for `fact_daily_summary`.
3. THE transform step SHALL group `passenger_events` by `(station_id, line_id, hour_start)` to produce rows for `fact_station_activity`.
4. THE transform step SHALL compute `avg_occupancy_rate` as the mean of `occupancy_rate` values within the group.
5. THE transform step SHALL compute `peak_hour` as the hour (0–23) with the highest `avg_occupancy_rate` within a given day and bus.
6. IF `occupancy_rate` is NULL for an event (bus capacity unknown), THE transform step SHALL exclude that event from rate calculations but still count it in `total_boardings` / `total_alightings`.

---

### Requirement 5: Load Step

**User Story:** As a data engineer, I want the load step to upsert aggregated rows, so that re-running the ETL corrects any previously loaded data without creating duplicate rows.

#### Acceptance Criteria

1. THE load step SHALL use INSERT … ON CONFLICT DO UPDATE (upsert) for all analytics tables.
2. WHEN an analytics row already exists for a given natural key, THE load step SHALL overwrite it with the newly computed values.
3. THE load step SHALL set `updated_at` to the current UTC timestamp on every upsert.
4. IF the load step fails for one table, THE System SHALL log the error, skip that table, and continue loading the remaining tables.
5. WHEN the load step completes successfully, THE ETL_Runner SHALL update the `etl_watermark` table with the current UTC timestamp.

---

### Requirement 6: KPIs Enabled by the Analytics Layer

**User Story:** As a transport analyst, I want a defined set of KPIs computed by the ETL pipeline, so that the Power BI dashboard answers the questions that matter to the transport authority.

#### Acceptance Criteria

The ETL pipeline SHALL produce data that enables the following KPIs in Power BI without requiring runtime joins on raw tables:

1. **Occupancy Rate by Bus** — current and average `occupancy_rate` per bus, sourced from `fact_hourly_occupancy`.
2. **Busiest Hour** — the hour with the highest `avg_occupancy_rate` per line, sourced from `fact_daily_summary.peak_hour`.
3. **Busiest Station** — the station with the highest `total_boardings` over a date range, sourced from `fact_station_activity`.
4. **Daily Passenger Totals** — total IN and OUT per bus per day, sourced from `fact_daily_summary`.
5. **Occupancy Trend Over Time** — `avg_occupancy_rate` per hour over the last 7 days per bus, sourced from `fact_hourly_occupancy`.
6. **Line Performance Comparison** — side-by-side `avg_occupancy_rate` for Line 23 vs Line 42, sourced from `fact_daily_summary`.

---

### Requirement 7: ETL Scheduling

**User Story:** As a system operator, I want the ETL pipeline to run automatically at a defined interval, so that the analytics tables are always up to date without manual intervention.

#### Acceptance Criteria

1. THE ETL_Runner SHALL be schedulable via Windows Task Scheduler or a cron-equivalent tool.
2. THE ETL_Runner SHALL complete a full pipeline run (extract + transform + load) in under 60 seconds for up to 100,000 `passenger_events` rows.
3. THE ETL_Runner SHALL exit with code 0 on success and a non-zero code on failure.
4. THE ETL_Runner SHALL write a log entry to `etl/logs/etl_YYYY-MM-DD.log` on every run, recording row counts and any errors.

---

### Requirement 8: Data Quality

**User Story:** As a data analyst, I want the ETL pipeline to detect and report data quality issues, so that the dashboard never displays misleading KPIs.

#### Acceptance Criteria

1. THE transform step SHALL flag any `passenger_events` row where `occupancy_after_event < 0` as invalid and exclude it from aggregations.
2. THE transform step SHALL flag any session where `session_end < session_start` as invalid and exclude its events from aggregations.
3. THE transform step SHALL log a warning for any bus_id in `passenger_events` that does not exist in the `buses` table (orphaned foreign key).
4. THE ETL_Runner SHALL report the count of invalid rows skipped in each run's log entry.
5. IF more than 10% of rows in an extract batch are invalid, THE ETL_Runner SHALL log an ERROR-level alert and halt the load step for that batch.

---

## Analytics Table Relationships

```
buses  ←── fact_hourly_occupancy ───→ lines
buses  ←── fact_daily_summary    ───→ lines
           fact_station_activity ───→ stations
                                 ───→ lines
```

All fact tables are independent of `sessions` and `passenger_events` at query time — Power BI reads only the fact tables.

---

## ETL Data Flow

```
passenger_events  (raw, high-volume)
        │
        ▼
  [ Extract ]  reads rows newer than watermark
        │
        ▼
  [ Transform ]  group by hour / day / station
                 compute avg/max occupancy_rate
                 compute peak_hour
                 filter invalid rows
        │
        ▼
  [ Load ]  upsert into fact_hourly_occupancy
            upsert into fact_daily_summary
            upsert into fact_station_activity
            update etl_watermark
        │
        ▼
  Power BI / Prediction Engine
```

---

## Out of Scope for Milestone 3

The following items are explicitly deferred to later milestones:

- Real-time streaming ETL (Milestone 5+)
- Integration with the prediction engine (`crowd_prediction.py`)
- REST API exposure of analytics tables
- Automated dispatcher recommendations
