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
- *̶*̶N̶o̶r̶m̶a̶l̶ ̶D̶a̶t̶a̶*̶*̶ ̶–̶ ̶p̶a̶r̶s̶e̶ ̶a̶n̶d̶ ̶d̶i̶s̶p̶l̶a̶y̶ ̶J̶S̶O̶N̶ ̶s̶e̶n̶s̶o̶r̶ ̶p̶a̶y̶l̶o̶a̶d̶s̶.̶
- *̶*̶N̶o̶ ̶D̶a̶t̶a̶ ̶F̶e̶e̶d̶*̶*̶̶–̶ ̶d̶e̶t̶e̶c̶t̶ ̶a̶n̶d̶ ̶h̶a̶n̶d̶l̶e̶ ̶c̶a̶s̶e̶s̶ ̶w̶h̶e̶r̶e̶ ̶p̶u̶b̶l̶i̶s̶h̶e̶r̶ ̶i̶s̶ ̶c̶o̶n̶n̶e̶c̶t̶e̶d̶ ̶b̶u̶t̶ ̶s̶t̶o̶p̶s̶ ̶s̶e̶n̶d̶i̶n̶g̶ ̶(̶e̶.̶g̶.̶,̶ ̶S̶t̶o̶p̶ ̶b̶u̶t̶t̶o̶n̶ ̶o̶r̶ ̶b̶l̶a̶c̶k̶o̶u̶t̶ ̶s̶i̶m̶u̶l̶a̶t̶i̶o̶n̶)̶.̶
- *̶*̶N̶e̶t̶w̶o̶r̶k̶ ̶D̶r̶o̶p̶ ̶/̶ ̶P̶u̶b̶l̶i̶s̶h̶e̶r̶ ̶O̶f̶f̶l̶i̶n̶e̶*̶*̶ ̶–̶ ̶d̶e̶t̶e̶c̶t̶ ̶O̶F̶F̶L̶I̶N̶E̶ ̶s̶t̶a̶t̶u̶s̶ ̶m̶e̶s̶s̶a̶g̶e̶ ̶f̶r̶o̶m̶ ̶L̶W̶T̶ ̶a̶n̶d̶ ̶i̶n̶d̶i̶c̶a̶t̶e̶ ̶d̶e̶v̶i̶c̶e̶ ̶i̶s̶ ̶d̶o̶w̶n̶.̶ ̶
- *̶*̶W̶i̶l̶d̶ ̶D̶a̶t̶a̶*̶*̶ ̶–̶ ̶i̶d̶e̶n̶t̶i̶f̶y̶ ̶v̶a̶l̶u̶e̶s̶ ̶o̶u̶t̶ ̶o̶f̶ ̶e̶x̶p̶e̶c̶t̶e̶d̶ ̶r̶a̶n̶g̶e̶ ̶a̶n̶d̶ ̶f̶l̶a̶g̶ ̶t̶h̶e̶m̶.̶ ̶-̶ ̶*̶*̶C̶o̶r̶r̶u̶p̶t̶ ̶D̶a̶t̶a̶*̶*̶ ̶–̶ ̶c̶a̶t̶c̶h̶ ̶J̶S̶O̶N̶ ̶d̶e̶c̶o̶d̶e̶ ̶e̶r̶r̶o̶r̶s̶ ̶o̶r̶ ̶m̶i̶s̶s̶i̶n̶g̶ ̶f̶i̶e̶l̶d̶s̶ ̶w̶i̶t̶h̶o̶u̶t̶ ̶c̶r̶a̶s̶h̶i̶n̶g̶.̶
---

## TODO: Subscriber Responsibilities
The subscriber must handle these scenarios:
**email** amazon mtp setup or other alternative email

