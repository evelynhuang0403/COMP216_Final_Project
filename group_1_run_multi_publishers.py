import subprocess
import time

# List of predefined device IDs
device_ids = ["dev001", "dev002", "dev003"]

# Launch each publisher in a separate subprocess
processes = []
for dev_id in device_ids:
    print(f"Starting publisher for {dev_id}...")
    process = subprocess.Popen(["python", "group_1_publisher.py", dev_id])
    processes.append(process)
    time.sleep(1)  # Optional: stagger the start time slightly

print("All publishers are running. Press Ctrl+C to terminate them.")

try:
    # Keep the main script alive while subprocesses run
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nTerminating all publishers...")
    for p in processes:
        p.terminate()