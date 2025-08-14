import json
import time
import threading
import smtplib
import random
import math
from bisect import insort
from collections import deque, defaultdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from tkinter import Tk, StringVar, END, DISABLED, NORMAL, VERTICAL, Canvas
from tkinter import ttk, scrolledtext
import paho.mqtt.client as mqtt
from typing import Optional, Dict, Any, List, Tuple
from group_1_alert_manager import AlertManager


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

# ------------------ MQTT + app config ------------------
BROKER = CFG.get("mqtt", {}).get("broker", "broker.hivemq.com")
PORT = CFG.get("mqtt", {}).get("port", 1883)
KEEPALIVE = CFG.get("mqtt", {}).get("keepalive", 15)
QOS = CFG.get("mqtt", {}).get("qos", 1)

TOPIC_DATA = CFG.get("mqtt", {}).get("topics", {}).get("data", "group_1/temp")
TOPIC_STATUS = CFG.get("mqtt", {}).get("topics", {}).get("status", "group_1/status")

PUBLISH_INTERVAL = float(CFG.get("publish", {}).get("interval", 2.0))

# Only wild rule matters now.
WILD_MIN = 0.0
WILD_MAX = 50.0

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
    style.configure("Group.TLabelframe", padding=10)
    style.configure("Group.TLabelframe.Label", font=("Segoe UI", 10, "bold"))

    # Status bar (bigger & bold)
    style.configure("Status.TLabel", font=("Segoe UI", 12, "bold"))

    # Treeview styling
    style.configure("Treeview", font=("Segoe UI", 9))
    style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))


