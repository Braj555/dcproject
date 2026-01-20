import numpy as np
import socket

# -------------------- Modulation / Demodulation --------------------
# Symbols normalized to Es≈1 for fairness

def bpsk_mod(bits: np.ndarray) -> np.ndarray:
    return (1 - 2*bits.astype(np.float64)).astype(np.complex128)

def bpsk_demod(sym: np.ndarray) -> np.ndarray:
    return (sym.real < 0).astype(np.uint8)

def qpsk_mod(bits: np.ndarray) -> np.ndarray:
    if len(bits) % 2 != 0:
        bits = np.append(bits, 0)
    b = bits.reshape(-1, 2)
    i = (1 - 2*b[:,0])
    q = (1 - 2*b[:,1])
    return ((i + 1j*q) / np.sqrt(2)).astype(np.complex128)

def qpsk_demod(sym: np.ndarray) -> np.ndarray:
    b1 = (sym.real < 0).astype(np.uint8)
    b0 = (sym.imag < 0).astype(np.uint8)
    return np.column_stack([b1, b0]).reshape(-1)

def qam16_mod(bits: np.ndarray) -> np.ndarray:
    pad = (-len(bits)) % 4
    if pad:
        bits = np.append(bits, np.zeros(pad, dtype=np.uint8))
    b = bits.reshape(-1,4)

    def map2(x, y):
        if x==0 and y==0: return -3
        if x==0 and y==1: return -1
        if x==1 and y==1: return +1
        if x==1 and y==0: return +3

    I = np.array([map2(bb[0], bb[1]) for bb in b], dtype=np.float64)
    Q = np.array([map2(bb[2], bb[3]) for bb in b], dtype=np.float64)
    return ((I + 1j*Q) / np.sqrt(10)).astype(np.complex128)  # Es≈1

def qam16_demod(sym: np.ndarray) -> np.ndarray:
    x = sym.real * np.sqrt(10)
    y = sym.imag * np.sqrt(10)
    def degray(v):
        if v < -2: return (0,0)
        elif v < 0: return (0,1)
        elif v < 2: return (1,1)
        else: return (1,0)
    bI = np.array([degray(val) for val in x])
    bQ = np.array([degray(val) for val in y])
    return np.column_stack([bI, bQ]).reshape(-1).astype(np.uint8)

MOD_SCHEMES = {
    "BPSK": (bpsk_mod, bpsk_demod, 1),
    "QPSK": (qpsk_mod, qpsk_demod, 2),
    "16QAM": (qam16_mod, qam16_demod, 4),
}

# -------------------- Channel / Noise --------------------
def add_awgn(symbols: np.ndarray, ebn0_db: float, bits_per_symbol: int) -> np.ndarray:
    esn0_db = ebn0_db + 10*np.log10(bits_per_symbol)
    esn0 = 10**(esn0_db/10)
    es = np.mean(np.abs(symbols)**2)
    noise_var = es/(2*esn0)
    noise = np.sqrt(noise_var)*(np.random.randn(*symbols.shape) + 1j*np.random.randn(*symbols.shape))
    return symbols + noise

# -------------------- Bits / bytes --------------------
def pack_bits_to_bytes(bits: np.ndarray) -> bytes:
    pad = (-len(bits)) % 8
    if pad:
        bits = np.append(bits, np.zeros(pad, dtype=np.uint8))
    return np.packbits(bits).tobytes()

def unpack_bytes_to_bits(b: bytes, nbits: int) -> np.ndarray:
    arr = np.frombuffer(b, dtype=np.uint8)
    bits = np.unpackbits(arr)
    return bits[:nbits].astype(np.uint8)

# -------------------- Metrics --------------------
def ber(ref_bits: np.ndarray, rx_bits: np.ndarray) -> float:
    n = min(len(ref_bits), len(rx_bits))
    if n == 0: return 1.0
    return float(np.mean(ref_bits[:n] != rx_bits[:n]))

# -------------------- UDP helpers --------------------
def new_udp_sender(host: str, port: int):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((host, port))
    return s

def new_udp_listener(bind_ip: str, port: int):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((bind_ip, port))
    return s
