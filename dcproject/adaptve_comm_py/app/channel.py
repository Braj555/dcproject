# app/channel.py
import numpy as np
from math import erfc, sqrt

# -------------------------------
# BER models (AWGN, demo-friendly)
# -------------------------------
def ber_bpsk_theory(snr_db: float) -> float:
    ebn0 = 10**(snr_db/10.0)
    return 0.5 * erfc(sqrt(ebn0))

def ber_qpsk_theory(snr_db: float) -> float:
    return ber_bpsk_theory(snr_db)

def ber_16qam_theory(snr_db: float) -> float:
    ebn0 = 10**(snr_db/10.0)
    # Crude but visually consistent
    return (3/8.0) * erfc(sqrt(0.1 * ebn0))

def ber_for_scheme(snr_db: float, scheme: str) -> float:
    if scheme == "BPSK":
        p = ber_bpsk_theory(snr_db)
    elif scheme == "QPSK":
        p = ber_qpsk_theory(snr_db)
    else:
        p = ber_16qam_theory(snr_db)
    # add a mild "coding gain" factor so demo is smooth
    p = max(min(p * 0.2, 0.2), 0.0)
    return p

# -------------------------------
# Repetition-3 FEC (bit domain)
# -------------------------------
def rep3_encode(data: bytes) -> bytes:
    bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
    bits3 = np.repeat(bits, 3)
    return np.packbits(bits3).tobytes()

def rep3_decode(encoded: bytes) -> bytes:
    bits = np.unpackbits(np.frombuffer(encoded, dtype=np.uint8))
    pad = (-len(bits)) % 3
    if pad:
        bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
    trip = bits.reshape(-1, 3)
    maj = (np.sum(trip, axis=1) >= 2).astype(np.uint8)
    pad2 = (-len(maj)) % 8
    if pad2:
        maj = np.concatenate([maj, np.zeros(pad2, dtype=np.uint8)])
    return np.packbits(maj).tobytes()

# -------------------------------
# Binary symmetric channel (bit flips)
# -------------------------------
def flip_bits(data: bytes, ber: float) -> bytes:
    if ber <= 0: 
        return data
    arr = bytearray(data)
    rng = np.random.default_rng()
    for i in range(len(arr)):
        b = arr[i]
        for k in range(8):
            if rng.random() < ber:
                b ^= (1 << k)
        arr[i] = b
    return bytes(arr)

# -------------------------------
# Constellation helpers (for charts)
# -------------------------------
def bytes_to_bits(buf: bytes) -> np.ndarray:
    return np.unpackbits(np.frombuffer(buf, dtype=np.uint8)).astype(np.uint8)

def _map_bpsk(bits: np.ndarray):
    # 1 bit/sym, points: {-1,+1} on I (Q=0)
    s = 2*bits.astype(float) - 1.0
    I = s
    Q = np.zeros_like(I)
    # Normalize Es = 1
    return I, Q

def _map_qpsk(bits: np.ndarray):
    # 2 bits/sym, Gray: b0 -> I, b1 -> Q ; {-1,+1}/sqrt(2)
    if len(bits) % 2 != 0:
        raise ValueError("QPSK mapping requires an even number of bits")
    b = bits.reshape(-1,2)
    I = (2*b[:,0].astype(float)-1.0)/np.sqrt(2.0)
    Q = (2*b[:,1].astype(float)-1.0)/np.sqrt(2.0)
    return I, Q

def _gray_2bit_to_level(b0, b1):
    # Gray to PAM4: 00->-3, 01->-1, 11->+1, 10->+3
    if b0==0 and b1==0: return -3
    if b0==0 and b1==1: return -1
    if b0==1 and b1==1: return +1
    return +3  # b0==1 and b1==0

