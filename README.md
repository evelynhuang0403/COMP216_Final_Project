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
Runs group_1_run_multi_publishers.py - **all 3 devices** at once in separate threads.

---

## Publisher GUI Features

- **Start Publishing** – begin sending temperature data to the broker.
- **Stop Publishing** – pause data sends (simulates no data feed for an extended period).
- **Go Offline** – disconnect from broker (simulates network drop; triggers LWT OFFLINE message).
- **Enable Wild Data** – send out-of-range values (<0 or >50).
- **Enable Corrupt Data** – send malformed/bad data for error handling tests.
- **Adjust Amplitude / Frequency / Noise** – tweak the data generator parameters.
- **Blackout Simulation** – occasionally skip several sends in a row.

---

## TODO: Subscriber Responsibilities
The subscriber must handle these scenarios:
- **Normal Data** – parse and display JSON sensor payloads.
- **No Data Feed** – detect and handle cases where publisher is connected but stops sending (e.g., Stop button or blackout simulation).
- **Network Drop / Publisher Offline** – detect OFFLINE status message from LWT and indicate device is down.
- **Wild Data** – identify values out of expected range and flag them.
- **Corrupt Data** – catch JSON decode errors or missing fields without crashing.

