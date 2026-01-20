# app/common.py
import time

def now_ms() -> int:
    return int(time.time()*1000)

# (If you want, you can move BPSK/QPSK/16QAM symbol-level here later)
