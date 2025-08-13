# IoT Publisher – Quick Start

## Launch Single Publisher
```bash
python group_1_publisher.py [DEVICE_ID]
```

**DEVICE_ID options:**
- `dev001` → Library
- `dev002` → Engineering Lab
- `dev003` → Student Cafeteria

**Example:**
```bash
python group_1_publisher.py dev001
```

---

## Launch Multiple Publishers
```bash
python group_1_run_multi_publishers.py
```
Runs **all 3 devices** at once in separate threads.

---

## Publisher GUI Features

- **Start Publishing** – begin sending temperature data to the broker.
- **Stop Publishing** – pause data sends (simulates no data feed for an extended period).
- **Go Offline** – disconnect from broker manually
- **Reconnect** – reconnect to broker
- **Enable Wild Data** – send out-of-range values (<0 or >50).
- **Enable Corrupt Data** – send malformed/bad data for error handling tests.
- **Adjust Amplitude / Frequency / Noise** – tweak the data generator parameters.
- **Blackout Simulation** – occasionally skip several sends in a row.
---

## TODO: Subscriber Responsibilities
The subscriber must handle these scenarios:
0. **Email Alert** 
    SendGrid setup for email and related SMTP functionality (Misha implemented but pending Merge)

1. **Dynamic charting**  
   Add a session in the GUI to display a rolling, real‑time chart of temperature values. (see requirements of assignment 9)

2. **Multiple subscribers**  
   Support running **at least two** subscribers simultaneously (unique client IDs).

3. **Detect “connected but not sending”**  
   if no data has arrived for **> 2×** the publish interval (configurable), Per device set status to Stopped (not OFFLINE)

4. **Detect skipped messages (single skip & blackout)**  
   Use `seq` gaps (preferred) or timestamp deltas to detect single or block skips of data; show a visible indicator.<img width="290" height="255" alt="image" src="https://github.com/user-attachments/assets/46173785-b5eb-4044-a2f5-728e529e125c" />

5. **Wild data handling**  
   Treat values **< 0** or **> 50** as wild; highlight in the UI and log. Please refer to data_generator.py

6. **Corrupt data handling**  
   Gracefully handle invalid payloads (e.g., `"ERROR"`, `"SENSOR_FAULT"`, `None`, `"NaN"`); do not crash, show an alert and skip unsafe parsing.  Please refer to data_generator.py

7. **Status recovery**  
   After an **OFFLINE** LWT and subsequent reconnect, set device status back to **ONLINE**.<img width="586" height="82" alt="image" src="https://github.com/user-attachments/assets/c96023f9-9c3f-4cce-81c4-eaf38e529489" />


## Implementation Guide

### 1) Handle normal data (text + visual)
- Show a **live value** (e.g., `22.4 °C`) and **Last seen** per device.
- Plot a **rolling line chart** (keep ~300–500 points; drop old ones).

### 2) Detect & handle out‑of‑range (wild) data
- Rule: **value < 0** or **value > 50** (must match the publisher).
- On wild:
  - **Highlight** the reading (badge/row color).
  - Add a **marker/flag** on the chart.
  - Send **one email alert** (rate‑limited, e.g., 1 per 5 min per device).
  - Continue running (no crashes).

### 3) Detect & handle corrupt data
- Treat as corrupt when value is not a valid float: `"ERROR"`, `"SENSOR_FAULT"`, `None`, `"NaN"`, or missing keys.
- On corrupt:
  - **Skip plotting** that point.
  - Show a **red “CORRUPT”** badge with a short reason.
  - **Email alert** (rate‑limited).
  - Continue running.

### 4) Detect & handle missing transmission (connected but not sending)
- Threshold: **no data > 2 × publish.interval** (+ small grace).
- On threshold:
  - Set state **NO DATA (Stopped)** (distinct from OFFLINE).
  - **Pause**/break the chart line by appending a gap (`None/NaN`).
  - Show: “**No data for Ns (expected every Xs)**”.
  - Send **one email** on entry; **clear** on first recovery message.

### 5) Handle ONLINE/OFFLINE via status topic
- If `status == "OFFLINE"` → show **OFFLINE** (stop plotting; cancel NO DATA timer).
- If `status == "ONLINE"` → show **ONLINE**.
- After reconnect, **first data message** clears any **NO DATA** badge and resumes the line.

### 6) Run multiple subscribers
- Start ≥ 2 subscriber apps with **unique MQTT `client_id`s** (e.g., `sub-ui-1`, `sub-ui-2`).
- Both subscribe to the same topics; each maintains its own UI state.

---

## Notes
- All broker and publish behavior (server, port, QoS, topics, interval, miss rate, blackout, device map) are configured in project’s **config file**.
- Keep the subscriber’s **wild/corrupt rules** in sync with the publisher’s `data_generator.py` to avoid false positives/negatives.



