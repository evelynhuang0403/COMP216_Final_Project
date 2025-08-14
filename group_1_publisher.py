import sys
import json
import time
import threading
import random
from tkinter import Tk, StringVar, END, DISABLED, NORMAL
from tkinter import ttk
from random import random as rand01
from typing import Optional

import paho.mqtt.client as mqtt

from group_1_data_generator import DataGenerator
from group_1_util import MessagePackager
from group_1_publisher_ui import setup_style, build_ui


# ------------------ Config loader ------------------
def load_config(path="group_1_config.json"):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"[CONFIG] Failed to load {path}: {e}")
        return {}


CFG = load_config()

# ------------------ MQTT + app config (defaults if not in config file) ------------------
BROKER = CFG.get("mqtt", {}).get("broker", "broker.hivemq.com")
PORT = CFG.get("mqtt", {}).get("port", 1883)
KEEPALIVE = CFG.get("mqtt", {}).get("keepalive", 5)
QOS = CFG.get("mqtt", {}).get("qos", 1)

TOPIC_DATA = CFG.get("mqtt", {}).get("topics", {}).get("data", "group_1/temp")
TOPIC_STATUS = CFG.get("mqtt", {}).get("topics", {}).get("status", "group_1/status")

PUBLISH_INTERVAL = CFG.get("publish", {}).get("interval", 2)
DEFAULT_MISS_RATE = CFG.get("publish", {}).get("miss_rate", 0.02)

BLACKOUT_CFG = CFG.get("publish", {}).get("blackout", {})
DEFAULT_BLACKOUT_CHANCE = BLACKOUT_CFG.get("chance", 0.03)
DEFAULT_BLACKOUT_MIN = BLACKOUT_CFG.get("min", 3)
DEFAULT_BLACKOUT_MAX = BLACKOUT_CFG.get("max", 8)

DEVICE_LOCATIONS = CFG.get("devices", {
    "dev001": "Library",
    "dev002": "Engineering Lab",
    "dev003": "Student Cafeteria",
})

# ------------------ CLI args: device id -> location ------------------
if len(sys.argv) < 2 or sys.argv[1] not in DEVICE_LOCATIONS:
    print("Usage: python group_1_publisher.py [dev001 | dev002 | dev003]")
    sys.exit(1)

DEVICE_ID = sys.argv[1]
LOCATION = DEVICE_LOCATIONS[DEVICE_ID]


