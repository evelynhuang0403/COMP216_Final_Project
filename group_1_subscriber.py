import json
import time
import threading
from datetime import datetime, timedelta
from tkinter import *
from tkinter import ttk, scrolledtext
import paho.mqtt.client as mqtt


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


class TemperatureSubscriber:
    def __init__(self, master):
        self.master = master
        self.master.title("Group 1 - IoT Subscriber Monitor")
        self.master.geometry("800x600")
        
        self.client = None
        self.connected = False
        self.running = False
        
        # Device monitoring state
        self.device_states = {}  # device_id -> {last_data_time, status, location, last_value}
        self.data_timeout_timer = None
        
        # UI variables
        self.status_text = StringVar(value="Status: Disconnected")
        self.devices_tree = None
        self.log_text = None
        
        self.setup_ui()
        self.setup_monitoring_timer()
    
    def setup_ui(self):
        # Main frame
        main_frame = Frame(self.master)
        main_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)
        
        # Status frame
        status_frame = Frame(main_frame)
        status_frame.pack(fill=X, pady=(0, 10))
        
        status_label = Label(status_frame, textvariable=self.status_text, font=("Arial", 12, "bold"))
        status_label.pack(side=LEFT)
        
        # Control buttons
        button_frame = Frame(status_frame)
        button_frame.pack(side=RIGHT)
        
        self.connect_btn = Button(button_frame, text="Connect", command=self.connect_to_broker, 
                                bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
        self.connect_btn.pack(side=LEFT, padx=(0, 5))
        
        self.disconnect_btn = Button(button_frame, text="Disconnect", command=self.disconnect_from_broker,
                                   bg="#f44336", fg="white", font=("Arial", 10, "bold"), state=DISABLED)
        self.disconnect_btn.pack(side=LEFT)
        
        # Device status frame
        device_frame = LabelFrame(main_frame, text="Device Status", font=("Arial", 11, "bold"))
        device_frame.pack(fill=BOTH, expand=True, pady=(0, 10))
        
        # Device tree view
        columns = ("Device ID", "Location", "Status", "Last Value", "Last Data", "Alert")
        self.devices_tree = ttk.Treeview(device_frame, columns=columns, show="headings", height=8)
        
        for col in columns:
            self.devices_tree.heading(col, text=col)
            if col == "Alert":
                self.devices_tree.column(col, width=120)
            elif col == "Last Data":
                self.devices_tree.column(col, width=150)
            else:
                self.devices_tree.column(col, width=120)
        
        scrollbar_tree = Scrollbar(device_frame, orient=VERTICAL, command=self.devices_tree.yview)
        self.devices_tree.configure(yscrollcommand=scrollbar_tree.set)
        
        self.devices_tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar_tree.pack(side=RIGHT, fill=Y)
        
        # Log frame
        log_frame = LabelFrame(main_frame, text="Activity Log", font=("Arial", 11, "bold"))
        log_frame.pack(fill=BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, font=("Consolas", 9))
        self.log_text.pack(fill=BOTH, expand=True, padx=5, pady=5)
    
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
                self.status_text.set(text)
            self.master.after(0, _set)
        except Exception:
            pass
    
    def setup_client(self):
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
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
            self.ui_status("Status: Connecting...")
            self.log_message("Attempting to connect to broker...")
        except Exception as e:
            self.ui_status(f"Status: Connect error: {e}")
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
        self.ui_status("Status: Disconnected")
        self.log_message("Disconnected from broker")
        
        self.connect_btn.config(state=NORMAL)
        self.disconnect_btn.config(state=DISABLED)
    
    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            self.connected = True
            self.running = True
            self.ui_status("Status: Connected - Monitoring devices")
            self.log_message("Connected to broker successfully")
            
            # Subscribe to both data and status topics
            self.client.subscribe(TOPIC_DATA, qos=QOS)
            self.client.subscribe(TOPIC_STATUS, qos=QOS)
            
            self.log_message(f"Subscribed to data topic: {TOPIC_DATA}")
            self.log_message(f"Subscribed to status topic: {TOPIC_STATUS}")
            
            self.connect_btn.config(state=DISABLED)
            self.disconnect_btn.config(state=NORMAL)
        else:
            self.ui_status(f"Status: Connect failed ({reason_code})")
            self.log_message(f"Connection failed with reason code: {reason_code}")
    
    def on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self.connected = False
        self.ui_status(f"Status: Disconnected (rc={reason_code})")
        self.log_message(f"Disconnected from broker (reason code: {reason_code})")
        
        self.connect_btn.config(state=NORMAL)
        self.disconnect_btn.config(state=DISABLED)
    
    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            topic = msg.topic
            
            if topic == TOPIC_DATA:
                self.handle_data_message(payload)
            elif topic == TOPIC_STATUS:
                self.handle_status_message(payload)
                
        except json.JSONDecodeError as e:
            self.log_message(f"Failed to decode JSON message: {e}")
        except Exception as e:
            self.log_message(f"Error processing message: {e}")
    
    def handle_data_message(self, data):
        device_id = data.get("device_id", "unknown")
        location = data.get("location", "unknown")
        sensor_data = data.get("sensor_data", {})
        value = sensor_data.get("value", 0)
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
        
        # Check for out-of-range data
        alert = ""
        if not (NORMAL_TEMP_MIN <= value <= NORMAL_TEMP_MAX):
            alert = "OUT OF RANGE"
            self.log_message(f"🚨 {device_id}: Temperature {value}°C is out of normal range ({NORMAL_TEMP_MIN}-{NORMAL_TEMP_MAX}°C)")
        
        self.device_states[device_id]["alert"] = alert
        
        self.log_message(f"📊 Data from {device_id} ({location}): {value}°C")
        self.update_device_display()
    
    def handle_status_message(self, status_data):
        device_id = status_data.get("device_id", "unknown")
        location = status_data.get("location", "unknown")
        status = status_data.get("status", "UNKNOWN")
        
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
            self.device_states[device_id]["status"] = status
            self.device_states[device_id]["location"] = location
        
        if status == "OFFLINE":
            self.device_states[device_id]["alert"] = "NETWORK DROP"
            self.log_message(f"🔴 {device_id}: Device went OFFLINE (Network Drop/LWT)")
        elif status == "ONLINE":
            self.device_states[device_id]["alert"] = ""
            self.log_message(f"🟢 {device_id}: Device is ONLINE")
        
        self.update_device_display()
    
    def setup_monitoring_timer(self):
        def check_no_data_feed():
            if not self.running:
                return
            
            current_time = time.time()
            
            for device_id, state in self.device_states.items():
                if state["status"] == "ONLINE" and state["last_data_time"]:
                    time_since_last_data = current_time - state["last_data_time"]
                    
                    if time_since_last_data > NO_DATA_TIMEOUT:
                        if state["alert"] != "NO DATA FEED":
                            state["alert"] = "NO DATA FEED"
                            self.log_message(f"⚠️ {device_id}: No data feed detected (no data for {int(time_since_last_data)}s)")
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
                    
                    # Color coding for alerts
                    if alert == "NETWORK DROP":
                        self.devices_tree.set(item, "Alert", "🔴 NETWORK DROP")
                    elif alert == "NO DATA FEED":
                        self.devices_tree.set(item, "Alert", "⚠️ NO DATA FEED")
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