def _map_16qam(bits: np.ndarray):
    # 4 bits/sym: (b0,b1)->I , (b2,b3)->Q ; levels in {-3,-1,+1,+3}/sqrt(10)
    if len(bits) % 4 != 0:
        raise ValueError("16QAM mapping requires bit-length divisible by 4")
    b = bits.reshape(-1,4)
    I = np.array([_gray_2bit_to_level(x[0],x[1]) for x in b], dtype=float) / np.sqrt(10.0)
    Q = np.array([_gray_2bit_to_level(x[2],x[3]) for x in b], dtype=float) / np.sqrt(10.0)
    return I, Q

def bits_to_constellation(bits: np.ndarray, scheme: str):
    if scheme == "BPSK":
        return _map_bpsk(bits)
    elif scheme == "QPSK":
        return _map_qpsk(bits)
    else:
        return _map_16qam(bits)

def _demod_bpsk(I: np.ndarray, Q: np.ndarray) -> np.ndarray:
    return (I >= 0).astype(np.uint8)

def _demod_qpsk(I: np.ndarray, Q: np.ndarray) -> np.ndarray:
    b0 = (I >= 0).astype(np.uint8)
    b1 = (Q >= 0).astype(np.uint8)
    bits = np.empty(b0.size * 2, dtype=np.uint8)
    bits[0::2] = b0
    bits[1::2] = b1
    return bits

def _demod_16qam(I: np.ndarray, Q: np.ndarray) -> np.ndarray:
    scale = np.sqrt(10.0)
    pam_levels = np.array([-3.0, -1.0, 1.0, 3.0])
    lut = np.array([[0,0],[0,1],[1,1],[1,0]], dtype=np.uint8)

    def quantize(comp: np.ndarray):
        raw = comp * scale
        dists = (raw[:,None] - pam_levels[None,:])**2
        idx = np.argmin(dists, axis=1)
        return lut[idx]

    bits_i = quantize(I)
    bits_q = quantize(Q)
    bits = np.empty(bits_i.shape[0]*4, dtype=np.uint8)
    bits[0::4] = bits_i[:,0]
    bits[1::4] = bits_i[:,1]
    bits[2::4] = bits_q[:,0]
    bits[3::4] = bits_q[:,1]
    return bits

def demodulate_bits(I: np.ndarray, Q: np.ndarray, scheme: str) -> np.ndarray:
    if scheme == "BPSK":
        return _demod_bpsk(I, Q)
    elif scheme == "QPSK":
        return _demod_qpsk(I, Q)
    else:
        return _demod_16qam(I, Q)

def add_awgn(I: np.ndarray, Q: np.ndarray, snr_db: float):
    # Assume average Es = 1 -> N0 = 1/SNRlin ; per-dimension variance = N0/2
    snr_lin = 10**(snr_db/10.0)
    sigma = np.sqrt(0.5 / max(snr_lin, 1e-6))
    rng = np.random.default_rng()
    return I + rng.normal(0, sigma, size=I.shape), Q + rng.normal(0, sigma, size=Q.shape)

def _downsample_pair(I: np.ndarray, Q: np.ndarray, max_len: int):
    if len(I) > max_len:
        idx = np.linspace(0, len(I)-1, max_len, dtype=int)
        I = I[idx]; Q = Q[idx]
    return I, Q

def iq_points(I: np.ndarray, Q: np.ndarray, max_pts: int = 200):
    I_s, Q_s = _downsample_pair(I, Q, max_pts)
    return np.column_stack([I_s, Q_s]).astype(float).tolist()

def iq_series(I: np.ndarray, Q: np.ndarray, max_samples: int = 256):
    I_s, Q_s = _downsample_pair(I, Q, max_samples)
    return {
        "I": I_s.astype(float).tolist(),
        "Q": Q_s.astype(float).tolist()
    }

def constellation_from_bytes(buf: bytes, scheme: str, snr_db: float, *, clean: bool, max_pts: int = 200):
    bits = bytes_to_bits(buf)
    I, Q = bits_to_constellation(bits, scheme)
    if not clean:
        I, Q = add_awgn(I, Q, snr_db)
    # Sample to limit payload size
    return iq_points(I, Q, max_pts)
