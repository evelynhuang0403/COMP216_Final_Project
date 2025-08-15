#Syed

import os
import time
import sqlite3
import csv
import io
import json
import threading
import paho.mqtt.client as mqtt
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, Response, make_response

app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'admin-secret-key')


try:
    from flask_cors import CORS
    CORS(app)
    print("CORS enabled")
except ImportError:
    print("flask_cors not installed. Running without CORS support.")

# Load configuration
CONFIG_PATH = 'group_1_config.json'
if not os.path.exists(CONFIG_PATH):
    print(f"Error: Config file not found at {CONFIG_PATH}")
    # Create a minimal default config
    CFG = {
        "admin": {"db_path": "iot_admin.db", "host": "0.0.0.0", "port": 5050},
        "mqtt": {
            "broker": "broker.hivemq.com",
            "port": 1883,
            "keepalive": 60,
            "topics": {
                "data": "group_1/temp",
                "status": "group_1/status",
                "control": "group_1/control"
            }
        },
        "subscriber": {"allowed_temp_min": 0.0, "allowed_temp_max": 50.0},
        "history": {"retention_days": 30}
    }
    with open(CONFIG_PATH, 'w') as f:
        json.dump(CFG, f, indent=2)
    print("Created default config file")
else:
    with open(CONFIG_PATH) as f:
        CFG = json.load(f)

# Database file path
DB_PATH = CFG["admin"]["db_path"]

