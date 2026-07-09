# Requirements Document

## Introduction

This document defines the requirements for Milestone 1 of the SmartTransport passenger counting system: PostgreSQL Database Setup. The goal is to establish a persistent storage layer for both session-level summaries and individual passenger crossing events produced by the YOLO-based counting pipeline. At the end of each run, the application records how many passengers boarded (IN) and alighted (OUT), along with the camera mode used, the source video file, and the session timestamp. In addition, every individual crossing detected during a session is stored as a `Passenger_Event`, enabling future analytics such as busiest station identification, peak hour occupancy analysis, and crowd prediction. These results must be stored in a PostgreSQL database named `smart_transport` so that data is available for future reporting, ETL, and dashboard features.

The `smart_transport` database is treated as an installation prerequisite: it must exist before any migration is executed. Schema creation and migration are handled by Alembic operating inside that pre-existing database. A `SessionService` layer sits between `main.py` and the DB_Client so that business logic remains reusable by future components such as the REST API and the prediction pipeline.

## Glossary

- **System**: The SmartTransport passenger counting application, including `main.py` and all modules under `cv/`.
- **Database**: The PostgreSQL instance hosting the `smart_transport` database.
- **Session**: A single end-to-end execution of the counting pipeline against one video file, producing one `entry_count` and one `exit_count`.
- **Session_Record**: A row in the `sessions` table representing the result of one Session.
- **DB_Client**: The Python database access layer using SQLAlchemy ORM and Alembic, located under `database/`.
- **Schema**: The SQL definition of all tables, columns, constraints, and indexes inside the `smart_transport` database.
- **entry_count**: The number of passengers counted as entering the vehicle during a Session.
- **exit_count**: The number of passengers counted as exiting the vehicle during a Session.
- **mode**: The camera pipeline used for the Session — either `"color"` or `"bw"`.
- **video_file**: The filename (not full path) of the source video processed during a Session (e.g., `"busfinal.mp4"` or `"bus.mp4"`).
- **Migration Script**: A versioned Alembic migration file that creates or modifies Database objects inside the `smart_transport` database, located under `database/`.
- **SessionService**: A Python service class in `database/session_service.py` that encapsulates business logic for persisting sessions and events, sitting between `main.py` and the DB_Client.
- **Passenger_Event**: A row in the `passenger_events` table representing a single passenger boarding or alighting event, linked to a Session.
- **Bus**: A row in the `buses` table representing a physical bus vehicle with capacity and line information.
- **Station**: A row in the `stations` table representing a named stop along the bus route.
- **Occupancy**: The number of passengers currently on board the bus after a given Passenger_Event.
- **Alembic**: A database migration tool for SQLAlchemy that manages versioned schema changes.

---

## Requirements

### Requirement 1: Database and Schema Creation

**User Story:** As a developer, I want a PostgreSQL database named `smart_transport` with a well-defined schema, so that passenger counting results have a reliable, typed storage target.

#### Acceptance Criteria

1. THE `smart_transport` database SHALL exist before the migration is executed. The migration SHALL create all required schema objects inside that database if they do not already exist.
2. THE Migration_Script SHALL create a `sessions` table with the following columns:
   - `id` — auto-incrementing integer primary key
   - `session_start` — timestamp with time zone, not null
   - `session_end` — timestamp with time zone, not null
   - `mode` — varchar(10), not null, constrained to the values `'color'` and `'bw'`
   - `video_file` — varchar(255), not null
   - `entry_count` — integer, not null, default 0
   - `exit_count` — integer, not null, default 0
3. THE Migration_Script SHALL create a `buses` table with the following columns:
   - `bus_id` — primary key
   - `capacity` — integer
   - `line_id` — integer, nullable foreign key referencing a future `lines` table (no `lines` table is created in this milestone)
4. THE Migration_Script SHALL create a `stations` table with the following columns:
   - `station_id` — primary key
   - `station_name` — varchar
5. THE Migration_Script SHALL create a `passenger_events` table with the following columns:
   - `id` — auto-incrementing integer primary key
   - `session_id` — integer, foreign key referencing `sessions.id`, not null
   - `timestamp` — timestamp with time zone, not null
   - `station_id` — integer, foreign key referencing `stations.station_id`, nullable
   - `bus_id` — integer, nullable (no FK enforced this milestone; reserved for multi-bus support)
   - `direction` — varchar(3), not null, constrained to the values `'IN'` and `'OUT'`
   - `occupancy_after_event` — integer, not null, default 0
6. THE Migration_Script SHALL add a CHECK constraint on `sessions` ensuring `entry_count >= 0` and `exit_count >= 0`.
7. THE Migration_Script SHALL be idempotent: running it a second time SHALL NOT raise an error or duplicate any object.
8. WHEN the `sessions` table already contains rows, THE Migration_Script SHALL preserve all existing rows unchanged.

---

### Requirement 2: Database Connection Configuration

**User Story:** As a developer, I want the application to read database connection parameters from a configuration file or environment variables, so that credentials are never hard-coded in source files.

#### Acceptance Criteria

1. THE DB_Client SHALL read the PostgreSQL connection parameters — host, port, database name, username, and password — from a `.env` file located at the project root or from environment variables.
2. IF a required connection parameter is missing or empty, THEN THE DB_Client SHALL raise a descriptive `ConfigurationError` before attempting any database connection.
3. THE System SHALL provide a `.env.example` file at the project root listing all required connection parameter keys with placeholder values and no real credentials.
4. THE System SHALL add `.env` to `.gitignore` so that credentials are not committed to version control.

---

### Requirement 3: Database Connection Management

