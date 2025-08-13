import json
import time
import threading
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from tkinter import Tk, Frame, Label, Button, StringVar, BooleanVar, BOTH, X, Y, LEFT, RIGHT, END, DISABLED, NORMAL, WORD, VERTICAL
from tkinter import ttk, scrolledtext
import paho.mqtt.client as mqtt
from typing import Optional, Dict, Any
from group_1_alert_manager import AlertManager

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

BROKER = CFG.get("mqtt", {}).get("broker", "broker.hivemq.com")
PORT = CFG.get("mqtt", {}).get("port", 1883)
KEEPALIVE = CFG.get("mqtt", {}).get("keepalive", 15)
QOS = CFG.get("mqtt", {}).get("qos", 1)

TOPIC_DATA = CFG.get("mqtt", {}).get("topics", {}).get("data", "group_1/temp")
TOPIC_STATUS = CFG.get("mqtt", {}).get("topics", {}).get("status", "group_1/status")

NO_DATA_TIMEOUT = 10  # seconds to detect no data feed
NORMAL_TEMP_MIN = 18.0
NORMAL_TEMP_MAX = 28.0

# Email configuration
EMAIL_CONFIG = {
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "sender_email": "iot.monitor@example.com",
    "sender_password": "your_app_password",
    "recipient_email": "admin@example.com",
    "enabled": False  # Set to True to enable email notifications
}


def setup_style():
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass

    # Fonts & paddings
    style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"))
    style.configure("SubHeader.TLabel", font=("Segoe UI", 11, "bold"))
    style.configure("TLabel", font=("Segoe UI", 10))
    style.configure("TEntry", padding=4)
    style.configure("TButton", padding=(8, 6))
    style.configure("TCheckbutton", padding=4)

    # Group frames
    style.configure("Group.TLabelframe", padding=10)
    style.configure("Group.TLabelframe.Label", font=("Segoe UI", 10, "bold"))

    # Status bar (bigger & bold)
    style.configure("Status.TLabel", font=("Segoe UI", 12, "bold"))
    
    # Treeview styling
    style.configure("Treeview", font=("Segoe UI", 9))
    style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))


