# SmartTransport — End-to-End Demo Script
**Target duration: 5–7 minutes**

---

## Before You Start (5 min before demo)

Run this to verify everything is ready:
```bash
python -m demo.demo_check
```

Make sure:
- [ ] Power BI is open on Page 1 (Executive Overview)
- [ ] pgAdmin is open on the `passenger_events` table (or a terminal ready)
- [ ] Two terminals open side by side: one for commands, one for logs
- [ ] `recommendations` table visible in pgAdmin or second terminal

---

## Step 1 — "The system counts passengers in real time" (1 min)

**Say:** "This is our computer vision pipeline. It uses YOLO to detect and track passengers crossing the bus door line."

```bash
python main.py --mode color --bus-id 1
```

- A window opens showing the video with the counting line
- Point out: IN/OUT counters updating on screen
- Let it run for 20–30 seconds, then press `q`

**Say:** "Every crossing is immediately written to PostgreSQL."

Show in pgAdmin or run:
```bash
python -m demo.demo_check --events
```

Expected output:
```
passenger_events: X rows  ← number increased from before
Latest event: direction=IN  occupancy=4  station=1
```

---

## Step 2 — "The ETL aggregates the raw data" (1 min)

**Say:** "Raw events alone aren't useful for analysis. The ETL pipeline transforms them into analytics-ready tables."

```bash
python -m etl.run_etl
```

Point out in the output:
- Events extracted: X
- hourly_station rows aggregated
- All 6 tables upserted
- Duration: ~2 seconds

**Say:** "In production this would run on a schedule — every hour or every night."

---

## Step 3 — "Power BI reflects the new data" (1.5 min)

Switch to Power BI.

```
Home → Refresh
```

Walk through the pages:

**Page 1 — Executive Overview**
- "Total passengers counted by the CV system — 851,000 over 90 days"
- "Average occupancy across the network — X%"
- "Busiest line is Line 23, busiest station is [station name]"
- Point to the daily trend — "you can see the rush hour pattern every day"

**Page 4 — Passenger vs Ticket Validation**
- "This is the most interesting page for operations"
- "CV counted X passengers. Tickets sold: Y. Difference: Z."
- "Detection accuracy is 97% — that 3% gap could be fare evasion or model error"

---

## Step 4 — "The prediction model forecasts the next hours" (1 min)

**Say:** "We trained a Random Forest model on the 90 days of data. It predicts occupancy for any station, line, and hour."

```bash
python -m prediction.crowd_prediction --forecast --station 3 --line 2 --hour 7 --weekday 0 --month 7 --hours 8
```

Point out the output table:
```
Hour    Passengers   Occupancy    Risk
07:00          64       41.3%     LOW
08:00          66       41.2%     LOW
16:00          64       40.2%     LOW
17:00          63       40.3%     LOW
```

**Say:** "R² of 0.944 — the model explains 94% of the variance in passenger counts using only time features and historical lags."

---

## Step 5 — "The dispatcher generates recommendations" (1 min)

**Say:** "The prediction feeds a rule engine. Instead of just describing the data, the system now gives actionable advice."

```bash
python -m recommendation.dispatcher --network --hour 7 --hours 3 --weekday 0 --month 7 --min HIGH
```

Point out a CRITICAL recommendation:
```
🔴 [CRITICAL] Deploy additional bus immediately
   Line    : Tunis Centre - La Marsa
   Station : La Goulette
   Time    : 07:00 – 08:00
   Occupancy: 97.3%
   ➜ Deploy one additional bus for the 07:00–08:00 slot.
```

**Say:** "And these recommendations are automatically saved to the database — not just printed."

---

## Step 6 — "The dashboard shows live recommendations" (1 min)

Switch to Power BI → **Page 5 — Operations & Recommendations**

```
Home → Refresh
```

Point out:
- "Total recommendations: X — Critical: Y — Pending: Z"
- Donut chart: "Most are CRITICAL — morning rush hours"
- Table: "The dispatcher can see exactly which line, which station, which hour"
- "Status column — pending means not yet acted on. A real system would update this to resolved when the extra bus is deployed."

**Say:** "This is the complete loop: camera → database → ETL → prediction → recommendation → dashboard."

---

## Closing Line (15 seconds)

**Say:** "What you're seeing is a complete data pipeline — from a camera on a bus door to a management dashboard with AI-generated operational recommendations. Every component is modular: you can swap the prediction model, add new lines, or connect a live camera without changing anything else."

---

## Backup answers for tough questions

**"Is this real-time?"**
> "The CV pipeline is real-time — events are written as passengers cross. The ETL and dashboard currently run on demand, but the architecture supports scheduling them every few minutes with a cron job or task scheduler."

**"How accurate is the model?"**
> "MAE of 2.3 passengers per hour prediction, R² of 0.944 on held-out test data. The model was trained on 90 days of synthetic data — with real operational data it would improve further."

**"What happens when the bus is full?"**
> "The occupancy rate hits 100% and triggers a CRITICAL recommendation immediately. The dispatcher sees it on the Operations page and can act before the next bus arrives."

**"Could this work with a live camera?"**
> "Yes — `main.py` already supports live video by swapping the video file path for a camera index. The rest of the pipeline is unchanged."