class TemperaturePublisher:
    def __init__(self, master):
        self.master = master
        self.master.title(f"Group 1 - IoT Publisher ({DEVICE_ID})")

        # device info
        self.device_id = DEVICE_ID
        self.location = LOCATION
        self.generator = DataGenerator()
        self.packager = MessagePackager(self.device_id, self.location)

        # MQTT state
        self.client: Optional[mqtt.Client] = None
        self.connected = False
        self.reconnecting = False
        self.running = False

        # publishing control
        self.block_publishing = False
        self.miss_rate = DEFAULT_MISS_RATE

        # blackout simulation
        self.blackout_active = False
        self.blackout_remaining = 0
        self.blackout_chance = DEFAULT_BLACKOUT_CHANCE
        self.blackout_min = DEFAULT_BLACKOUT_MIN
        self.blackout_max = DEFAULT_BLACKOUT_MAX

        # reconnect settings
        self.auto_reconnect = True
        self._retries = 0
        self.manual_offline = False

        # shared UI state
        self.status_text = StringVar(value="Status: Disconnected")

        # setup UI
        setup_style()
        build_ui(self, master)

    # update status label in a thread-safe way
    def ui_status(self, text: str):
        try:
            def _set():
                self.status_text.set("")
                self.master.update_idletasks()
                self.status_text.set(text)
            self.master.after(0, _set)
        except Exception:
            pass

    # ----------------------- MQTT setup & callbacks ---------------------
    def setup_client(self):
        try:
            # Try VERSION2 (newer paho-mqtt)
            self.client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=f"group1_pub_{self.device_id}",
                protocol=mqtt.MQTTv5
            )
        except AttributeError:
            # Fallback for older paho-mqtt versions
            self.client = mqtt.Client(
                client_id=f"group1_pub_{self.device_id}",
                protocol=mqtt.MQTTv5
            )

        # LWT: unexpected disconnect => OFFLINE
        lwt_payload = json.dumps({
            "device_id": self.device_id,
            "location": self.location,
            "status": "OFFLINE"
        })
        self.client.will_set(TOPIC_STATUS, lwt_payload, qos=1, retain=True)

        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect

    # ---- helper to publish status (ONLINE / OFFLINE / STOPPED) ----
    def publish_status(self, status: str):
        try:
            if self.client:
                payload = json.dumps({
                    "device_id": self.device_id,
                    "location": self.location,
                    "status": status
                })
                # retain so subscribers always see the latest state
                self.client.publish(TOPIC_STATUS, payload, qos=1, retain=True)
        except Exception as e:
            print(f"[{self.device_id}] Failed to publish status '{status}': {e}")

    # connect to broker
    def connect_to_broker(self):
        if self.client is None:
            self.setup_client()
        try:
            self.client.connect(BROKER, PORT, keepalive=KEEPALIVE)
            self.client.loop_start()
            self.reconnecting = False
            self.ui_status("Status: Connecting…")
        except Exception as e:
            self.ui_status(f"Status: Connect error: {e}")
            print(f"[{self.device_id}] Connect error: {e}")

    # MQTT on_connect callback
    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        ok = (reason_code == 0)
        self.connected = ok

        if ok:
            # Reset retry counter and allow publishing
            self._retries = 0
            self.block_publishing = False

            # Update connection control buttons
            self.drop_btn.config(state=NORMAL)
            self.reconnect_btn.config(state=DISABLED)

            # UI
            if self.reconnecting and not self.manual_offline:
                self.ui_status("Status: Reconnected to broker")
            else:
                self.ui_status("Status: Connected to broker")

            print(f"[{self.device_id}] Connected: reason_code={reason_code}")
            self.reconnecting = False

            # ONLINE status (retained)
            self.publish_status("ONLINE")
        else:
            self.ui_status(f"Status: Connect failed ({reason_code})")
            print(f"[{self.device_id}] Connect failed: reason_code={reason_code}")

    # MQTT on_disconnect callback
    def on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self.connected = False
        self.ui_status(f"Status: Disconnected (rc={reason_code})")
        print(f"[{self.device_id}] Disconnected: rc={reason_code}")

        if self.manual_offline:
            self.reconnecting = False
            self.reconnect_btn.config(state=NORMAL)
            return

        self.reconnecting = True

        if self.running and self.auto_reconnect:
            delay = min(30, 2 ** self._retries)
            self._retries += 1
            print(f"[{self.device_id}] Reconnecting in {delay}s...")
            t = threading.Timer(delay, self._try_reconnect)
            t.daemon = True
            t.start()

    # ------------------------ Start/Stop -------------------------
    def start_publishing(self):
        if not self.connected and not self.manual_offline:
            self.connect_to_broker()

        # push current UI parameters into the generator
        self.generator.update_parameters(
            base=self.base_var.get(),
            amplitude=self.amp_var.get(),
            frequency=self.freq_var.get(),
            noise=self.noise_var.get()
        )

        # Apply wild/corrupt data settings from checkboxes
        self.generator.set_wild_enabled(self.wild_var.get())
        self.generator.set_corrupt_enabled(self.corrupt_var.get())

        # Running and update UI
        self.running = True
        self.ui_status("Status: Publishing...")
        self.start_btn.config(state=DISABLED)
        self.stop_btn.config(state=NORMAL)

        # clear any previous STOPPED state for subscribers
        self.publish_status("ONLINE")

        thread = threading.Thread(target=self.publish_loop, daemon=True)
        thread.start()

    def stop_publishing(self):
        self.running = False
        self.start_btn.config(state=NORMAL)
        self.stop_btn.config(state=DISABLED)
        self.ui_status("Status: Stopped")

        # announce STOPPED while staying connected
        self.publish_status("STOPPED")

    # ----------------------- Publish loop with blackout bursts -----------------------
    def publish_loop(self):
        while self.running:
            time.sleep(PUBLISH_INTERVAL)

            if self.block_publishing:
                continue

            if not self.connected:
                print(f"[{self.device_id}] Not connected, skipping this cycle.")
                continue

            if self.blackout_active:
                self.blackout_remaining -= 1
                print(f"[{self.device_id}] Blackout… {self.blackout_remaining} sends left to skip.")
                if self.blackout_remaining <= 0:
                    self.blackout_active = False
                    print(f"[{self.device_id}] Blackout ended.")
                continue

            if rand01() < self.miss_rate:
                print(f"[{self.device_id}] Simulated: skipping this single transmission.")
                continue

            if rand01() < self.blackout_chance and not self.blackout_active:
                self.start_blackout()
                continue

            value = self.generator.get_value()
            payload = self.packager.package(value)
            info = self.client.publish(TOPIC_DATA, payload, qos=QOS)

            if info.rc == mqtt.MQTT_ERR_SUCCESS:
                info.wait_for_publish(timeout=3)
                if info.is_published():
                    print(f"[{self.device_id}] Published: {payload}")
                else:
                    print(f"[{self.device_id}] Publish not acknowledged (likely offline).")
            else:
                print(f"[{self.device_id}] Publish failed with rc={info.rc}")

    def start_blackout(self):
        self.blackout_active = True
        self.blackout_remaining = random.randint(self.blackout_min, self.blackout_max)
        print(f"[{self.device_id}] Starting blackout for {self.blackout_remaining} sends.")

    # ---------------------- Maintenance mode --------------------
    def go_offline(self):
        self.block_publishing = True
        self.manual_offline = True
        self.reconnecting = False
        self.ui_status("Status: OFFLINE (manual) — no auto-reconnect")

        try:
            if self.client:
                self.publish_status("OFFLINE")
                self.client.disconnect()
        except Exception as e:
            print(f"[{self.device_id}] Offline publish/disconnect error: {e}")

        self.connected = False
        self.drop_btn.config(state=DISABLED)
        self.reconnect_btn.config(state=NORMAL)

    def go_online(self):
        self.ui_status("Status: Reconnecting…")
        self.manual_offline = False
        try:
            if self.client is None:
                self.setup_client()
            self.client.connect(BROKER, PORT, keepalive=KEEPALIVE)
            self.client.loop_start()
        except Exception as e:
            print(f"[{self.device_id}] Reconnect error: {e}")
            self.ui_status(f"Status: Reconnect failed: {e}")

    def _try_reconnect(self):
        if self.manual_offline:
            return
        try:
            if self.client is None:
                self.setup_client()
            try:
                self.client.reconnect()
            except Exception:
                self.client.connect(BROKER, PORT, keepalive=KEEPALIVE)
                self.client.loop_start()
        except Exception as e:
            print(f"[{self.device_id}] Reconnect attempt failed: {e}")
            if self.running and self.auto_reconnect and not self.manual_offline:
                delay = min(30, 2 ** self._retries)
                self._retries += 1
                t = threading.Timer(delay, self._try_reconnect)
                t.daemon = True
                t.start()

    # ----------------------- Cleanup -----------------------
    def on_closing(self):
        self.stop_publishing()
        try:
            if self.client and self.connected:
                self.publish_status("OFFLINE")
        except Exception:
            pass

        if self.client:
            try: self.client.loop_stop()
            except Exception: pass
            try: self.client.disconnect()
            except Exception: pass

        self.master.destroy()


if __name__ == "__main__":
    root = Tk()
    app = TemperaturePublisher(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
