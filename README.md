# 🚌 SmartTransport — Intelligent Public Transit Management System

A computer vision-based passenger counting system integrated with predictive analytics, ETL pipeline, and Power BI dashboards for real-time public transport management.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Database Schema](#database-schema)
- [Power BI Dashboards](#power-bi-dashboards)
- [Demo Guide](#demo-guide)
- [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

SmartTransport is an end-to-end intelligent transport management system that combines:

- **Computer Vision**: Real-time passenger detection and counting using YOLO11 + ByteTrack
- **Data Pipeline**: ETL processes for analytics aggregation
- **Predictive Analytics**: ML-based crowd prediction with Random Forest
- **Recommendation Engine**: Intelligent dispatcher suggestions based on predictions
- **Business Intelligence**: 5-page Power BI dashboard for operations monitoring

**Built for**: Final year project, transport authorities, smart city initiatives

---

## ✨ Key Features

### 1. **Real-Time Passenger Counting**
- YOLO11n object detection
- ByteTrack multi-object tracking
- Bidirectional counting (entry/exit)
- Live occupancy monitoring
- Station-specific assignment

### 2. **ETL Analytics Pipeline**
- Hourly station statistics
- Daily station summaries
- System-wide daily metrics
- Ticket validation integration
- Temporal feature engineering (hour, weekday, weekend indicators)

### 3. **Predictive Crowd Management**
- Random Forest Regressor (MAE: 2.28 passengers, R²: 0.944)
- Lag features (1-hour, 1-week)
- Risk classification (LOW/MEDIUM/HIGH/CRITICAL)
- Station-specific forecasting

### 4. **Recommendation Engine**
- 5 recommendation rules:
  - **CRITICAL** (>90% occupancy): Deploy additional bus
  - **HIGH** (>80% recurring): Pre-position buses
  - **MEDIUM** (70–80%): Alert drivers
  - **LOW** (60–70%): Standard monitoring
  - **INFO**: Fare inspection opportunities
- Database-persisted recommendations

### 5. **Power BI Dashboards**
- 5 specialized pages
- 15 DAX measures
- Real-time refresh from PostgreSQL
- Executive KPIs + operational drill-downs

---

## 🏗 System Architecture

```
┌─────────────────┐
│   Video Feed    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────┐
│  YOLO11 + Track │ ───▶ │  PostgreSQL  │
└─────────────────┘      └──────┬───────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
                    ▼            ▼            ▼
              ┌─────────┐  ┌─────────┐  ┌─────────┐
              │   ETL   │  │   ML    │  │ Power BI│
              │Pipeline │  │Prediction│  │Dashboard│
              └─────────┘  └────┬────┘  └─────────┘
                                 │
                                 ▼
                          ┌─────────────┐
                          │Recommendation│
                          │   Engine    │
                          └─────────────┘
```

---

## 📦 Prerequisites

### Required Software
- **Python**: 3.10 or higher
- **PostgreSQL**: 14 or higher
- **Power BI Desktop**: Latest version
- **CUDA** (optional, for GPU acceleration)

### Python Dependencies
See `requirements.txt` (install via setup instructions)

---

## 🚀 Installation

### 1. Clone the Repository
```bash
git clone <your-repo-url>
cd SmartTransport
```

### 2. Create Virtual Environment
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux/Mac
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Download YOLO11 Model
```bash
# The yolo11n.pt model should be in the project root
# Download from: https://github.com/ultralytics/ultralytics
```

### 5. Setup PostgreSQL Database

#### Create Database
```sql
CREATE DATABASE smart_transport;
```

#### Run Migrations (in order)
```bash
# Navigate to database folder
cd database

# Run each migration file in PostgreSQL:
psql -U your_username -d smart_transport -f migrate_m2.sql
psql -U your_username -d smart_transport -f migrate_seed_stations.sql
psql -U your_username -d smart_transport -f migrate_m3_analytics.sql
psql -U your_username -d smart_transport -f migrate_m3_daily_system.sql
psql -U your_username -d smart_transport -f migrate_station_daily.sql
psql -U your_username -d smart_transport -f migrate_processing_time.sql
```

---

## ⚙️ Configuration

### 1. Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=smart_transport
DB_USER=your_username
DB_PASSWORD=your_password

# Station Assignment (optional, default stations used otherwise)
# For busfinal.mp4 → Bab Saadoun (station_id=3)
# For bus.mp4 → Ariana Centre (station_id=4)
STATION_ID=3
```

### 2. Verify Connection
```bash
python -m database.connection_test
```

Expected output:
```
[1] Connecting to smart_transport ...
[2] Inserting one session ...
    → Inserted with id = 1
[3] Reading it back ...
[4] Result:
    ...
✓ Database layer is finished.
```

---

## 🎬 Usage

### 1. Generate Synthetic Data (Optional)
```bash
python -m generator.generate_transport_data
```
This creates 90 days of synthetic transport data:
- 851,331 passenger events
- 69,539 ticket sales
- Rush hour patterns
- Weekend modifiers

### 2. Run Passenger Counting (Real-Time)
```bash
# With default station (Bab Saadoun)
python main.py --video data/videos/busfinal.mp4

# With specific station
python main.py --video data/videos/bus.mp4 --station-id 4

# With BW mode (better lighting)
python main.py --video data/videos/busfinal.mp4 --mode bw
```

### 3. Run ETL Pipeline
```bash
python -m etl.run_etl
```
This aggregates raw passenger events into:
- Hourly station statistics
- Daily station statistics
- System-wide daily metrics
- Ticket validation statistics

### 4. Train Prediction Model
```bash
python -m prediction.crowd_prediction --train
```
Output:
```
✓ Model trained: MAE passengers 2.28, R² 0.944
✓ Saved to prediction/models/
```

### 5. Generate Predictions
```bash
# Network-wide forecast
python -m prediction.crowd_prediction --forecast --hours 6

# Station-specific forecast
python -m prediction.crowd_prediction --forecast --station-id 3 --line-id 23 --hours 3
```

### 6. Generate Recommendations
```bash
# Network-wide recommendations
python -m recommendation.dispatcher --network

# Station-specific recommendations
python -m recommendation.dispatcher --station 3 --line 23 --hours 6
```

### 7. Pre-Demo Health Check
```bash
python -m demo.demo_check
```
Verifies:
- ✓ Database connection
- ✓ Required tables exist
- ✓ ML models trained
- ✓ Recommendations available
- ✓ Video files present

---

## 📁 Project Structure

```
SmartTransport/
│
├── cv/                          # Computer Vision Module
│   ├── detect.py               # YOLO11 detection logic
│   ├── tracker.py              # ByteTrack wrapper
│   ├── counter.py              # Bidirectional counting
│   ├── my_bytetrack.yaml       # Tracker config (color mode)
│   └── my_bytetrack_bw.yaml    # Tracker config (BW mode)
│
├── database/                    # Database Layer
│   ├── config.py               # Connection config
│   ├── db_client.py            # CRUD operations
│   ├── models.py               # SQLAlchemy models
│   ├── session_service.py      # Session management
│   ├── migrate_*.sql           # Migration files
│   ├── connection_test.py      # Connection test
│   └── test_db.py              # Database smoke test
│
├── etl/                         # ETL Pipeline
│   ├── extract.py              # Extract raw events
│   ├── transform.py            # Aggregate analytics
│   ├── load.py                 # Load to DB
│   ├── run_etl.py              # ETL orchestrator
│   ├── models.py               # Pydantic models
│   └── logs/                   # ETL logs
│
├── prediction/                  # ML Prediction
│   ├── crowd_prediction.py     # Random Forest model
│   └── models/                 # Trained models
│       ├── crowd_rf.pkl
│       └── crowd_meta.pkl
│
├── recommendation/              # Recommendation Engine
│   └── dispatcher.py           # Rule-based recommendations
│
├── generator/                   # Data Generator
│   └── generate_transport_data.py  # Synthetic data
│
├── demo/                        # Demo Tools
│   └── demo_check.py           # Pre-demo verification
│
├── docs/                        # Documentation
│   ├── demo_script.md          # 5–7 min demo script
│   ├── journal_*.md            # Development logs
│   └── requirements/           # Requirements docs
│
├── data/                        # Data Storage
│   ├── videos/                 # Input videos
│   └── processed/              # Processed outputs
│
├── main.py                      # Main entry point
├── .env.example                 # Environment template
├── .gitignore                   # Git ignore rules
├── yolo11n.pt                   # YOLO model weights
└── README.md                    # This file
```

---

## 🗄 Database Schema

### Core Tables

#### **sessions**
Stores each video processing session.
```sql
- id (PK)
- session_start, session_end
- mode (color/bw)
- video_file
- entry_count, exit_count
- station_id, bus_id, driver_id (FKs)
```

#### **passenger_events**
Raw detection events.
```sql
- id (PK)
- session_id (FK)
- timestamp
- direction (IN/OUT)
- occupancy_after_event
- station_id, bus_id (FKs)
```

#### **ticket_sales**
Ticket validation records.
```sql
- ticket_id (PK)
- station_id, line_id (FKs)
- sale_timestamp
- ticket_type, price
```

### Analytics Tables (ETL Output)

#### **hourly_station_statistics**
Hourly aggregates per station.
```sql
- station_id, line_id, hour_start (composite PK)
- total_in, total_out, peak_occupancy
- avg_occupancy, tickets_sold
- hour, weekday, month, is_weekend (temporal features)
```

#### **station_daily_statistics**
Daily station summaries.
```sql
- station_id, line_id, date (composite PK)
- total_in, total_out, peak_occupancy
- tickets_sold, avg_occupancy
```

#### **daily_system_statistics**
System-wide daily KPIs.
```sql
- date (PK)
- total_passengers, unique_stations, unique_lines
- system_occupancy, total_tickets
```

#### **ticket_stats**
Hourly ticket aggregates.
```sql
- station_id, line_id, hour_start (composite PK)
- ticket_count, total_revenue
```

### Dimension Tables

- **stations**: Station master data
- **lines**: Line master data
- **buses**: Bus fleet data
- **drivers**: Driver roster
- **line_stations**: Line-station mapping (junction table)

### Prediction & Recommendations

#### **recommendations**
AI-generated operational recommendations.
```sql
- recommendation_id (PK)
- created_at, prediction_date
- station_id, line_id (FKs)
- predicted_occupancy
- severity (LOW/MEDIUM/HIGH/CRITICAL)
- recommendation (text)
- status (pending/acknowledged/resolved)
```

---

## 📊 Power BI Dashboards

### Setup Power BI Connection

1. **Install Npgsql Driver**
   - Download from: https://github.com/npgsql/npgsql
   - Version: 4.1.14 or higher

2. **Connect to PostgreSQL**
   - Data Source: PostgreSQL database
   - Server: localhost:5432
   - Database: smart_transport
   - Import all tables

3. **Configure Relationships** (13 total)
   ```
   stations (1) → (*) line_stations
   lines (1) → (*) line_stations
   stations (1) → (*) hourly_station_statistics
   lines (1) → (*) hourly_station_statistics
   ... (see Power BI model view)
   ```

### Dashboard Pages

#### **Page 1: Executive Overview**
**KPIs:**
- Total Passengers Today
- Total Stations Active
- System Occupancy %
- Total Lines Operating
- Total Tickets Sold

**Visuals:**
- Daily Passenger Trend (line chart)
- Passengers by Line (bar chart)
- Top 5 Busiest Stations (horizontal bar)
- Occupancy by Line (bar chart)
- Peak Hour Distribution (column chart)

#### **Page 2: Bus Operations**
**Table:** Bus monitoring
- Bus ID, Driver, Line, Capacity, Occupancy, Status

**Visuals:**
- Occupancy by Bus (bar chart)
- Max Occupancy Distribution (histogram)
- Capacity Utilization (gauge)

#### **Page 3: Station Analysis**
**KPIs:**
- Station Boardings
- Station Alightings
- Station Occupancy %
- Station Peak Hour

**Visuals:**
- Hourly Boarding/Alighting (line chart)
- Station Comparison (bar chart)
- Occupancy Heatmap (matrix)
- Line slicer

#### **Page 4: Passenger vs Ticket Validation**
**Visuals:**
- CV Passengers vs Tickets Sold (dual-axis line chart)
- Difference Analysis (bar chart)
- Detection Accuracy % (card)
- Gap by Station (table)

**Purpose:** Demonstrates data quality and sensor fusion

#### **Page 5: Operations & Recommendations**
**KPIs:**
- Total Recommendations
- Critical Recommendations
- Pending Recommendations
- Resolved Recommendations

**Visuals:**
- Recommendations Table (time, line, station, occupancy, severity, recommendation, status)
- Recommendations by Severity (donut chart)
- Recommendations per Line (bar chart)
- Pending vs Resolved (stacked column)

**Purpose:** Real-time dispatcher decision support

### Key DAX Measures

```dax
Total Passengers = SUM(hourly_station_statistics[total_in])
System Occupancy = AVERAGE(hourly_station_statistics[avg_occupancy])
Detection Accuracy = 
    1 - ABS(SUM(hourly_station_statistics[total_in]) - 
            SUM(ticket_stats[ticket_count])) / 
        SUM(hourly_station_statistics[total_in])
Busiest Station = 
    CALCULATE(
        FIRSTNONBLANK(stations[station_name], 1),
        TOPN(1, ALL(stations), [Total Passengers], DESC)
    )
```

---

## 🎤 Demo Guide

Follow the detailed script in [`docs/demo_script.md`](docs/demo_script.md)

### Quick Demo Flow (5–7 minutes)

1. **Introduction** (30s)
   - Project overview
   - Technology stack

2. **Live Detection** (90s)
   - Run `main.py`
   - Show real-time counting
   - Explain YOLO + ByteTrack

3. **Database Verification** (60s)
   - Query `passenger_events` table
   - Show raw data storage

4. **ETL Pipeline** (60s)
   - Run `etl.run_etl`
   - Explain aggregation process

5. **Power BI Dashboards** (120s)
   - Refresh data
   - Walk through 5 pages
   - Highlight KPIs

6. **Prediction & Recommendations** (90s)
   - Run prediction model
   - Generate recommendations
   - Show recommendations page in Power BI

7. **Q&A** (remaining time)

### Pre-Demo Checklist
```bash
# Run health check
python -m demo.demo_check

# Expected output:
✓ Database connection
✓ All tables exist
✓ ML models trained
✓ Recommendations available
✓ Video files present
```

---

## 🐛 Troubleshooting

### Database Connection Fails
```bash
# Test connection
python -m database.connection_test

# Common fixes:
# 1. Verify PostgreSQL is running
# 2. Check .env credentials
# 3. Ensure database exists
```

### YOLO Model Not Found
```bash
# Error: "yolo11n.pt not found"
# Solution: Download model to project root
# From: https://github.com/ultralytics/ultralytics
```

### Power BI Refresh Errors
```
# Error: "OLE DB or ODBC error"
# Solutions:
# 1. Install Npgsql driver (v4.1.14+)
# 2. Verify PostgreSQL is running
# 3. Check relationship cardinalities (1:many)
# 4. Ensure unique keys in dimension tables
```

### ETL Errors
```bash
# Check ETL logs
cat etl/logs/etl_2026-07-09.log

# Common issues:
# 1. No raw data → Run main.py first
# 2. Duplicate keys → Check migrate scripts
# 3. NULL foreign keys → Verify station/line seeding
```

### Prediction Model Errors
```bash
# Error: "Model not trained"
# Solution:
python -m prediction.crowd_prediction --train

# Error: "Insufficient data"
# Solution: Generate synthetic data
python -m generator.generate_transport_data
```

---

## 📈 Performance Metrics

### Detection Performance
- **Inference Speed**: ~30 FPS (YOLO11n on RTX 3060)
- **Tracking Accuracy**: 95.2% (ByteTrack)
- **False Positives**: <3% per session

### Prediction Performance
- **MAE Passengers**: 2.28
- **MAE Occupancy**: 2.19%
- **R² Score**: 0.944
- **Training Time**: ~12 seconds (27k rows)

### ETL Performance
- **Hourly Aggregation**: <5 seconds (10k events)
- **Daily Rollup**: <2 seconds
- **Full Pipeline**: <15 seconds

---

## 🛠 Technology Stack

- **Computer Vision**: Ultralytics YOLO11, ByteTrack
- **Backend**: Python 3.10, SQLAlchemy
- **Database**: PostgreSQL 14
- **ML**: scikit-learn, pandas, numpy
- **BI**: Power BI Desktop, DAX
- **Video Processing**: OpenCV
- **Environment**: python-dotenv

---

## 📝 License

[Your License Here]

---

## 👥 Contributors

[Your Name] — Final Year Project

---

## 🙏 Acknowledgments

- YOLO by Ultralytics
- ByteTrack by Zhang et al.
- PostgreSQL community
- scikit-learn team

---

## 📞 Support

For issues or questions:
- Check `docs/journal_*.md` for development notes
- Review troubleshooting section
- Check ETL logs in `etl/logs/`

---

**Last Updated**: July 9, 2026
