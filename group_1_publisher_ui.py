from tkinter import Frame, Label, Button, StringVar, BooleanVar, DoubleVar, BOTH, X, Y, LEFT, RIGHT, END, DISABLED, NORMAL
from tkinter import ttk

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


def build_ui(app, master):
    # Root container with nice padding and column stretch
    container = ttk.Frame(master, padding=12)
    container.grid(sticky="nsew")
    master.columnconfigure(0, weight=1)
    master.rowconfigure(0, weight=1)
    container.columnconfigure(0, weight=1)
    container.columnconfigure(1, weight=1)

    # Title
    title = ttk.Label(container, text=f"Group 1 — IoT Publisher  •  {app.device_id}", style="Header.TLabel")
    title.grid(column=0, row=0, columnspan=2, sticky="w", pady=(0, 10))

    # Device info (compact header row)
    info = ttk.Frame(container)
    info.grid(column=0, row=1, columnspan=2, sticky="ew", pady=(0, 10))
    info.columnconfigure(0, weight=1)
    info.columnconfigure(1, weight=1)

    ttk.Label(info, text=f"Device ID: {app.device_id}", style="SubHeader.TLabel").grid(column=0, row=0, sticky="w")
    ttk.Label(info, text=f"Location: {app.location}", style="SubHeader.TLabel").grid(column=1, row=0, sticky="e")

    # --- Left column: Signal Parameters ---
    params = ttk.LabelFrame(container, text="Signal Parameters", style="Group.TLabelframe")
    params.grid(column=0, row=2, sticky="nsew", padx=(0, 6))
    params.columnconfigure(1, weight=1)

    ttk.Label(params, text="Amplitude:").grid(column=0, row=0, sticky="w", pady=2)
    app.amp_var = DoubleVar(value=2.5)
    ttk.Entry(params, textvariable=app.amp_var, width=12).grid(column=1, row=0, sticky="ew", padx=6, pady=2)

    ttk.Label(params, text="Frequency:").grid(column=0, row=1, sticky="w", pady=2)
    app.freq_var = DoubleVar(value=0.08)
    ttk.Entry(params, textvariable=app.freq_var, width=12).grid(column=1, row=1, sticky="ew", padx=6, pady=2)

    ttk.Label(params, text="Noise:").grid(column=0, row=2, sticky="w", pady=2)
    app.noise_var = DoubleVar(value=0.8)
    ttk.Entry(params, textvariable=app.noise_var, width=12).grid(column=1, row=2, sticky="ew", padx=6, pady=2)

    # NEW: Base temperature (offset)
    ttk.Label(params, text="Base Temp:").grid(column=0, row=3, sticky="w", pady=2)
    app.base_var = DoubleVar(value=20.0)  # default 20°C; adjust if you prefer
    ttk.Entry(params, textvariable=app.base_var, width=12).grid(column=1, row=3, sticky="ew", padx=6, pady=2)

    # --- Right column: Data Options + Connection ---
    right_col = ttk.Frame(container)
    right_col.grid(column=1, row=2, sticky="nsew", padx=(6, 0))
    right_col.columnconfigure(0, weight=1)

    options = ttk.LabelFrame(right_col, text="Data Options", style="Group.TLabelframe")
    options.grid(column=0, row=0, sticky="ew")
    options.columnconfigure(0, weight=1)

    app.wild_var = BooleanVar(value=False)
    app.corrupt_var = BooleanVar(value=False)
    ttk.Checkbutton(options, text="Enable Wild Data", variable=app.wild_var).grid(column=0, row=0, sticky="w", pady=2)
    ttk.Checkbutton(options, text="Enable Corrupt Data", variable=app.corrupt_var).grid(column=0, row=1, sticky="w", pady=2)

    conn = ttk.LabelFrame(right_col, text="Connection", style="Group.TLabelframe")
    conn.grid(column=0, row=1, sticky="ew", pady=(8, 0))
    conn.columnconfigure(0, weight=1)
    app.drop_btn = ttk.Button(conn, text="Go Offline", command=app.go_offline)
    app.drop_btn.grid(column=0, row=0, sticky="ew", pady=2)
    app.reconnect_btn = ttk.Button(conn, text="Reconnect Now", command=app.go_online, state=DISABLED)
    app.reconnect_btn.grid(column=0, row=1, sticky="ew", pady=2)

    # --- Controls row (full width) ---
    controls = ttk.LabelFrame(container, text="Controls", style="Group.TLabelframe")
    controls.grid(column=0, row=3, columnspan=2, sticky="ew", pady=(10, 0))
    for c in range(2):
        controls.columnconfigure(c, weight=1)

    app.start_btn = ttk.Button(controls, text="Start Publishing", command=app.start_publishing)
    app.start_btn.grid(column=0, row=0, sticky="ew", padx=(0, 6), pady=4)
    app.stop_btn = ttk.Button(controls, text="Stop", command=app.stop_publishing, state=DISABLED)
    app.stop_btn.grid(column=1, row=0, sticky="ew", padx=(6, 0), pady=4)

    # --- Status bar ---
    sep = ttk.Separator(container, orient="horizontal")
    sep.grid(column=0, row=4, columnspan=2, sticky="ew", pady=(12, 6))

    status_bar = ttk.Frame(container)
    status_bar.grid(column=0, row=5, columnspan=2, sticky="ew")
    status_bar.columnconfigure(0, weight=1)
    app.status_lbl = ttk.Label(status_bar, textvariable=app.status_text, style="Status.TLabel", anchor="w")
    app.status_lbl.grid(column=0, row=0, sticky="w")
