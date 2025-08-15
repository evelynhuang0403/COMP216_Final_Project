# group_1_admin_mqtt.py
#Syed
import json
import time
import threading
from typing import Optional
import paho.mqtt.client as mqtt
from group_1_storage import (
    init_db, insert_message, insert_anomaly, insert_status,
    get_schedules, purge_old_data
)

class AdminMQTT:
    """
    Background MQTT bridge:
    - Subscribes to data/status topics
    - Persists messages/statuses and service-level metadata (QoS, schema_ok)
    - Detects anomalies (wild/corrupt values, schema errors)
    - Publishes control commands (pause/resume/shutdown/reconfig) on schedule or on demand
    - Can hot-reconfigure MQTT protocol version and QoS
    """
    def __init__(self, config: dict):
        self.cfg = config
        self.db_path = self.cfg["admin"]["db_path"]
        init_db(self.db_path)

        # thresholds for "wild" data detection
        self.allowed_min = self.cfg.get("subscriber", {}).get("allowed_temp_min", 0)
        self.allowed_max = self.cfg.get("subscriber", {}).get("allowed_temp_max", 50)

        # mqtt settings
        self.mqtt_settings_lock = threading.Lock()
        self.mqtt_version = int(self.cfg.get("mqtt", {}).get("version", 5))
        self.mqtt_qos = int(self.cfg.get("mqtt", {}).get("qos", 1))
        self.broker = self.cfg["mqtt"]["broker"]
        self.port = int(self.cfg["mqtt"]["port"])
        self.keepalive = int(self.cfg["mqtt"]["keepalive"])
        self.topics = self.cfg["mqtt"]["topics"]
        self.data_topic = self.topics["data"]
        self.status_topic = self.topics["status"]
        self.control_base = self.topics["control"]

        self.client: Optional[mqtt.Client] = None
        self._stop = threading.Event()

        # maintenance timers
        self.retention_days = int(self.cfg.get("history", {}).get("retention_days", 30))
        self._last_purge = 0

        # background scheduler thread
        self._schedule_thread = threading.Thread(target=self._schedule_loop, daemon=True)

    # ------------------ Public API ------------------
    def start(self):
        self._build_client()
        self.client.connect(self.broker, self.port, keepalive=self.keepalive)
        self.client.loop_start()
        self._schedule_thread.start()

    def stop(self):
        self._stop.set()
        try:
            if self.client:
                self.client.loop_stop()
                self.client.disconnect()
        except Exception:
            pass

    def publish_control(self, device_id: str, payload: dict):
        topic = f"{self.control_base}/{device_id}"
        data = json.dumps(payload)
        with self.mqtt_settings_lock:
            qos = self.mqtt_qos
            client = self.client
        if client:
            client.publish(topic, data, qos=qos)

    def update_mqtt_settings(self, version: int, qos: int):
        """Hot-reconfigure admin bridge (v3.1.1 or v5) and QoS."""
        with self.mqtt_settings_lock:
            self.mqtt_version = 5 if int(version) == 5 else 3
            self.mqtt_qos = qos if qos in (0, 1, 2) else 0

            # rebuild client
            try:
                if self.client:
                    self.client.loop_stop()
                    self.client.disconnect()
            except Exception:
                pass
            self._build_client()
            self.client.connect(self.broker, self.port, keepalive=self.keepalive)
            self.client.loop_start()

    # ------------------ Internal ------------------
    def _build_client(self):
        proto = mqtt.MQTTv5 if self.mqtt_version == 5 else mqtt.MQTTv311
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="group1_admin", protocol=proto)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            try:
                client.subscribe(self.data_topic, qos=self.mqtt_qos)
                client.subscribe(self.status_topic, qos=self.mqtt_qos)
            except Exception as e:
                print("[ADMIN] Subscribe error:", e)
            print(f"[ADMIN] Connected. Subscribed to {self.data_topic} and {self.status_topic}")
        else:
            print(f"[ADMIN] Connect failed rc={reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        print(f"[ADMIN] Disconnected rc={reason_code}")

    def _on_message(self, client, userdata, msg):
        ts = time.time()
        topic = msg.topic
        qos = msg.qos
        payload = msg.payload

        if topic == self.status_topic:
            # Status messages
            try:
                obj = json.loads(payload.decode())
                device_id = obj.get("device_id")
                location = obj.get("location")
                status = obj.get("status")
                insert_status(self.db_path, ts, device_id, location, status)
            except Exception as e:
                insert_anomaly(self.db_path, ts, None, "CORRUPT", f"Status decode error: {e}")
            return

        # Data topic
        schema_ok = False
        device_id = location = None
        core_temp = None
        raw_data = None

        try:
            obj = json.loads(payload.decode())
            device_id = obj.get("device_id")
            location = obj.get("location")
            raw_data = obj

            # Extract temperature
            if "sensor_data" in obj and isinstance(obj["sensor_data"], dict):
                val = obj["sensor_data"].get("value")
                try:
                    if val is not None and val != "SENSOR_FAULT":
                        core_temp = float(val)
                        schema_ok = True
                    else:
                        core_temp = None
                        schema_ok = False
                except (ValueError, TypeError):
                    core_temp = None
                    schema_ok = False
            else:
                schema_ok = False

        except Exception as e:
            core_temp = None
            raw_data = {"_raw": payload.decode(errors="replace")}
            schema_ok = False
            insert_anomaly(self.db_path, ts, None, "CORRUPT", f"JSON decode error: {e}")

        # Wild value detection
        if schema_ok and core_temp is not None:
            if core_temp < self.allowed_min or core_temp > self.allowed_max:
                insert_anomaly(
                    self.db_path,
                    ts,
                    device_id,
                    "WILD",
                    f"Temperature {core_temp} outside allowed range ({self.allowed_min}-{self.allowed_max})"
                )

        # Store message
        insert_message(
            self.db_path,
            ts,
            device_id,
            location,
            core_temp,
            raw_data,
            topic,
            qos,
            schema_ok
        )

    def _schedule_loop(self):
        """Periodically executes schedules and purges old data."""
        while not self._stop.is_set():
            now = time.time()

            # Execute schedules
            try:
                schedules = get_schedules(self.db_path)
                for s in schedules:
                    start_ts, end_ts = s["start_ts"], s["end_ts"]
                    if start_ts <= now <= end_ts:
                        self.publish_control(s["device_id"], {"action": s["action"]})
                        s["start_ts"] = now + 3600 * 24 * 365  # Debounce
                time.sleep(1.0)
            except Exception as e:
                print("[ADMIN] schedule loop error:", e)

            # Purge old data periodically
            if now - self._last_purge > 6 * 3600:
                try:
                    purge_old_data(self.db_path, self.retention_days)
                    self._last_purge = now
                except Exception as e:
                    print("[ADMIN] purge error:", e)
