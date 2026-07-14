# SmartTransport

AI-powered public transport monitoring system combining computer vision, real-time database storage, ETL analytics, machine learning crowd prediction, and an operations web portal.

---

## Overview

SmartTransport captures real passenger data from bus cameras, counts entries and exits using YOLO + ByteTrack, stores every event in PostgreSQL, transforms raw data into analytics through an ETL pipeline, predicts crowd levels with a Random Forest model, generates operational recommendations, and exposes everything through a Flask web portal and Power BI dashboards.

---

## Features

- **Computer Vision** — YOLO11n + ByteTrack detect and track passengers in real time. Bidirectional counting (entry / exit) with two camera modes (color and overhead BW).
- **PostgreSQL** — Every crossing event written immediately. Master data for buses, drivers, stations, lines.
- **ETL Pipeline** — Incremental extract → transform → load into 6 analytics tables. Watermark-based, idempotent, <5 seconds.
- **Prediction Model** — Random Forest trained on 27K rows. MAE: 2.28 passengers. R²: 0.944.
- **Recommendation Engine** — Rule-based dispatcher recommendations (CRITICAL / HIGH / MEDIUM / LOW / INFO) saved to the database with full status lifecycle.
- **Operations Portal** — Flask web app with 8 pages: Operations Center, Tickets, Buses, Drivers, Recommendations, Activity, Settings, Search.
- **Power BI** — 5-page executive dashboard connected directly to PostgreSQL.

---

## Architecture

```
Video Feed
    │
    ▼
YOLO11n + ByteTrack
    │  (detect + track persons)
    ▼
LineCounter
    │  (bidirectional crossing events)
    ▼
PostgreSQL
    │  (passenger_events, sessions)
    ├──────────────────────────────────────┐
    ▼                                      ▼
ETL Pipeline                        Ticket Sales
    │  (extract → transform → load)   (portal CRUD)
    ▼
Analytics Tables
    ├────────────────────┐
    ▼                    ▼
Prediction Model     Power BI
    │  (Random Forest)
    ▼
Recommendations
    │
    ▼
Operations Portal
```

---

## Model Performance

| Metric | Boardings | Occupancy |
|---|---|---|
| MAE | 2.28 passengers | 2.19% |
| RMSE | 3.30 passengers | 3.16% |
| R² | 0.944 | 0.988 |

Trained on 27,541 rows (90 days, 20% test split, random_state=42).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Object Detection | Ultralytics YOLO11n |
| Tracking | ByteTrack |
| Video | OpenCV |
| Backend | Python 3.10+, Flask 3.x |
| ORM | SQLAlchemy |
| Database | PostgreSQL 14+ |
| ETL | pandas |
| Machine Learning | scikit-learn (Random Forest) |
| Business Intelligence | Power BI Desktop |
| Frontend | Bootstrap 5, Jinja2 |

---

## Installation

### 1. Clone

```bash
git clone https://github.com/K-A-W-A-K-I/SmartTransport-System.git
cd SmartTransport-System
```

### 2. Virtual environment

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/macOS
```

### 3. Install dependencies

```bash
pip install ultralytics opencv-python sqlalchemy psycopg2-binary \
            pandas scikit-learn flask python-dotenv
