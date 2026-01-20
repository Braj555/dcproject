# rx_gui.py  — Receiver with a tiny Tkinter dashboard
import numpy as np, socket, time, struct, threading, collections
import tkinter as tk

BIND_IP = "0.0.0.0"
RX_DATA_PORT = 6000
TX_CONTROL_IP = "127.0.0.1"   # set to Transmitter IP if on different machine
TX_CONTROL_PORT = 6001

lat_hist = collections.deque(maxlen=50)
ber_hist = collections.deque(maxlen=50)
snr_hist = collections.deque(maxlen=50)

# shared state for GUI
state = {
    "frame": 0,
    "scheme": "—",
    "snr_db": 0.0,
    "delay_ms": 0.0,
    "jitter_ms": 0.0,
    "ber": 0.0,
    "running": True,
}

def estimate_snr_from_cloud(iq: np.ndarray) -> float:
    pwr = np.mean(iq[:,0]**2 + iq[:,1]**2)
    mi, mq = np.median(iq[:,0]), np.median(iq[:,1])
    var = np.mean((iq[:,0]-mi)**2 + (iq[:,1]-mq)**2) + 1e-9
    snr_lin = max(pwr/var, 1e-9)
    return 10*np.log10(snr_lin)

def feedback_sender_loop():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    while state["running"]:
        delay_ms = float(np.mean(lat_hist)) if lat_hist else 10.0
        jitter_ms = float(np.std(lat_hist)) if len(lat_hist)>1 else 1.0
        recent_ber = float(np.mean(ber_hist)) if ber_hist else 0.01
        snr_db = float(np.mean(snr_hist)) if snr_hist else 8.0
        payload = struct.pack("!ffff", snr_db, delay_ms, jitter_ms, recent_ber)
        s.sendto(payload, (TX_CONTROL_IP, TX_CONTROL_PORT))
        time.sleep(0.2)

def recv_loop():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((BIND_IP, RX_DATA_PORT))
    s.settimeout(2.0)
    last_t = time.time()
    print(f"[RX] Listening {RX_DATA_PORT}")
    while state["running"]:
        try:
            data, addr = s.recvfrom(65535)
        except socket.timeout:
            continue
        now = time.time()
        lat_ms = (now - last_t)*1000.0
        last_t = now
        lat_hist.append(lat_ms)

        header_sz = 4+1+4
        frame_id, scheme_id, nbits = struct.unpack("!IBI", data[:header_sz])
        iq = np.frombuffer(data[header_sz:], dtype=np.float32).reshape(-1,2)

        sdb = estimate_snr_from_cloud(iq); snr_hist.append(sdb)
        if scheme_id == 1: b = 0.5*np.exp(-sdb/10)
        elif scheme_id == 2: b = 0.5*np.exp(-sdb/10)
        else: b = 0.6*np.exp(-sdb/9)
        ber_hist.append(float(b))

        state["frame"] = frame_id
        state["scheme"] = {1:"BPSK",2:"QPSK",3:"16QAM"}[scheme_id]
        state["snr_db"] = float(sdb)
        state["delay_ms"] = float(lat_ms)
        state["jitter_ms"] = float(np.std(lat_hist)) if len(lat_hist)>1 else 1.0
        state["ber"] = float(b)

def make_gui():
    root = tk.Tk()
    root.title("Adaptive Link – Receiver Dashboard")

    def row(r, label):
        tk.Label(root, text=label, font=("Segoe UI", 12, "bold")).grid(row=r, column=0, sticky="w", padx=8, pady=6)
        v = tk.Label(root, text="—", font=("Consolas", 14))
        v.grid(row=r, column=1, sticky="w", padx=8, pady=6)
        return v

    mod_v   = row(0, "Modulation")
    snr_v   = row(1, "SNR (dB)")
    delay_v = row(2, "Delay (ms)")
    jitter_v= row(3, "Jitter (ms)")
    ber_v   = row(4, "BER (est.)")

    status = tk.Label(root, text="LINK STATUS", font=("Segoe UI", 12, "bold"), width=16)
    status.grid(row=0, column=2, rowspan=5, padx=12, pady=6, sticky="ns")

    def color_for_snr(s):
        if s >= 12:  return "#2ecc71"   # green
        if s >= 6:   return "#f1c40f"   # yellow
        return "#e74c3c"                # red

    def tick():
        mod_v.config(text=f"{state['scheme']}")
        snr_v.config(text=f"{state['snr_db']:.1f}")
        delay_v.config(text=f"{state['delay_ms']:.1f}")
        jitter_v.config(text=f"{state['jitter_ms']:.1f}")
        ber_v.config(text=f"{state['ber']:.2e}")

        status.config(bg=color_for_snr(state["snr_db"]))
        root.after(200, tick)

    def on_close():
        state["running"] = False
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    tick()
    return root

if __name__ == "__main__":
    threading.Thread(target=feedback_sender_loop, daemon=True).start()
    threading.Thread(target=recv_loop, daemon=True).start()
    app = make_gui()
    app.mainloop()
    print("[RX] Closed.")