class TemperatureSubscriber:
    def __init__(self, master):
        self.master = master
        self.alert_manager = AlertManager()
        self.master.title("Group 1 - IoT Subscriber Monitor")
        self.master.geometry("900x700")
        
        self.client: Optional[mqtt.Client] = None
        self.connected = False
        self.running = False
        
        # Device monitoring state
        self.device_states: Dict[str, Dict[str, Any]] = {}  # device_id -> {last_data_time, status, location, last_value}
        self.data_timeout_timer = None
        
        # UI variables
        self.status_text = StringVar(value="Status: Disconnected")
        self.devices_tree: Optional[ttk.Treeview] = None
        self.log_text: Optional[scrolledtext.ScrolledText] = None
        
        # Connection status variables
        self.broker_info = StringVar(value=f"Broker: {BROKER}:{PORT}")
        self.topic_info = StringVar(value=f"Topics: {TOPIC_DATA}, {TOPIC_STATUS}")
        
        # Email notification tracking
        self.last_email_sent = {}  # device_id -> timestamp to prevent spam
        self.email_cooldown = 300  # 5 minutes between emails for same device/issue
        
        setup_style()
        self.setup_ui()
        self.setup_monitoring_timer()
    
    def send_email_notification(self, subject, message, device_id, alert_type):
        """Send email notification for critical alerts"""
        if not EMAIL_CONFIG["enabled"]:
            return
            
        # Check cooldown to prevent spam
        current_time = time.time()
        cooldown_key = f"{device_id}_{alert_type}"
        
        if cooldown_key in self.last_email_sent:
            if current_time - self.last_email_sent[cooldown_key] < self.email_cooldown:
                return  # Still in cooldown period
        
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = EMAIL_CONFIG["sender_email"]
            msg['To'] = EMAIL_CONFIG["recipient_email"]
            msg['Subject'] = f"IoT Alert: {subject}"
            
            # Email body
            body = f"""
IoT Monitoring System Alert

Device ID: {device_id}
Alert Type: {alert_type}
Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Details:
{message}

This is an automated alert from the IoT Monitoring System.
Please investigate the issue promptly.

---
Group 1 IoT Subscriber Monitor
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Send email
            server = smtplib.SMTP(EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"])
            server.starttls()
            server.login(EMAIL_CONFIG["sender_email"], EMAIL_CONFIG["sender_password"])
            text = msg.as_string()
            server.sendmail(EMAIL_CONFIG["sender_email"], EMAIL_CONFIG["recipient_email"], text)
            server.quit()
            
            # Update cooldown
            self.last_email_sent[cooldown_key] = current_time
            self.log_message(f"📧 Email notification sent for {device_id}: {alert_type}")
            
        except Exception as e:
            self.log_message(f"❌ Failed to send email notification: {e}")
    
    def setup_ui(self):
        # Root container with nice padding and column stretch
        container = ttk.Frame(self.master, padding=12)
        container.grid(sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=1)

        # Title
        title = ttk.Label(container, text="Group 1 — IoT Subscriber Monitor", style="Header.TLabel")
        title.grid(column=0, row=0, columnspan=2, sticky="w", pady=(0, 10))

        # Connection info (compact header row)
        info = ttk.Frame(container)
        info.grid(column=0, row=1, columnspan=2, sticky="ew", pady=(0, 10))
        info.columnconfigure(0, weight=1)
        info.columnconfigure(1, weight=1)

        ttk.Label(info, textvariable=self.broker_info, style="SubHeader.TLabel").grid(column=0, row=0, sticky="w")
        ttk.Label(info, textvariable=self.topic_info, style="SubHeader.TLabel").grid(column=1, row=0, sticky="e")

        # --- Left column: Connection Controls ---
        conn_frame = ttk.LabelFrame(container, text="Connection", style="Group.TLabelframe")
        conn_frame.grid(column=0, row=2, sticky="nsew", padx=(0, 6))
        conn_frame.columnconfigure(0, weight=1)

        self.connect_btn = ttk.Button(conn_frame, text="Connect to Broker", command=self.connect_to_broker)
        self.connect_btn.grid(column=0, row=0, sticky="ew", pady=2)
        
        self.disconnect_btn = ttk.Button(conn_frame, text="Disconnect", command=self.disconnect_from_broker, state=DISABLED)
        self.disconnect_btn.grid(column=0, row=1, sticky="ew", pady=2)

        # --- Right column: Monitoring Options ---
        right_col = ttk.Frame(container)
        right_col.grid(column=1, row=2, sticky="nsew", padx=(6, 0))
        right_col.columnconfigure(0, weight=1)

        options = ttk.LabelFrame(right_col, text="Monitoring Settings", style="Group.TLabelframe")
        options.grid(column=0, row=0, sticky="ew")
        options.columnconfigure(0, weight=1)

        # Monitoring settings info
        ttk.Label(options, text=f"Data Timeout: {NO_DATA_TIMEOUT}s").grid(column=0, row=0, sticky="w", pady=2)
        ttk.Label(options, text=f"Normal Range: {NORMAL_TEMP_MIN}°C - {NORMAL_TEMP_MAX}°C").grid(column=0, row=1, sticky="w", pady=2)
        ttk.Label(options, text="QoS Level: 1").grid(column=0, row=2, sticky="w", pady=2)
        
        # Email notification status
        email_status = "Enabled" if EMAIL_CONFIG["enabled"] else "Disabled"
        ttk.Label(options, text=f"Email Alerts: {email_status}").grid(column=0, row=3, sticky="w", pady=2)

        # --- Device Status Table (full width) ---
        device_frame = ttk.LabelFrame(container, text="Device Status", style="Group.TLabelframe")
        device_frame.grid(column=0, row=3, columnspan=2, sticky="nsew", pady=(10, 0))
        device_frame.columnconfigure(0, weight=1)
        device_frame.rowconfigure(0, weight=1)
        container.rowconfigure(3, weight=1)

        # Device tree view with modern styling
        columns = ("Device ID", "Location", "Status", "Last Value", "Last Data", "Alert")
        self.devices_tree = ttk.Treeview(device_frame, columns=columns, show="headings", height=8)
        
        for col in columns:
            self.devices_tree.heading(col, text=col)
            if col == "Alert":
                self.devices_tree.column(col, width=140)
            elif col == "Last Data":
                self.devices_tree.column(col, width=120)
            elif col == "Device ID":
                self.devices_tree.column(col, width=100)
            elif col == "Location":
                self.devices_tree.column(col, width=140)
            elif col == "Status":
                self.devices_tree.column(col, width=90)
            else:
                self.devices_tree.column(col, width=100)
        
        scrollbar_tree = ttk.Scrollbar(device_frame, orient=VERTICAL, command=self.devices_tree.yview)
        self.devices_tree.configure(yscrollcommand=scrollbar_tree.set)
        
        self.devices_tree.grid(column=0, row=0, sticky="nsew", padx=(5, 0), pady=5)
        scrollbar_tree.grid(column=1, row=0, sticky="ns", pady=5)

        # --- Activity Log (full width) ---
        log_frame = ttk.LabelFrame(container, text="Activity Log", style="Group.TLabelframe")
        log_frame.grid(column=0, row=4, columnspan=2, sticky="nsew", pady=(10, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        container.rowconfigure(4, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, font=("Consolas", 9), wrap=WORD)
        self.log_text.grid(column=0, row=0, sticky="nsew", padx=5, pady=5)

        # --- Status bar ---
        sep = ttk.Separator(container, orient="horizontal")
        sep.grid(column=0, row=5, columnspan=2, sticky="ew", pady=(12, 6))

        status_bar = ttk.Frame(container)
        status_bar.grid(column=0, row=6, columnspan=2, sticky="ew")
        status_bar.columnconfigure(0, weight=1)
        self.status_lbl = ttk.Label(status_bar, textvariable=self.status_text, style="Status.TLabel", anchor="w")
        self.status_lbl.grid(column=0, row=0, sticky="w")
    
    def log_message(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        try:
            def _log():
                self.log_text.insert(END, log_entry)
                self.log_text.see(END)
            self.master.after(0, _log)
        except Exception:
            pass
    
    def ui_status(self, text: str):
        try:
            def _set():
                self.status_text.set(f"Status: {text}")
            self.master.after(0, _set)
        except Exception:
            pass
    
    def setup_client(self):
        try:
            # Try VERSION2 (newer paho-mqtt)
            self.client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id="group1_subscriber",
                protocol=mqtt.MQTTv5
            )
        except AttributeError:
            # Fallback for older paho-mqtt versions
            self.client = mqtt.Client(
                client_id="group1_subscriber",
                protocol=mqtt.MQTTv5
            )
        
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
    
    def connect_to_broker(self):
        if self.client is None:
            self.setup_client()
        
        try:
            self.client.connect(BROKER, PORT, keepalive=KEEPALIVE)
            self.client.loop_start()
            self.ui_status("Connecting...")
            self.log_message("Attempting to connect to broker...")
        except Exception as e:
            self.ui_status(f"Connect error: {e}")
            self.log_message(f"Connection error: {e}")
    
    def disconnect_from_broker(self):
        self.running = False
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:
                pass
        
        self.connected = False
        self.ui_status("Disconnected")
        self.log_message("Disconnected from broker")
        
        self.connect_btn.config(state=NORMAL)
        self.disconnect_btn.config(state=DISABLED)
    
    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            self.connected = True
            self.running = True
            self.ui_status("Connected - Monitoring devices")
            self.log_message("Connected to broker successfully")
            
            # Subscribe to both data and status topics
            self.client.subscribe(TOPIC_DATA, qos=QOS)
            self.client.subscribe(TOPIC_STATUS, qos=QOS)
            
            self.log_message(f"Subscribed to data topic: {TOPIC_DATA}")
            self.log_message(f"Subscribed to status topic: {TOPIC_STATUS}")
            
            self.connect_btn.config(state=DISABLED)
            self.disconnect_btn.config(state=NORMAL)
        else:
            self.ui_status(f"Connect failed ({reason_code})")
            self.log_message(f"Connection failed with reason code: {reason_code}")
    
    def on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self.connected = False
        self.ui_status(f"Disconnected (rc={reason_code})")
        self.log_message(f"Disconnected from broker (reason code: {reason_code})")
        
        self.connect_btn.config(state=NORMAL)
        self.disconnect_btn.config(state=DISABLED)
    
    def on_message(self, client, userdata, msg):
        try:
            # Enhanced corrupt data handling
            raw_payload = msg.payload.decode('utf-8', errors='replace')
            
            # Check for empty payload
            if not raw_payload.strip():
                self.log_message(f"❌ Corrupt data: Empty payload received from topic {msg.topic}")
                return
                
            payload = json.loads(raw_payload)
            topic = msg.topic
            
            # Validate payload is a dictionary
            if not isinstance(payload, dict):
                self.log_message(f"❌ Corrupt data: Payload is not a JSON object from topic {topic}")
                return
            
            if topic == TOPIC_DATA:
                self.handle_data_message(payload)
            elif topic == TOPIC_STATUS:
                self.handle_status_message(payload)
            else:
                self.log_message(f"⚠️ Received message from unknown topic: {topic}")
                
        except json.JSONDecodeError as e:
            self.log_message(f"❌ Corrupt data: Failed to decode JSON message from topic {msg.topic}: {e}")
            self.log_message(f"❌ Raw payload: {repr(msg.payload)}")
        except UnicodeDecodeError as e:
            self.log_message(f"❌ Corrupt data: Failed to decode message payload as UTF-8: {e}")
        except Exception as e:
            self.log_message(f"❌ Unexpected error processing message from topic {msg.topic}: {e}")
    
    def handle_data_message(self, data):
        # Enhanced validation for required fields
        device_id = data.get("device_id")
        if not device_id:
            self.log_message("❌ Corrupt data: Missing device_id field")
            return
            
        location = data.get("location", "unknown")
        sensor_data = data.get("sensor_data", {})
        
        # Validate sensor_data structure
        if not isinstance(sensor_data, dict):
            self.log_message(f"❌ Corrupt data from {device_id}: sensor_data is not a dictionary")
            return
            
        value = sensor_data.get("value")
        if value is None:
            self.log_message(f"❌ Corrupt data from {device_id}: Missing temperature value")
            return
            
        # Validate value is numeric
        try:
            value = float(value)
        except (ValueError, TypeError):
            self.log_message(f"❌ Corrupt data from {device_id}: Invalid temperature value '{value}'")
            return
            
        timestamp = data.get("timestamp", time.time())
        
        # Update device state
        if device_id not in self.device_states:
            self.device_states[device_id] = {
                "location": location,
                "status": "ONLINE",
                "last_data_time": timestamp,
                "last_value": value,
                "alert": ""
            }
        else:
            self.device_states[device_id].update({
                "location": location,
                "last_data_time": timestamp,
                "last_value": value,
                "alert": ""  # Clear alert when data is received
            })
        
        # Enhanced wild data detection - check for out-of-range data
        alert = ""
        if not (NORMAL_TEMP_MIN <= value <= NORMAL_TEMP_MAX):
            self.alert_manager.send_alert(device_id, location, value, "WILD_DATA")
            if value < NORMAL_TEMP_MIN:
                message = f"Temperature {value}°C is below normal range (min: {NORMAL_TEMP_MIN}°C)"
                self.log_message(f"🚨 {device_id}: WILD DATA - {message}")
            else:
                message = f"Temperature {value}°C is above normal range (max: {NORMAL_TEMP_MAX}°C)"
                self.log_message(f"🚨 {device_id}: WILD DATA - {message}")
        
        # Additional wild data checks for extreme values
        if value < -50 or value > 100:
            self.alert_manager.send_alert(device_id, location, value, "EXTREME_WILD_DATA")
            message = f"Temperature {value}°C is physically impossible for room sensors"
            self.log_message(f"🚨 {device_id}: EXTREME WILD DATA - {message}")
        self.device_states[device_id]["alert"] = alert
        
        # Enhanced normal data logging with more details
        if not alert:
            self.log_message(f"📊 Normal data from {device_id} ({location}): {value}°C - Within range [{NORMAL_TEMP_MIN}-{NORMAL_TEMP_MAX}°C]")
        else:
            self.log_message(f"📊 Data from {device_id} ({location}): {value}°C - FLAGGED: {alert}")
        self.update_device_display()
    
    def handle_status_message(self, status_data):
        # Enhanced validation for status messages
        device_id = status_data.get("device_id")
        if not device_id:
            self.log_message("❌ Corrupt status message: Missing device_id field")
            return
            
        location = status_data.get("location", "unknown")
        status = status_data.get("status", "UNKNOWN")
        
        # Validate status value
        valid_statuses = ["ONLINE", "OFFLINE", "CONNECTING", "DISCONNECTING"]
        if status not in valid_statuses:
            self.log_message(f"⚠️ {device_id}: Unknown status '{status}', treating as UNKNOWN")
            status = "UNKNOWN"
        
        # Initialize device state if not exists
        if device_id not in self.device_states:
            self.device_states[device_id] = {
                "location": location,
                "status": status,
                "last_data_time": None,
                "last_value": None,
                "alert": ""
            }
        else:
            # Update existing device state
            old_status = self.device_states[device_id]["status"]
            self.device_states[device_id]["status"] = status
            self.device_states[device_id]["location"] = location
            
            # Log status transitions
            if old_status != status:
                self.log_message(f"🔄 {device_id}: Status changed from {old_status} to {status}")
        
        # Enhanced network drop detection with LWT handling
        if status == "OFFLINE":
            self.alert_manager.send_alert(device_id, location, "N/A", "NETWORK_DROP")
            message = "Device went OFFLINE - Network Drop detected (likely from LWT - Last Will Testament). This indicates the device lost connection unexpectedly."
            self.log_message(f"🔴 {device_id}: Device went OFFLINE - Network Drop detected (likely from LWT - Last Will Testament)")
            self.log_message(f"🔴 {device_id}: This indicates the device lost connection unexpectedly")
        elif status == "ONLINE":
            # Clear alerts when device comes back online
            old_alert = self.device_states[device_id]["alert"]
            self.device_states[device_id]["alert"] = ""
            if old_alert == "NETWORK DROP":
                self.log_message(f"🟢 {device_id}: Device recovered from NETWORK DROP - Now ONLINE")
            else:
                self.log_message(f"🟢 {device_id}: Device is ONLINE")
        elif status == "CONNECTING":
            self.log_message(f"🟡 {device_id}: Device is attempting to connect")
        elif status == "DISCONNECTING":
            self.log_message(f"🟡 {device_id}: Device is disconnecting gracefully")
        
        self.update_device_display()
    
    def setup_monitoring_timer(self):
        def check_no_data_feed():
            if not self.running:
                return
            
            current_time = time.time()
            
            for device_id, state in self.device_states.items():
                # Enhanced no data feed detection
                if state["status"] == "ONLINE" and state["last_data_time"]:
                    time_since_last_data = current_time - state["last_data_time"]
                    
                    if time_since_last_data > NO_DATA_TIMEOUT:
                        if state["alert"] != "NO DATA FEED":
                            state["alert"] = "NO DATA FEED"
                            message = f"Publisher connected but stopped sending data ({int(time_since_last_data)}s since last data)"
                            self.log_message(f"⚠️ {device_id}: No data feed detected - {message}")
                            self.send_email_notification(f"No Data Feed Alert - {device_id}", message, device_id, "NO_DATA_FEED")
                            self.update_device_display()
                    elif state["alert"] == "NO DATA FEED" and time_since_last_data <= NO_DATA_TIMEOUT:
                        # Clear no data feed alert if data resumes
                        state["alert"] = ""
                        self.log_message(f"✅ {device_id}: Data feed resumed after {int(time_since_last_data)}s")
                        self.update_device_display()
                
                # Check for devices that are ONLINE but never sent data
                elif state["status"] == "ONLINE" and state["last_data_time"] is None:
                    # Device is online but has never sent data - this could indicate a problem
                    if state["alert"] != "NO DATA FEED":
                        state["alert"] = "NO DATA FEED"
                        message = "Device is ONLINE but has never sent data"
                        self.log_message(f"⚠️ {device_id}: {message}")
                        self.send_email_notification(f"No Data Alert - {device_id}", message, device_id, "NO_DATA_FEED")
                        self.update_device_display()
            
            # Schedule next check
            if self.running:
                self.data_timeout_timer = threading.Timer(2.0, check_no_data_feed)
                self.data_timeout_timer.daemon = True
                self.data_timeout_timer.start()
        
        # Start the monitoring
        check_no_data_feed()
    
    def update_device_display(self):
        try:
            def _update():
                # Clear existing items
                for item in self.devices_tree.get_children():
                    self.devices_tree.delete(item)
                
                # Add current device states
                for device_id, state in self.device_states.items():
                    location = state.get("location", "unknown")
                    status = state.get("status", "UNKNOWN")
                    last_value = state.get("last_value")
                    last_data_time = state.get("last_data_time")
                    alert = state.get("alert", "")
                    
                    # Format last value
                    if last_value is not None:
                        value_str = f"{last_value}°C"
                    else:
                        value_str = "No data"
                    
                    # Format last data time
                    if last_data_time:
                        last_data_str = datetime.fromtimestamp(last_data_time).strftime("%H:%M:%S")
                    else:
                        last_data_str = "Never"
                    
                    # Set row color based on alert
                    item = self.devices_tree.insert("", "end", values=(
                        device_id, location, status, value_str, last_data_str, alert
                    ))
                    
                    # Enhanced color coding for alerts
                    if alert == "NETWORK DROP":
                        self.devices_tree.set(item, "Alert", "🔴 NETWORK DROP")
                    elif alert == "NO DATA FEED":
                        self.devices_tree.set(item, "Alert", "⚠️ NO DATA FEED")
                    elif alert == "WILD DATA":
                        self.devices_tree.set(item, "Alert", "🚨 WILD DATA")
                    elif alert == "EXTREME WILD DATA":
                        self.devices_tree.set(item, "Alert", "🔥 EXTREME WILD")
                    elif alert == "OUT OF RANGE":
                        self.devices_tree.set(item, "Alert", "🚨 OUT OF RANGE")
                    elif status == "ONLINE" and not alert:
                        self.devices_tree.set(item, "Alert", "🟢 Normal")
            
            self.master.after(0, _update)
        except Exception as e:
            print(f"Error updating display: {e}")
    
    def on_closing(self):
        self.running = False
        
        if self.data_timeout_timer:
            self.data_timeout_timer.cancel()
        
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:
                pass
        
        self.master.destroy()


if __name__ == "__main__":
    root = Tk()
    app = TemperatureSubscriber(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()