**User Story:** As a developer, I want the DB_Client to manage PostgreSQL connections safely, so that the application does not leak connections or crash when the database is unreachable.

#### Acceptance Criteria

1. WHEN the System starts a Session, THE DB_Client SHALL open a connection to the Database.
2. WHEN a Session ends — whether successfully or due to an error — THE DB_Client SHALL close the database connection.
3. IF the Database is unreachable at connection time, THEN THE DB_Client SHALL log a descriptive error message and allow the Session to complete without persisting data (graceful degradation).
4. THE DB_Client SHALL use a connection pool with a minimum of 1 and a maximum of 5 connections.

---

### Requirement 4: Session Persistence

**User Story:** As a data analyst, I want every completed passenger counting session to be saved to the database, so that historical counts are available for reporting and analysis.

#### Acceptance Criteria

1. WHEN a Session completes — i.e., the video finishes processing or the user presses `q` — THE System SHALL insert one Session_Record AND zero or more Passenger_Event records associated with that session into the Database.
2. THE Session_Record SHALL contain:
   - `session_start`: the UTC timestamp recorded when the pipeline began processing the first frame
   - `session_end`: the UTC timestamp recorded when the pipeline stopped processing
   - `mode`: the `--mode` argument value used for the Session (`"color"` or `"bw"`)
   - `video_file`: the filename of the source video (e.g., `"busfinal.mp4"`)
   - `entry_count`: the final value of `counter.entry_count`
   - `exit_count`: the final value of `counter.exit_count`
3. WHEN a passenger crossing is detected by the System via `_update_color` or `_update_bw`, THE System SHALL record a Passenger_Event containing:
   - `session_id`: the `id` of the current Session_Record
   - `timestamp`: the UTC timestamp of the crossing
   - `direction`: `'IN'` for a downward crossing (entry) or `'OUT'` for an upward crossing (exit)
   - `occupancy_after_event`: the running count of passengers currently on the bus after this event
4. IF the database insert fails, THEN THE System SHALL log the error with the Session data and continue without crashing.
5. WHEN a Session_Record is successfully inserted, THE System SHALL print the inserted row's `id` to the console alongside the existing session summary line.
6. THE System SHALL continue to print the existing summary `Session complete — IN: {entry_count} | OUT: {exit_count}` regardless of whether the database insert succeeded.

---

### Requirement 5: Data Integrity

**User Story:** As a data analyst, I want the stored session data to be accurate and consistent, so that reports built on top of it are trustworthy.

#### Acceptance Criteria

1. THE System SHALL ensure `session_end` is always greater than or equal to `session_start` for every inserted Session_Record.
2. THE System SHALL store all timestamps in UTC using timezone-aware datetime objects.
3. THE DB_Client SHALL use parameterized queries or an ORM for all database writes to prevent SQL injection.
4. FOR ALL valid Session_Records inserted by THE System, reading the record back from the Database SHALL return identical values for `mode`, `video_file`, `entry_count`, and `exit_count` (round-trip integrity).

---

### Requirement 6: Database Module Structure

**User Story:** As a developer, I want the database code to be organized in the `database/` folder, so that it is easy to find, maintain, and extend in future milestones.

#### Acceptance Criteria

1. THE System SHALL place all database access code in the `database/` directory.
2. THE System SHALL provide a `database/schema.sql` file documenting the baseline schema that can be used as a reference alongside the Alembic migrations.
3. THE System SHALL provide a `database/db_client.py` module that exposes at minimum:
   - `connect() -> connection` — opens and returns a database connection
   - `insert_session(conn, session_data: dict) -> int` — inserts a Session_Record and returns the new row `id`
   - `close(conn) -> None` — closes the connection
4. THE System SHALL provide a `database/session_service.py` module that encapsulates all business logic for persisting sessions and events, and is the only caller of `db_client` from `main.py`.
5. THE System SHALL provide a `database/models.py` module containing SQLAlchemy ORM model definitions for all tables (`sessions`, `buses`, `stations`, `passenger_events`).
6. THE System SHALL provide a `database/config.py` module responsible for database configuration and connection pool setup.
7. THE System SHALL provide a `database/README.md` file documenting how to run the Migration Script and configure the `.env` file.

---

### Requirement 7: Event Recording

**User Story:** As a transport analyst, I want every passenger crossing to be recorded individually, so that historical passenger flow can be analyzed beyond simple session totals.

#### Acceptance Criteria

1. WHEN a passenger crossing is detected by the System, THE System SHALL insert one Passenger_Event record into the `passenger_events` table.
2. EVERY Passenger_Event SHALL reference a valid Session via `session_id`.
3. THE System SHALL store Passenger_Events in chronological order by `timestamp`.
4. THE System SHALL store `occupancy_after_event` as the running count of passengers on board immediately after the crossing.
5. THE `direction` field SHALL only contain `'IN'` or `'OUT'`.
6. THE `bus_id` field SHALL be stored when available and SHALL be NULL when the bus is not yet identified.
7. IF a Passenger_Event insert fails, THEN THE System SHALL log the error and continue processing without crashing.

---

### Requirement 8: Database Indexing

**User Story:** As a data analyst, I want commonly queried columns to be indexed, so that dashboard and reporting queries remain fast as the `passenger_events` table grows to millions of rows.

#### Acceptance Criteria

1. THE Migration_Script SHALL create an index on `sessions.session_start`.
2. THE Migration_Script SHALL create an index on `passenger_events.timestamp`.
3. THE Migration_Script SHALL create an index on `passenger_events.station_id`.
4. THE Migration_Script SHALL create an index on `passenger_events.bus_id`.
5. ALL indexes SHALL be created with `IF NOT EXISTS` or equivalent so the migration remains idempotent.