# ======================== Rolling chart (Canvas) ========================
class RollingChart(ttk.Frame):
    """
    Rolling line chart on a Canvas.

    - series_map: device_id -> deque[(timestamp, value|None)]  (None = visible gap)
    - wild_segments: device_id -> deque[(t1, v1, t2, v2)]       # red bridges for wild/corrupt (sloped)
    - pending_wild_from: device_id -> (t_prev, v_prev, t_abnormal)
    """

    def __init__(self, master, width=300, height=220, max_points=100):
        super().__init__(master)
        self.width, self.height = width, height
        self.max_points = max_points
        self.canvas = Canvas(self, width=width, height=height,
                             highlightthickness=1, highlightbackground="#ccc")
        self.canvas.grid(sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.series_map: Dict[str, deque] = {}
        self.wild_segments: Dict[str, deque] = {}
        self.pending_wild_from: Dict[str, tuple] = {}
        self.active_device: Optional[str] = None

    def ensure(self, device_id: str) -> deque:
        if device_id not in self.series_map:
            self.series_map[device_id] = deque(maxlen=self.max_points)
        if device_id not in self.wild_segments:
            self.wild_segments[device_id] = deque(maxlen=200)
        return self.series_map[device_id]

    def set_active(self, device_id: Optional[str]):
        self.active_device = device_id
        self.redraw()

    def append(self, device_id: str, timestamp: float, value: Optional[float]):
        dq = self.ensure(device_id)
        if value is None or not isinstance(value, (int, float)) or not math.isfinite(value):
            dq.append((timestamp, None))
        else:
            dq.append((timestamp, float(value)))

        # complete any pending wild bridge
        if device_id in self.pending_wild_from and value is not None and math.isfinite(value):
            (t_prev, v_prev, _t_ab) = self.pending_wild_from.pop(device_id)
            self.wild_segments[device_id].append((t_prev, v_prev, timestamp, float(value)))

        if self.active_device == device_id:
            self.redraw()

    def mark_wild(self, device_id: str, t_abnormal: float):
        """Wild/corrupt: create a sloped red bridge later and insert a tiny gap."""
        dq = self.ensure(device_id)
        t_prev = v_prev = None
        for t, v in reversed(dq):
            if isinstance(v, (int, float)) and math.isfinite(v):
                t_prev, v_prev = t, v
                break
        dq.append((t_abnormal, None))  # small visual break under the red bridge
        if t_prev is not None and v_prev is not None:
            self.pending_wild_from[device_id] = (t_prev, v_prev, t_abnormal)
        if self.active_device == device_id:
            self.redraw()

    def _scale(self, pts):
        """
        IMPORTANT: ignore out-of-range values for scaling so wild spikes
        never stretch the y-axis. We also ignore None gaps.
        """
        if not pts:
            return [], 0.0, 1.0, (lambda t: 30), (lambda v: 10)

        ys = [
            v for _, v in pts
            if isinstance(v, (int, float)) and math.isfinite(v)
               and (WILD_MIN <= v <= WILD_MAX)  # <-- axis ignores wild values
        ]
        if not ys:
            ys = [20.0, 21.0]  # a tiny band if only gaps exist
        ymin, ymax = min(ys), max(ys)
        if ymin == ymax:
            ymin -= 1.0;
            ymax += 1.0
        pad = (ymax - ymin) * 0.05
        ymin -= pad;
        ymax += pad

        tmin, tmax = pts[0][0], pts[-1][0]
        if tmin == tmax:
            tmin -= 1.0;
            tmax += 1.0

        def sx(t):
            return int((t - tmin) / (tmax - tmin) * (self.width - 40)) + 30

        def sy(v):
            return int((1.0 - (v - ymin) / (ymax - ymin)) * (self.height - 30)) + 10

        scaled = []
        for t, v in pts:
            if v is None or not isinstance(v, (int, float)) or not math.isfinite(v):
                scaled.append((None, None))
            else:
                scaled.append((sx(t), sy(v)))
        return scaled, ymin, ymax, sx, sy

    def redraw(self):
        self.canvas.delete("all")
        dev = self.active_device
        if not dev or dev not in self.series_map:
            self.canvas.create_text(self.width // 2, self.height // 2, text="(waiting for device)", fill="#666")
            return

        pts = list(self.series_map[dev])
        scaled, ymin, ymax, sx, sy = self._scale(pts)

        # axes
        self.canvas.create_line(25, 10, 25, self.height - 20, fill="#999")
        self.canvas.create_line(25, self.height - 20, self.width - 10, self.height - 20, fill="#999")
        self.canvas.create_text(40, 15, text=f"{ymax:.1f}", fill="#666", anchor="w")
        self.canvas.create_text(40, self.height - 25, text=f"{ymin:.1f}", fill="#666", anchor="w")

        # main polyline (gaps break it)
        last = None
        for xy in scaled:
            if xy == (None, None):
                last = None
                continue
            x, y = xy
            if last is not None:
                self.canvas.create_line(last[0], last[1], x, y)
            last = (x, y)

        # wild sloped bridges on top
        for (t1, v1, t2, v2) in list(self.wild_segments.get(dev, [])):
            self.canvas.create_line(sx(t1), sy(v1), sx(t2), sy(v2), fill="#d62728", width=2)


# ========================== Main App ==========================
class TemperatureSubscriber:
    def __init__(self, master):
        self.master = master
        self.alert_manager = AlertManager()
        self.master.title("Group 1 - IoT Subscriber Monitor")
        self.master.geometry("980x780")

        self.client: Optional[mqtt.Client] = None
        self.connected = False
        self.running = False

        # device_id -> state dict
        self.device_states: Dict[str, Dict[str, Any]] = {}
        self.data_timeout_timer = None

        # UI variables
        self.status_text = StringVar(value="Status: Disconnected")
        self.devices_tree: Optional[ttk.Treeview] = None
        self.log_text: Optional[scrolledtext.ScrolledText] = None

        self.broker_info = StringVar(value=f"Broker: {BROKER}:{PORT}")
        self.topic_info = StringVar(value=f"Topics: {TOPIC_DATA}, {TOPIC_STATUS}")

        self.last_email_sent = {}
        self.email_cooldown = 300

        # Charts
        self.charts: List[RollingChart] = []
        self.chart_labels: List[ttk.Label] = []
        self.chart_device_map: Dict[str, int] = {}  # device_id -> slot idx

        # reorder buffer window (seconds)
        self.REORDER_WINDOW = max(0.8, 0.6 * PUBLISH_INTERVAL)
        self.reorder_bufs: Dict[str, List[Tuple[float, str, Optional[float]]]] = defaultdict(list)

        setup_style()
        self.setup_ui()
        self.setup_monitoring_timer()

    # ---------- Email helper ----------
    def send_email_notification(self, subject, message, device_id, alert_type):
        if not EMAIL_CONFIG["enabled"]:
            return
        now = time.time()
        key = f"{device_id}_{alert_type}"
        # NOTE: keep existing behavior (cooldown); if you truly want no limit, set self.email_cooldown=0.
        if key in self.last_email_sent and now - self.last_email_sent[key] < self.email_cooldown:
            return
        try:
            msg = MIMEMultipart()
            msg['From'] = EMAIL_CONFIG["sender_email"]
            msg['To'] = EMAIL_CONFIG["recipient_email"]
            msg['Subject'] = f"IoT Alert: {subject}"
            body = f"""IoT Monitoring System Alert

Device ID: {device_id}
Alert Type: {alert_type}
Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Details:
{message}

---
Group 1 IoT Subscriber Monitor
"""
            msg.attach(MIMEText(body, 'plain'))
            s = smtplib.SMTP(EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"])
            s.starttls()
            s.login(EMAIL_CONFIG["sender_email"], EMAIL_CONFIG["sender_password"])
            s.sendmail(EMAIL_CONFIG["sender_email"], EMAIL_CONFIG["recipient_email"], msg.as_string())
            s.quit()
            self.last_email_sent[key] = now
            self.log_message(f"📧 Email notification sent for {device_id}: {alert_type}")
        except Exception as e:
            self.log_message(f"❌ Failed to send email notification: {e}")

    # ---------- UI ----------
    def setup_ui(self):
        container = ttk.Frame(self.master, padding=12)
        container.grid(sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1);
        container.columnconfigure(1, weight=1)

        ttk.Label(container, text="Group 1 — IoT Subscriber Monitor", style="Header.TLabel") \
            .grid(column=0, row=0, columnspan=2, sticky="w", pady=(0, 10))

        info = ttk.Frame(container)
        info.grid(column=0, row=1, columnspan=2, sticky="ew", pady=(0, 10))
        info.columnconfigure(0, weight=1);
        info.columnconfigure(1, weight=1)
        ttk.Label(info, textvariable=self.broker_info, style="SubHeader.TLabel").grid(column=0, row=0, sticky="w")
        ttk.Label(info, textvariable=self.topic_info, style="SubHeader.TLabel").grid(column=1, row=0, sticky="e")

        conn = ttk.LabelFrame(container, text="Connection", style="Group.TLabelframe")
        conn.grid(column=0, row=2, sticky="nsew", padx=(0, 6));
        conn.columnconfigure(0, weight=1)
        self.connect_btn = ttk.Button(conn, text="Connect to Broker", command=self.connect_to_broker)
        self.connect_btn.grid(column=0, row=0, sticky="ew", pady=2)
        self.disconnect_btn = ttk.Button(conn, text="Disconnect", command=self.disconnect_from_broker, state=DISABLED)
        self.disconnect_btn.grid(column=0, row=1, sticky="ew", pady=2)

        opts = ttk.LabelFrame(container, text="Monitoring Settings", style="Group.TLabelframe")
        opts.grid(column=1, row=2, sticky="nsew", padx=(6, 0));
        opts.columnconfigure(0, weight=1)
        ttk.Label(opts, text=f"Publish Interval: {PUBLISH_INTERVAL}s").grid(column=0, row=0, sticky="w", pady=2)
        ttk.Label(opts, text=f"Wild Rule: < {WILD_MIN} or > {WILD_MAX}").grid(column=0, row=1, sticky="w", pady=2)
        ttk.Label(opts, text="QoS Level: 1").grid(column=0, row=2, sticky="w", pady=2)

        dev = ttk.LabelFrame(container, text="Device Status", style="Group.TLabelframe")
        dev.grid(column=0, row=3, columnspan=2, sticky="nsew", pady=(10, 0))
        dev.columnconfigure(0, weight=1);
        dev.rowconfigure(0, weight=1)
        container.rowconfigure(3, weight=1, minsize=170)

        columns = ("Device ID", "Location", "Status", "Last Value", "Last Data", "Alert")
        self.devices_tree = ttk.Treeview(dev, columns=columns, show="headings", height=8)
        for col in columns:
            self.devices_tree.heading(col, text=col)
            self.devices_tree.column(col, width=140 if col in ("Location", "Alert") else 110)
        sb = ttk.Scrollbar(dev, orient=VERTICAL, command=self.devices_tree.yview)
        self.devices_tree.configure(yscrollcommand=sb.set)
        self.devices_tree.grid(column=0, row=0, sticky="nsew", padx=(5, 0), pady=5)
        sb.grid(column=1, row=0, sticky="ns", pady=5)

        chart_frame = ttk.LabelFrame(container, text="Live Charts (one per device)", style="Group.TLabelframe")
        chart_frame.grid(column=0, row=4, columnspan=2, sticky="nsew", pady=(10, 0))
        for c in range(3): chart_frame.columnconfigure(c, weight=1)
        chart_frame.rowconfigure(1, weight=1)
        self.chart_labels = [];
        self.charts = []
        for i in range(3):
            lab = ttk.Label(chart_frame, text=f"Chart {i + 1}: (waiting)", anchor="center")
            lab.grid(row=0, column=i, sticky="ew", padx=4, pady=(0, 4))
            ch = RollingChart(chart_frame, width=300, height=220, max_points=100)  # last 100 points
            ch.grid(row=1, column=i, sticky="nsew", padx=4)
            self.chart_labels.append(lab);
            self.charts.append(ch)

        log_frame = ttk.LabelFrame(container, text="Activity Log", style="Group.TLabelframe")
        log_frame.grid(column=0, row=5, columnspan=2, sticky="nsew", pady=(10, 0))
        log_frame.columnconfigure(0, weight=1);
        log_frame.rowconfigure(0, weight=1)
        container.rowconfigure(5, weight=2, minsize=160)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, font=("Consolas", 9), wrap="none")
        self.log_text.grid(column=0, row=0, sticky="nsew", padx=5, pady=5)
        hscroll = ttk.Scrollbar(log_frame, orient="horizontal", command=self.log_text.xview)
        self.log_text.configure(xscrollcommand=hscroll.set)
        hscroll.grid(column=0, row=1, sticky="ew", padx=5, pady=(0, 5))

        sep = ttk.Separator(container, orient="horizontal")
        sep.grid(column=0, row=6, columnspan=2, sticky="ew", pady=(12, 6))
        status_bar = ttk.Frame(container);
        status_bar.grid(column=0, row=7, columnspan=2, sticky="ew")
        status_bar.columnconfigure(0, weight=1)
        ttk.Label(status_bar, textvariable=self.status_text, style="Status.TLabel", anchor="w").grid(column=0, row=0,
                                                                                                     sticky="w")

    # ---------- Utils ----------
    def log_message(self, message):
        msg_one_line = " ".join(str(message).splitlines())
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {msg_one_line}\n"
        try:
            self.master.after(0, lambda: (self.log_text.insert(END, entry), self.log_text.see(END)))
        except Exception:
            pass

    def ui_status(self, text: str):
        try:
            self.master.after(0, lambda: self.status_text.set(f"Status: {text}"))
        except Exception:
            pass

    # ---------- MQTT ----------
    def setup_client(self):
        try:
            self.client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=f"group1_subscriber-{int(time.time()) % 100000}-{random.randint(1000, 9999)}",
                protocol=mqtt.MQTTv5
            )
            self.client.on_connect = self.on_connect
            self.client.on_disconnect = self.on_disconnect
        except AttributeError:
            self.client = mqtt.Client(
                client_id=f"group1_subscriber-{int(time.time()) % 100000}-{random.randint(1000, 9999)}",
                protocol=mqtt.MQTTv5
            )
            self.client.on_connect = self.on_connect_v3
            self.client.on_disconnect = self.on_disconnect_v3
        self.client.on_message = self.on_message

    def connect_to_broker(self):
        if self.client is None:
            self.setup_client()
        try:
            self.client.connect(BROKER, PORT, keepalive=KEEPALIVE)
            self.client.loop_start()
            self.ui_status("Connecting...")
            self.log_message("Attempting to connect to broker…")
            self.running = True
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
            self.ui_status("Connected - Monitoring devices")
            self.log_message("Connected to broker successfully")
            self.client.subscribe(TOPIC_DATA, qos=QOS)
            self.client.subscribe(TOPIC_STATUS, qos=QOS)
            self.log_message(f"Subscribed to data topic: {TOPIC_DATA}")
            self.log_message(f"Subscribed to status topic: {TOPIC_STATUS}")
            self.connect_btn.config(state=DISABLED);
            self.disconnect_btn.config(state=NORMAL)
        else:
            self.ui_status(f"Connect failed ({reason_code})")
            self.log_message(f"Connection failed with reason code: {reason_code}")

    def on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self.connected = False
        self.ui_status(f"Disconnected (rc={reason_code})")
        self.log_message(f"Disconnected from broker (reason code: {reason_code})")
        self.connect_btn.config(state=NORMAL);
        self.disconnect_btn.config(state=DISABLED)

    def on_connect_v3(self, client, userdata, flags, rc):
        self.on_connect(client, userdata, flags, rc, None)

    def on_disconnect_v3(self, client, userdata, rc):
        self.on_disconnect(client, userdata, None, rc, None)

    # ---------- Messages ----------
    def on_message(self, client, userdata, msg):
        try:
            raw = msg.payload.decode('utf-8', errors='replace')
            if not raw.strip():
                self.log_message(f"❌ Corrupt data: Empty payload from {msg.topic}")
                return
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                self.log_message(f"❌ Corrupt data: Payload not a JSON object from {msg.topic}")
                return
            if msg.topic == TOPIC_DATA:
                self.handle_data_message(payload)
            elif msg.topic == TOPIC_STATUS:
                self.handle_status_message(payload)
        except json.JSONDecodeError as e:
            self.log_message(f"❌ Corrupt data: JSON decode error from {msg.topic}: {e}")
        except Exception as e:
            self.log_message(f"❌ Unexpected error processing {msg.topic}: {e}")

    # --- helpers ---
    def _assign_chart_slot(self, device_id: str):
        if device_id in self.chart_device_map:
            return
        for idx in range(3):
            if idx not in self.chart_device_map.values():
                self.chart_device_map[device_id] = idx
                self.charts[idx].set_active(device_id)
                self.chart_labels[idx].configure(text=device_id)
                return

    def _parse_src_ts(self, t) -> float:
        try:
            return float(t)
        except Exception:
            return time.time()

    def _extract_seq(self, packet_id: Optional[str]) -> Optional[int]:
        if not packet_id or "-" not in str(packet_id):
            return None
        try:
            return int(str(packet_id).split("-")[-1])
        except ValueError:
            return None

    # reorder-buffer emit/queue
    def _emit_to_chart(self, device_id: str, kind: str, src_ts: float, value: Optional[float]):
        slot = self.chart_device_map.get(device_id)
        if slot is None:
            return
        if kind == "value":
            self.charts[slot].append(device_id, src_ts, value)
        elif kind == "gap":
            self.charts[slot].append(device_id, src_ts, None)
        elif kind == "wild":
            self.charts[slot].mark_wild(device_id, src_ts)

    def _queue_for_chart(self, device_id: str, kind: str, src_ts: float, value: Optional[float]):
        buf = self.reorder_bufs[device_id]
        insort(buf, (src_ts, kind, value))
        while buf and (buf[-1][0] - buf[0][0]) >= self.REORDER_WINDOW:
            ts, k, v = buf.pop(0)
            self._emit_to_chart(device_id, k, ts, v)

    # ---------- DATA handler ----------
    def handle_data_message(self, data):
        device_id = data.get("device_id")
        if not device_id:
            self.log_message("❌ Corrupt data: Missing device_id")
            return
        location = data.get("location", "unknown")
        sensor_data = data.get("sensor_data", {})
        if not isinstance(sensor_data, dict):
            self.log_message(f"❌ Corrupt data from {device_id}: sensor_data not a dict")
            return

        rx_wall = time.time()
        rx_mono = time.monotonic()
        src_ts = self._parse_src_ts(data.get("timestamp"))
        packet_id = data.get("packet_id")

        st = self.device_states.setdefault(device_id, {
            "location": location, "status": "ONLINE",
            "last_data_time": None, "last_rx_mono": None,
            "last_value": None, "alert": "",
            "last_src_ts": None, "last_seq": None
        })
        self._assign_chart_slot(device_id)

        # ignore data if publisher STOPPED (until ONLINE again)
        if st.get("status") == "STOPPED" and st.get("stopped_by") == "publisher":
            self._queue_for_chart(device_id, "gap", src_ts, None)
            self.log_message(f"⏸️ {device_id}: Data received while publisher STOPPED — ignored")
            return

        # Clear NO DATA on first data
        if st.get("alert") == "NO DATA":
            st["alert"] = ""
            self.log_message(f"✅ {device_id}: Data feed resumed")

        # Parse numeric & finite
        value_raw = sensor_data.get("value")
        try:
            value = float(value_raw)
            if not math.isfinite(value):
                raise ValueError("non-finite")
        except (ValueError, TypeError):
            st.update({"location": location, "status": "ONLINE", "alert": "CORRUPT"})
            self._queue_for_chart(device_id, "wild", src_ts, None)  # red sloped bridge later
            # email for corrupt data
            self.send_email_notification(
                f"Corrupt Data - {device_id}",
                f"Invalid/NaN value received (payload value={value_raw}) from {location}.",
                device_id, "CORRUPT_DATA"
            )
            self.update_device_display()
            self.log_message(f"❌ Corrupt data from {device_id}: invalid/NaN value")
            return

        # Sequence gap → flat hold + optional email for blackout
        seq = self._extract_seq(packet_id)
        prev_seq = st.get("last_seq")
        prev_ts = st.get("last_src_ts")
        prev_val = st.get("last_value")

        if seq is not None and prev_seq is not None:
            gap = seq - prev_seq
            if gap > 1:
                missing = gap - 1

                # add a flat hold line up to just before this sample
                if isinstance(prev_val, (int, float)) and prev_ts:
                    end_ts = max(prev_ts, src_ts - 1e-3)
                    if end_ts > prev_ts:
                        self._queue_for_chart(device_id, "value", end_ts, prev_val)
                # Email only for real blackout (>=2 missing)
                if missing >= 2:
                    self.send_email_notification(
                        f"Blackout detected - {device_id}",
                        f"Missing {missing} messages (~{missing * PUBLISH_INTERVAL:.1f}s) while ONLINE at {location}.",
                        device_id, "BLACKOUT"
                    )
                    self.log_message(
                        f"⛔ {device_id}: BLACKOUT — missing {missing} messages (~{missing * PUBLISH_INTERVAL:.1f}s)")
        st["last_seq"] = seq

        # Wild range alert (sloped bridge overlay; do NOT plot the point)
        if value < WILD_MIN or value > WILD_MAX:
            st["alert"] = "WILD DATA"
            self.alert_manager.send_alert(device_id, location, value, "WILD_DATA")
            self._queue_for_chart(device_id, "wild", src_ts, None)
            self.log_message(f"🚨 {device_id}: WILD DATA — {value:.2f}°C (rule <{WILD_MIN} or >{WILD_MAX})")
        else:
            st["alert"] = ""
            self._queue_for_chart(device_id, "value", src_ts, value)  # normal sample

        # Extreme sanity (just in case)
        if value < -50 or value > 100:
            self.alert_manager.send_alert(device_id, location, value, "EXTREME_WILD_DATA")
            self.log_message(f"🔥 {device_id}: EXTREME WILD — {value:.2f}°C")

        # Update state using local times + source time
        st.update({
            "location": location,
            "status": "ONLINE",
            "last_data_time": rx_wall,
            "last_rx_mono": rx_mono,
            "last_value": value if (WILD_MIN <= value <= WILD_MAX) else st.get("last_value"),
            "last_src_ts": src_ts
        })

        # Log + table
        if not st["alert"]:
            self.log_message(f"📊 Normal data from {device_id} ({location}): {value:.2f}°C")
        else:
            self.log_message(f"📊 Data from {device_id} ({location}): {value:.2f}°C — FLAGGED: {st['alert']}")
        self.update_device_display()

    # ---------- STATUS handler ----------
    def handle_status_message(self, status_data):
        device_id = status_data.get("device_id")
        if not device_id:
            self.log_message("❌ Corrupt status: Missing device_id")
            return
        location = status_data.get("location", "unknown")
        status = status_data.get("status", "UNKNOWN")

        valid = {"ONLINE", "OFFLINE", "CONNECTING", "DISCONNECTING", "STOPPED"}
        if status not in valid:
            status = "UNKNOWN"

        st = self.device_states.setdefault(device_id, {
            "location": location, "status": status,
            "last_data_time": None, "last_rx_mono": None,
            "last_value": None, "alert": "",
            "last_src_ts": None, "last_seq": None
        })
        old = st["status"]
        st["status"] = status
        st["location"] = location

        self._assign_chart_slot(device_id)

        if status == "OFFLINE":
            st["alert"] = "NETWORK DROP"
            st.pop("stopped_by", None)
            self.alert_manager.send_alert(device_id, location, "N/A", "NETWORK_DROP")
            self.log_message(f"🔴 {device_id}: OFFLINE (likely LWT)")
        elif status == "STOPPED":
            st["alert"] = "STOPPED"
            st["stopped_by"] = "publisher"
            src_ts = st.get("last_src_ts") or time.time()
            self._queue_for_chart(device_id, "gap", src_ts, None)  # real gap only for STOPPED
            self.log_message(f"🟠 {device_id}: STOPPED by publisher")
        elif status == "ONLINE":
            st["alert"] = ""
            st.pop("stopped_by", None)
            self.log_message(f"🟢 {device_id}: ONLINE")
        elif status == "CONNECTING":
            self.log_message(f"🟡 {device_id}: CONNECTING")
        elif status == "DISCONNECTING":
            self.log_message(f"🟡 {device_id}: DISCONNECTING")

        if old != status:
            self.log_message(f"🔄 {device_id}: {old} → {status}")

        self.update_device_display()

    # ---------- NO DATA watchdog (monotonic time) ----------
    def setup_monitoring_timer(self):
        NO_DATA_SLOP = 0.75
        self.NO_DATA_THRESHOLD = (2.0 * PUBLISH_INTERVAL) + NO_DATA_SLOP

        def check_no_data_feed():
            now_mono = time.monotonic()
            if self.running:
                for device_id, st in self.device_states.items():
                    if st.get("status") == "ONLINE" and st.get("last_rx_mono"):
                        elapsed = now_mono - st["last_rx_mono"]
                        if elapsed > self.NO_DATA_THRESHOLD:
                            if st.get("alert") != "NO DATA":
                                st["alert"] = "NO DATA"  # alert only; keep chart smooth
                                self.log_message(
                                    f"⚠️ {device_id}: No data for {elapsed:.1f}s (expected every {PUBLISH_INTERVAL}s)"
                                )
                                # Email for extended no-data blackout
                                self.send_email_notification(
                                    f"No Data Feed - {device_id}",
                                    f"No data has arrived for {elapsed:.1f}s (expected every {PUBLISH_INTERVAL}s).",
                                    device_id, "NO_DATA_FEED"
                                )
                                self.update_device_display()
                        elif st.get("alert") == "NO DATA" and elapsed <= self.NO_DATA_THRESHOLD:
                            st["alert"] = ""
                            self.log_message(f"✅ {device_id}: Data feed resumed after {elapsed:.1f}s")
                            self.update_device_display()

            self.data_timeout_timer = threading.Timer(2.0, check_no_data_feed)
            self.data_timeout_timer.daemon = True
            self.data_timeout_timer.start()

        check_no_data_feed()

    # ---------- UI table ----------
    def update_device_display(self):
        try:
            def _update():
                for item in self.devices_tree.get_children():
                    self.devices_tree.delete(item)
                for device_id, state in self.device_states.items():
                    location = state.get("location", "unknown")
                    status = state.get("status", "UNKNOWN")
                    last_value = state.get("last_value")
                    last_wall = state.get("last_data_time")
                    alert = state.get("alert", "")

                    value_str = f"{last_value}°C" if isinstance(last_value, (int, float)) else "No data"
                    last_data_str = datetime.fromtimestamp(last_wall).strftime("%H:%M:%S") if last_wall else "Never"

                    if alert == "NETWORK DROP":
                        alert_cell = "🔴 NETWORK DROP"
                    elif alert == "STOPPED" or status == "STOPPED":
                        alert_cell = "🟠 STOPPED"
                    elif alert == "NO DATA":
                        alert_cell = "⚠️ NO DATA"
                    elif alert == "WILD DATA":
                        alert_cell = "🚨 WILD DATA"
                    elif alert == "CORRUPT":
                        alert_cell = "❌ CORRUPT"
                    elif status == "ONLINE" and not alert:
                        alert_cell = "🟢 Normal"
                    else:
                        alert_cell = alert or ""

                    self.devices_tree.insert("", "end", iid=device_id, values=(
                        device_id, location, status, value_str, last_data_str, alert_cell
                    ))

            self.master.after(0, _update)
        except Exception as e:
            print(f"Error updating display: {e}")

    # ---------- lifecycle ----------
    def on_closing(self):
        if self.data_timeout_timer:
            try:
                self.data_timeout_timer.cancel()
            except Exception:
                pass
        if self.client:
            try:
                self.client.loop_stop()
            except Exception:
                pass
            try:
                self.client.disconnect()
            except Exception:
                pass
        self.master.destroy()


if __name__ == "__main__":
    root = Tk()
    app = TemperatureSubscriber(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()