# Initialize the database
def init_db():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            
            # Create tables
            c.execute('''
                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT UNIQUE,
                    location TEXT,
                    status TEXT DEFAULT 'online',
                    last_updated REAL
                )
            ''')
            
            c.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT,
                    ts REAL,
                    core_temp REAL,
                    packet_id TEXT,
                    valid INTEGER,
                    schema_ok INTEGER,
                    qos INTEGER,
                    topic TEXT,
                    raw_data TEXT
                )
            ''')
            
            c.execute('''
                CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT,
                    action TEXT,
                    start_ts REAL,
                    end_ts REAL
                )
            ''')
            
            c.execute('''
                CREATE TABLE IF NOT EXISTS service_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT,
                    ts REAL,
                    qos INTEGER,
                    schema_ok INTEGER,
                    log_message TEXT,
                    anomaly_type TEXT
                )
            ''')
            
            c.execute('''
                CREATE TABLE IF NOT EXISTS anomalies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT,
                    ts REAL,
                    anomaly_type TEXT,
                    message TEXT
                )
            ''')
            
            c.execute('''
                CREATE TABLE IF NOT EXISTS mqtt_config (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    version INTEGER DEFAULT 5,
                    qos INTEGER DEFAULT 1,
                    CONSTRAINT config_pk UNIQUE (id)
                )
            ''')
            
            # Insert default MQTT config 
            c.execute('''
                INSERT OR IGNORE INTO mqtt_config (id, version, qos) 
                VALUES (1, 5, 1)
            ''')
            
            # Insert sample devices 
            sample_devices = [
                ('dev001', 'Library', 'online', time.time() - 300),
                ('dev002', 'Lab', 'online', time.time() - 200),
                ('dev003', 'Office', 'paused', time.time() - 600)
            ]
            
            for device in sample_devices:
                c.execute('''
                    INSERT OR IGNORE INTO devices (device_id, location, status, last_updated)
                    VALUES (?, ?, ?, ?)
                ''', device)
            
            # Insert sample anomalies
            sample_anomalies = [
                ('dev001', time.time() - 600, 'WILD', 'Temperature 52.3°C exceeds maximum'),
                ('dev002', time.time() - 300, 'CORRUPT', 'Invalid sensor reading'),
                ('dev003', time.time() - 150, 'WILD', 'Temperature -2.1°C below minimum')
            ]
            
            for anomaly in sample_anomalies:
                c.execute('''
                    INSERT OR IGNORE INTO anomalies (device_id, ts, anomaly_type, message)
                    VALUES (?, ?, ?, ?)
                ''', anomaly)
            
            conn.commit()
    except Exception as e:
        print(f"Error initializing database: {e}")

# Initialize database on startup
init_db()

# Get database connection
def get_db_connection():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return None

# MQTT Admin Bridge
class AdminMQTT:
    """
    Background MQTT bridge:
    - Subscribes to data/status topics
    - Persists messages/statuses and service-level metadata
    - Detects anomalies
    - Publishes control commands
    - Can hot-reconfigure MQTT protocol version and QoS
    """
    def __init__(self, config: dict):
        self.cfg = config
        self.db_path = self.cfg["admin"]["db_path"]
        
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

        self.client: mqtt.Client = None
        self._stop = threading.Event()

        # maintenance timers
        self.retention_days = int(self.cfg.get("history", {}).get("retention_days", 30))
        self._last_purge = 0

        # background scheduler thread
        self._schedule_thread = threading.Thread(target=self._schedule_loop, daemon=True)

    # ------------------ Public API ------------------
    def start(self):
        try:
            self._build_client()
            self.client.connect(self.broker, self.port, keepalive=self.keepalive)
            self.client.loop_start()
            self._schedule_thread.start()
            print(f"[ADMIN] Connected to MQTT broker at {self.broker}:{self.port}")
        except Exception as e:
            print(f"[ADMIN] Connection failed: {str(e)}")

    def stop(self):
        self._stop.set()
        try:
            if self.client:
                self.client.loop_stop()
                self.client.disconnect()
        except Exception as e:
            print(f"[ADMIN] Error stopping: {e}")

    def publish_control(self, device_id: str, payload: dict):
        if not self.client:
            print("[ADMIN] Cannot publish - MQTT client not initialized")
            return
            
        topic = f"{self.control_base}/{device_id}"
        data = json.dumps(payload)
        with self.mqtt_settings_lock:
            qos = self.mqtt_qos
            client = self.client
        if client:
            try:
                client.publish(topic, data, qos=qos)
            except Exception as e:
                print(f"[ADMIN] Publish error: {e}")

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
            except Exception as e:
                print(f"[ADMIN] Error reconfiguring: {e}")
                
            try:
                self._build_client()
                self.client.connect(self.broker, self.port, keepalive=self.keepalive)
                self.client.loop_start()
            except Exception as e:
                print(f"[ADMIN] Reconnect after reconfig failed: {e}")

    # ------------------ Internal ------------------
    def _build_client(self):
        try:
            proto = mqtt.MQTTv5 if self.mqtt_version == 5 else mqtt.MQTTv311
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="group1_admin", protocol=proto)
            self.client.on_connect = self._on_connect
            self.client.on_message = self._on_message
            self.client.on_disconnect = self._on_disconnect
        except Exception as e:
            print(f"[ADMIN] Client build error: {e}")

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
        try:
            ts = time.time()
            topic = msg.topic
            qos = msg.qos
            payload = msg.payload
            log_message = ""
            anomaly_type = None
            schema_ok = False

            if topic == self.status_topic:
                # Status messages
                try:
                    obj = json.loads(payload.decode())
                    device_id = obj.get("device_id")
                    location = obj.get("location")
                    status = obj.get("status")
                    self._insert_status(ts, device_id, location, status)
                    return
                except Exception as e:
                    log_message = f"Status decode error: {e}"
                    anomaly_type = "CORRUPT"
                    self._insert_anomaly(ts, None, anomaly_type, log_message)
                    self._insert_service_log(ts, None, topic, qos, False, log_message, anomaly_type)
                    return

            # Data topic
            device_id = location = None
            core_temp = None
            raw_data = None
            packet_id = None

            try:
                # Try to parse JSON
                obj = json.loads(payload.decode())
                raw_data = json.dumps(obj)  # Store as string
                device_id = obj.get("device_id")
                location = obj.get("location")
                packet_id = obj.get("packet_id", "N/A")
                
                # Validate schema
                if not device_id:
                    raise ValueError("Missing device_id")
                    
                if "sensor_data" not in obj:
                    raise ValueError("Missing sensor_data")
                    
                sensor_data = obj["sensor_data"]
                if not isinstance(sensor_data, dict):
                    raise ValueError("sensor_data should be an object")
                    
                if "value" not in sensor_data:
                    raise ValueError("Missing value in sensor_data")
                    
                # Validate value
                value = sensor_data["value"]
                if value == "SENSOR_FAULT":
                    raise ValueError("Sensor fault detected")
                    
                try:
                    core_temp = float(value)
                    schema_ok = True
                except (TypeError, ValueError):
                    raise ValueError(f"Invalid temperature value: {value}")
                    
                # Validate temperature range
                if core_temp < self.allowed_min or core_temp > self.allowed_max:
                    log_message = f"Temperature {core_temp} outside allowed range ({self.allowed_min}-{self.allowed_max})"
                    anomaly_type = "WILD"
                    self._insert_anomaly(ts, device_id, anomaly_type, log_message)

            except Exception as e:
                # Handle parsing/validation errors
                if not device_id:
                    device_id = "unknown"
                log_message = str(e)
                anomaly_type = "INVALID"
                self._insert_anomaly(ts, device_id, anomaly_type, log_message)
                schema_ok = False
                if not raw_data:
                    raw_data = payload.decode(errors="replace")

            # Store message
            valid = 1 if core_temp is not None and schema_ok else 0
            self._insert_message(
                ts,
                device_id,
                location,
                core_temp,
                packet_id,
                valid,
                schema_ok,
                qos,
                topic,
                raw_data
            )
            
            # Store service log
            self._insert_service_log(
                ts,
                device_id,
                topic,
                qos,
                schema_ok,
                log_message if log_message else "Valid message",
                anomaly_type
            )
        except Exception as e:
            print(f"[ADMIN] Error processing message: {e}")

    def _insert_status(self, ts, device_id, location, status):
        conn = get_db_connection()
        if not conn:
            return
        try:
            conn.execute('''
                INSERT OR REPLACE INTO devices (device_id, location, status, last_updated)
                VALUES (?, ?, ?, ?)
            ''', (device_id, location, status, ts))
            conn.commit()
        except Exception as e:
            print(f"[ADMIN] Error inserting status: {e}")
        finally:
            conn.close()

    def _insert_message(self, ts, device_id, location, core_temp, packet_id, valid, schema_ok, qos, topic, raw_data):
        conn = get_db_connection()
        if not conn:
            return
        try:
            conn.execute('''
                INSERT INTO messages (
                    device_id, ts, core_temp, packet_id, 
                    valid, schema_ok, qos, topic, raw_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                device_id, ts, core_temp, packet_id,
                valid, schema_ok, qos, topic, raw_data
            ))
            conn.commit()
        except Exception as e:
            print(f"[ADMIN] Error inserting message: {e}")
        finally:
            conn.close()

    def _insert_service_log(self, ts, device_id, topic, qos, schema_ok, log_message, anomaly_type):
        conn = get_db_connection()
        if not conn:
            return
        try:
            conn.execute('''
                INSERT INTO service_logs (
                    device_id, ts, topic, qos, 
                    schema_ok, log_message, anomaly_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                device_id, ts, topic, qos,
                schema_ok, log_message, anomaly_type
            ))
            conn.commit()
        except Exception as e:
            print(f"[ADMIN] Error inserting service log: {e}")
        finally:
            conn.close()

    def _insert_anomaly(self, ts, device_id, anomaly_type, message):
        conn = get_db_connection()
        if not conn:
            return
        try:
            conn.execute('''
                INSERT INTO anomalies (device_id, ts, anomaly_type, message)
                VALUES (?, ?, ?, ?)
            ''', (device_id, ts, anomaly_type, message))
            conn.commit()
        except Exception as e:
            print(f"[ADMIN] Error inserting anomaly: {e}")
        finally:
            conn.close()

    def _get_schedules(self):
        conn = get_db_connection()
        if not conn:
            return []
        try:
            schedules = conn.execute('SELECT * FROM schedules').fetchall()
            return [dict(sched) for sched in schedules]
        except Exception as e:
            print(f"[ADMIN] Error getting schedules: {e}")
            return []
        finally:
            conn.close()

    def _purge_old_data(self):
        cutoff = time.time() - (self.retention_days * 24 * 3600)
        conn = get_db_connection()
        if not conn:
            return
        try:
            conn.execute('DELETE FROM messages WHERE ts < ?', (cutoff,))
            conn.execute('DELETE FROM service_logs WHERE ts < ?', (cutoff,))
            conn.execute('DELETE FROM anomalies WHERE ts < ?', (cutoff,))
            conn.commit()
        except Exception as e:
            print(f"[ADMIN] Purge error: {e}")
        finally:
            conn.close()

    def _schedule_loop(self):
        """Periodically executes schedules and purges old data."""
        while not self._stop.is_set():
            now = time.time()

            # Execute schedules
            try:
                schedules = self._get_schedules()
                for s in schedules:
                    start_ts, end_ts = s["start_ts"], s["end_ts"]
                    if start_ts <= now <= end_ts:
                        self.publish_control(s["device_id"], {"action": s["action"]})
                        # Debounce by extending the start time
                        conn = get_db_connection()
                        if conn:
                            try:
                                conn.execute('''
                                    UPDATE schedules
                                    SET start_ts = ?
                                    WHERE id = ?
                                ''', (now + 3600 * 24 * 365, s["id"]))
                                conn.commit()
                            except Exception as e:
                                print(f"[ADMIN] Schedule update error: {e}")
                            finally:
                                conn.close()
                time.sleep(1.0)
            except Exception as e:
                print("[ADMIN] schedule loop error:", e)

            # Purge old data periodically
            if now - self._last_purge > 6 * 3600:
                try:
                    self._purge_old_data()
                    self._last_purge = now
                except Exception as e:
                    print("[ADMIN] purge error:", e)

# Initialize MQTT bridge
admin_mqtt = AdminMQTT(CFG)
admin_mqtt.start()

# API Routes
@app.route('/')
def index():
    return send_from_directory('templates', 'admin_console.html')

@app.route('/api/health')
def api_health():
    return jsonify({'ok': True, 'time': time.time()})

@app.route('/api/devices')
def api_devices():
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    try:
        devices = conn.execute('SELECT * FROM devices').fetchall()
        return jsonify([dict(device) for device in devices])
    except Exception as e:
        print(f"Error loading devices: {e}")
        return jsonify([])
    finally:
        conn.close()

@app.route('/api/messages')
def api_messages():
    device_id = request.args.get('device_id')
    since = request.args.get('since', type=float)
    until = request.args.get('until', type=float)
    limit = request.args.get('limit', default=200, type=int)
    
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    
    try:
        query = 'SELECT * FROM messages WHERE 1=1'
        params = []
        
        if device_id:
            query += ' AND device_id = ?'
            params.append(device_id)
        
        if since:
            query += ' AND ts >= ?'
            params.append(since)
        
        if until:
            query += ' AND ts <= ?'
            params.append(until)
        
        query += ' ORDER BY ts DESC LIMIT ?'
        params.append(limit)
        
        messages = conn.execute(query, params).fetchall()
        
        # If no messages, return sample data
        if len(messages) == 0:
            sample_ts = time.time()
            device = device_id or "dev001"
            return jsonify([
                {"ts": sample_ts - 30, "core_temp": 22.5, "device_id": device, "location": "Sample Location"},
                {"ts": sample_ts - 25, "core_temp": 23.1, "device_id": device, "location": "Sample Location"},
                {"ts": sample_ts - 20, "core_temp": 22.8, "device_id": device, "location": "Sample Location"},
                {"ts": sample_ts - 15, "core_temp": 23.5, "device_id": device, "location": "Sample Location"},
                {"ts": sample_ts - 10, "core_temp": 24.0, "device_id": device, "location": "Sample Location"},
            ])
        
        # Convert to list of dicts with UI-compatible field names
        messages_list = []
        for msg in messages:
            messages_list.append({
                "ts": msg["ts"],
                "core_temp": msg["core_temp"],
                "device_id": msg["device_id"],
                "location": msg["location"]
            })
        return jsonify(messages_list)
    except Exception as e:
        print(f"Error fetching messages: {e}")
        return jsonify([])
    finally:
        conn.close()

@app.route('/api/anomalies')
def api_anomalies():
    limit = request.args.get('limit', default=10, type=int)
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    try:
        anomalies = conn.execute('''
            SELECT * FROM anomalies 
            ORDER BY ts DESC 
            LIMIT ?
        ''', (limit,)).fetchall()
        return jsonify([dict(anom) for anom in anomalies])
    except Exception as e:
        print(f"Error fetching anomalies: {e}")
        return jsonify([])
    finally:
        conn.close()

@app.route('/api/anomalies.csv')
def api_anomalies_csv():
    limit = request.args.get('limit', default=10, type=int)
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    try:
        anomalies = conn.execute('''
            SELECT * FROM anomalies 
            ORDER BY ts DESC 
            LIMIT ?
        ''', (limit,)).fetchall()
        
        # Create CSV output
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['id', 'device_id', 'timestamp', 'anomaly_type', 'message'])
        
        # Write data
        for anom in anomalies:
            writer.writerow([
                anom['id'],
                anom['device_id'],
                datetime.fromtimestamp(anom['ts']).isoformat(),
                anom['anomaly_type'],
                anom['message']
            ])
        
        # Create response
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=anomalies-{int(time.time())}.csv'
        return response
    except Exception as e:
        print(f"Error generating CSV: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/stats')
def api_stats():
    device_id = request.args.get('device_id')
    since = request.args.get('since', type=float)
    until = request.args.get('until', type=float)
    
    conn = get_db_connection()
    if not conn:
        return jsonify({})
    try:
        query = '''
            SELECT 
                COUNT(*) as total_messages,
                AVG(core_temp) as avg_temperature,
                SUM(CASE WHEN valid = 0 THEN 1 ELSE 0 END) as invalid_count,
                SUM(CASE WHEN schema_ok = 0 THEN 1 ELSE 0 END) as schema_invalid_count
            FROM messages
            WHERE 1=1
        '''
        params = []
        
        if device_id:
            query += ' AND device_id = ?'
            params.append(device_id)
        
        if since:
            query += ' AND ts >= ?'
            params.append(since)
        
        if until:
            query += ' AND ts <= ?'
            params.append(until)
        
        stats = conn.execute(query, params).fetchone()
        return jsonify({
            "total_messages": stats['total_messages'] or 0,
            "avg_temperature": stats['avg_temperature'] or 0,
            "invalid_count": stats['invalid_count'] or 0,
            "schema_invalid_count": stats['schema_invalid_count'] or 0
        })
    except Exception as e:
        print(f"Error fetching stats: {e}")
        return jsonify({})
    finally:
        conn.close()

@app.route('/api/schedule', methods=['GET', 'POST'])
def api_schedule():
    if request.method == 'GET':
        conn = get_db_connection()
        if not conn:
            return jsonify([])
        try:
            schedules = conn.execute('SELECT * FROM schedules').fetchall()
            return jsonify([dict(sched) for sched in schedules])
        except Exception as e:
            print(f"Error fetching schedules: {e}")
            return jsonify([])
        finally:
            conn.close()
    
    elif request.method == 'POST':
        data = request.get_json()
        device_id = data.get('device_id')
        action = data.get('action')
        start_in = data.get('start_in', 0)
        duration = data.get('duration', 60)
        
        if not device_id or not action:
            return jsonify({'error': 'Missing device_id or action'}), 400
        
        # Calculate timestamps
        start_ts = time.time() + start_in
        end_ts = start_ts + duration
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database error'}), 500
        try:
            conn.execute('''
                INSERT INTO schedules (device_id, action, start_ts, end_ts)
                VALUES (?, ?, ?, ?)
            ''', (device_id, action, start_ts, end_ts))
            conn.commit()
            return jsonify({'status': 'success', 'message': 'Schedule added'})
        except Exception as e:
            print(f"Error adding schedule: {e}")
            return jsonify({'error': str(e)}), 500
        finally:
            conn.close()

@app.route('/api/control', methods=['POST'])
def api_control():
    data = request.get_json()
    device_id = data.get('device_id')
    action = data.get('action')
    version = data.get('version')
    qos = data.get('qos')
    
    # Validate input
    if not device_id or not action:
        return jsonify({'error': 'Missing device_id or action'}), 400
    
    # Send control command via MQTT
    admin_mqtt.publish_control(device_id, {
        'action': action,
        'version': version,
        'qos': qos
    })
    
    return jsonify({
        'status': 'success', 
        'message': f'Control command sent to {device_id}'
    })

@app.route('/api/mqttconfig', methods=['POST'])
def api_mqttconfig():
    data = request.get_json()
    version = data.get('version')
    qos = data.get('qos')
    
    if version is None or qos is None:
        return jsonify({'error': 'Missing version or qos'}), 400
    
    # Update MQTT settings
    admin_mqtt.update_mqtt_settings(version, qos)
    
    # Update database
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database error'}), 500
    try:
        conn.execute('''
            UPDATE mqtt_config 
            SET version = ?, qos = ?
            WHERE id = 1
        ''', (version, qos))
        conn.commit()
        return jsonify({
            'status': 'success',
            'message': 'MQTT configuration updated',
            'version': version,
            'qos': qos
        })
    except Exception as e:
        print(f"Error updating MQTT config: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/service_logs')
def api_service_logs():
    limit = request.args.get('limit', default=30, type=int)
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    try:
        logs = conn.execute('''
            SELECT * FROM service_logs 
            ORDER BY ts DESC 
            LIMIT ?
        ''', (limit,)).fetchall()
        return jsonify([dict(log) for log in logs])
    except Exception as e:
        print(f"Error fetching service logs: {e}")
        return jsonify([])
    finally:
        conn.close()

if __name__ == '__main__':
    try:
        host = CFG["admin"].get("host", "0.0.0.0")
        port = int(CFG["admin"].get("port", 5050))
        app.run(host=host, port=port, debug=True)
    except Exception as e:
        print(f"Failed to start server: {e}")