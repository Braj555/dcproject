import numpy as np, socket, time, pickle, os, threading, struct
from common import MOD_SCHEMES, add_awgn

CONTROL_IP = "0.0.0.0"     # feedback listener bind
CONTROL_PORT = 6001
TX_TARGET_IP = "127.0.0.1" # set to Receiver IP
TX_DATA_PORT = 6000
FRAME_BITS = 4096
USE_ML = True

MODEL_PATH = "model.pkl"
model = None
if USE_ML and os.path.exists(MODEL_PATH):
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
    print("[TX] ML model loaded.")

feedback = {"snr_db": 8.0, "delay_ms": 10.0, "jitter_ms": 2.0, "recent_ber": 0.01}

def feedback_listener():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((CONTROL_IP, CONTROL_PORT))
    print(f"[TX] Feedback on {CONTROL_PORT}")
    while True:
        data, _ = s.recvfrom(1024)
        try:
            snr_db, delay_ms, jitter_ms, recent_ber = struct.unpack("!ffff", data)
            feedback.update(snr_db=snr_db, delay_ms=delay_ms, jitter_ms=jitter_ms, recent_ber=recent_ber)
        except Exception:
            pass

def pick_modulation():
    x = np.array([[feedback["snr_db"], feedback["delay_ms"], feedback["jitter_ms"], feedback["recent_ber"]]], float)
    if model is not None:
        m = model.predict(x)[0]
        return ["BPSK","QPSK","16QAM"][int(m)]
    return "BPSK" if feedback["snr_db"] < 6 else ("QPSK" if feedback["snr_db"] < 12 else "16QAM")

def main():
    threading.Thread(target=feedback_listener, daemon=True).start()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((TX_TARGET_IP, TX_DATA_PORT))

    rng = np.random.default_rng(0)
    frame_id = 0

    print("[TX] Sending… Ctrl+C to stop.")
    try:
        while True:
            bits = rng.integers(0, 2, size=FRAME_BITS, endpoint=True, dtype=np.uint8)
            scheme = pick_modulation()
            mod, demod, k = MOD_SCHEMES[scheme]
            syms = mod(bits)

            # Symbol-level AWGN injection to emulate channel difficulty
            syms_noisy = add_awgn(syms, feedback["snr_db"], k)

            iq = np.column_stack([syms_noisy.real, syms_noisy.imag]).astype(np.float32).tobytes()
            scheme_id = {"BPSK":1,"QPSK":2,"16QAM":3}[scheme]
            header = struct.pack("!IBI", frame_id, scheme_id, FRAME_BITS)
            s.send(header + iq)

            if frame_id % 10 == 0:
                print(f"[TX] frame={frame_id} scheme={scheme} snr={feedback['snr_db']:.1f} dB")
            frame_id += 1
            time.sleep(0.02)
    except KeyboardInterrupt:
        print("\n[TX] Stopped.")

if __name__ == "__main__":
    main()