```

### 4. Download assets (not in git)

Place in project root:
```
yolo11n.pt          ← YOLO model weights
data/videos/busfinal.mp4
data/videos/bus.mp4
```

### 5. Configure database

```bash
cp .env.example .env
```

Edit `.env` with your PostgreSQL credentials.

### 6. Run migrations

```bash
psql -U postgres -d smart_transport -f database/migrate_m2.sql
psql -U postgres -d smart_transport -f database/migrate_seed_stations.sql
psql -U postgres -d smart_transport -f database/migrate_m3_analytics.sql
psql -U postgres -d smart_transport -f database/migrate_m3_daily_system.sql
psql -U postgres -d smart_transport -f database/migrate_station_daily.sql
psql -U postgres -d smart_transport -f database/migrate_processing_time.sql
psql -U postgres -d smart_transport -f database/migrate_m5_recommendations.sql
psql -U postgres -d smart_transport -f database/migrate_m5_buses_drivers.sql
```

---

## Running

### Computer Vision (passenger counting)

```bash
python main.py --mode color --station-id 3
python main.py --mode bw    --station-id 4
```

### ETL Pipeline

```bash
python -m etl.run_etl
```

### Prediction model

```bash
python -m prediction.crowd_prediction --train
python -m prediction.crowd_prediction --forecast --station 3 --line 1 --hours 6
```

### Recommendations

```bash
python -m recommendation.dispatcher --network
```

### Operations Portal

```bash
python webapp/app.py
```

Open: http://localhost:5000

### Pre-demo health check

```bash
python -m demo.demo_check
```

### Generate synthetic data (optional)

```bash
python -m generator.generate_transport_data
```

---

## Folder Structure

```
SmartTransport/
│
├── cv/                          Computer Vision
│   ├── detect.py               YOLO11n wrapper
│   ├── tracker.py              ByteTrack config resolver
│   ├── counter.py              Bidirectional line counter
│   └── my_bytetrack*.yaml      Tracker configs
│
├── database/                    Database Layer
│   ├── config.py               SQLAlchemy engine
│   ├── models.py               ORM models
│   ├── db_client.py            CRUD operations
│   ├── session_service.py      Session lifecycle
│   └── migrate_*.sql           Migration files
│
├── etl/                         ETL Pipeline
│   ├── extract.py              Read raw data
│   ├── transform.py            Aggregate analytics
│   ├── load.py                 Upsert to DB
│   ├── run_etl.py              Orchestrator
│   └── logs/                   Daily log files
│
├── prediction/                  ML Prediction
│   ├── crowd_prediction.py     Random Forest model
│   └── models/                 Trained artifacts (.pkl)
│
├── recommendation/              Recommendation Engine
│   └── dispatcher.py           Rule-based dispatcher
│
├── webapp/                      Operations Portal (Flask)
│   ├── app.py                  App factory
│   ├── routes/                 URL handlers
│   ├── services/               DB query layer
│   └── templates/              Jinja2 HTML
│
├── generator/                   Synthetic Data Generator
│   └── generate_transport_data.py
│
├── demo/                        Demo Tools
│   └── demo_check.py           Pre-demo health check
│
├── docs/                        Documentation
│   ├── Architecture.md
│   ├── Database.md
│   ├── ETL.md
│   ├── Prediction.md
│   ├── Recommendation.md
│   ├── Portal.md
│   ├── Deployment.md
│   └── Presentation.md
│
├── data/videos/                 Input videos (not in git)
├── main.py                      CV entry point
├── yolo11n.pt                   YOLO weights (not in git)
├── .env.example                 Environment template
└── .gitignore
```

---

## Documentation

Full documentation in `docs/`:

| Document | Contents |
|---|---|
| [Architecture.md](docs/Architecture.md) | Full system diagram, component descriptions, data flow |
| [Database.md](docs/Database.md) | All tables, columns, types, migration order |
| [ETL.md](docs/ETL.md) | Pipeline stages, flow diagram, error handling |
| [Prediction.md](docs/Prediction.md) | Model features, metrics, usage, inference API |
| [Recommendation.md](docs/Recommendation.md) | Business rules, thresholds, status lifecycle |
| [Portal.md](docs/Portal.md) | Page descriptions, routes, architecture |
| [Deployment.md](docs/Deployment.md) | Step-by-step setup from scratch |
| [Presentation.md](docs/Presentation.md) | Demo script, key numbers, Q&A prep |

---

## Future Work

- Real-time WebSocket push (auto-refresh without page reload)
- Authentication and role-based access
- Multi-bus live dashboard (side-by-side occupancy)
- Alert notifications (email/SMS on CRITICAL)
- CSV/Excel export from portal
- Dockerized deployment
- REST API for mobile integration

---

## Notes

- Place `yolo11n.pt` in the project root before running CV
- Place videos in `data/videos/` before running `main.py`
- Both are excluded from git to keep the repository lightweight

---

*SmartTransport — Final Year Project, 2026*
