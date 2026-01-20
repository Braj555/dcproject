import numpy as np, socket, time, struct, threading, collections
from common import MOD_SCHEMES

BIND_IP = "0.0.0.0"
RX_DATA_PORT = 6000
TX_CONTROL_IP = "127.0.0.1"  # set to Transmitter IP
TX_CONTROL_PORT = 6001

lat_hist = collections.deque(maxlen=50)
ber_hist = collections.deque(maxlen=50)
snr_hist = collections.deque(maxlen=50)

def estimate_snr_from_cloud(iq: np.ndarray) -> float:
    pwr = np.mean(iq[:,0]**2 + iq[:,1]**2)
    mi, mq = np.median(iq[:,0]), np.median(iq[:,1])
    var = np.mean((iq[:,0]-mi)**2 + (iq[:,1]-mq)**2) + 1e-9
    snr_lin = max(pwr/var, 1e-9)
    return 10*np.log10(snr_lin)

def feedback_sender():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    while True:
        delay_ms = float(np.mean(lat_hist)) if lat_hist else 10.0
        jitter_ms = float(np.std(lat_hist)) if len(lat_hist)>1 else 1.0
        recent_ber = float(np.mean(ber_hist)) if ber_hist else 0.01
        snr_db = float(np.mean(snr_hist)) if snr_hist else 8.0
        payload = struct.pack("!ffff", snr_db, delay_ms, jitter_ms, recent_ber)
        s.sendto(payload, (TX_CONTROL_IP, TX_CONTROL_PORT))
        time.sleep(0.2)

def main():
    threading.Thread(target=feedback_sender, daemon=True).start()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((BIND_IP, RX_DATA_PORT))
    print(f"[RX] Listening {RX_DATA_PORT}")

    last_t = time.time()
    while True:
        data, addr = s.recvfrom(65535)
        now = time.time()
        lat_ms = (now - last_t)*1000.0
        last_t = now
        lat_hist.append(lat_ms)

        header_sz = 4+1+4
        frame_id, scheme_id, nbits = struct.unpack("!IBI", data[:header_sz])
        iq = np.frombuffer(data[header_sz:], dtype=np.float32).reshape(-1,2)

        sdb = estimate_snr_from_cloud(iq); snr_hist.append(sdb)

        # SNR→BER crude proxy for live display (real BER requires shared PRBS or payload compare)
        if scheme_id == 1: b = 0.5*np.exp(-sdb/10)
        elif scheme_id == 2: b = 0.5*np.exp(-sdb/10)
        else: b = 0.6*np.exp(-sdb/9)
        ber_hist.append(float(b))

        if frame_id % 10 == 0:
            scheme = {1:"BPSK",2:"QPSK",3:"16QAM"}[scheme_id]
            print(f"[RX] frame={frame_id}  scheme={scheme}  snr≈{sdb:.1f} dB  delay≈{lat_ms:.1f} ms  BER~{b:.2e}")

if __name__ == "__main__":
    main()
