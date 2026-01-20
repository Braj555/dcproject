# app/server.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Dict, Any
import base64, json, os
import numpy as np

from .ml_model import load_model, select_modulation
from .crypto_utils import encrypt_bytes, decrypt_bytes
# NOTE: theory-based BER + simple FEC (repetition-3) + constellations + bits
from .channel import (
    ber_for_scheme,
    rep3_encode, rep3_decode,
    bytes_to_bits, bits_to_constellation,
    add_awgn, demodulate_bits, iq_points, iq_series
)

app = FastAPI()
base_dir = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(base_dir, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(base_dir, "static")), name="static")

# Simple in-memory rooms: room_id -> {"tx": ws, "rx": ws, "snr": float}
rooms: Dict[str, Dict[str, Any]] = {}

ml_model = load_model()

def get_room(room_id: str):
    if room_id not in rooms:
        rooms[room_id] = {"tx": None, "rx": None, "snr": 8.0}
    return rooms[room_id]

# ---- helper: pretty-print first N bits as 0/1 with spacing ----
def bits_str(buf: bytes, max_bits: int = 256, group: int = 8, line: int = 64) -> str:
    bits = bytes_to_bits(buf)[:max_bits]
    s = ''.join('1' if b else '0' for b in bits)
    out = []
    for i, ch in enumerate(s, 1):
        out.append(ch)
        if i % group == 0: out.append(' ')
        if i % line == 0: out.append('\n')
    return ''.join(out).strip()

def bits_list(buf: bytes, max_bits: int = 256):
    return bytes_to_bits(buf)[:max_bits].astype(int).tolist()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/tx", response_class=HTMLResponse)
async def tx_page(request: Request):
    return templates.TemplateResponse("tx.html", {"request": request})

@app.get("/rx", response_class=HTMLResponse)
async def rx_page(request: Request):
    return templates.TemplateResponse("rx.html", {"request": request})

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    room_id = None
    role = None
    try:
        while True:
            msg = await ws.receive_text()
            data = json.loads(msg)

            # --- Join a room as TX or RX ---
            if data.get("type") == "join":
                room_id = data["room"]
                role = data["role"]  # "tx" or "rx"
                room = get_room(room_id)
                room[role] = ws
                await ws.send_json({"type": "joined", "room": room_id, "role": role, "snr": room["snr"]})
                peer = room["rx"] if role == "tx" else room["tx"]
                if peer:
                    await peer.send_json({"type": "peer_status", "status": "online"})
                continue

            # --- TX updates SNR (channel condition slider) ---
            if data.get("type") == "set_snr":
                room = get_room(room_id)
                room["snr"] = float(data["snr"])
                for peer in (room["tx"], room["rx"]):
                    if peer:
                        await peer.send_json({"type": "snr_update", "snr": room["snr"]})
                continue

            # --- TX: send TEXT (encrypt → FEC encode → channel → previews → forward) ---
            if data.get("type") == "send_text":
                room = get_room(room_id)
                snr = room["snr"]
                password = data["password"]
                text = data["text"]

                # ML modulation choice (features kept simple for the demo)
                scheme = select_modulation(ml_model, snr, delay_ms=20, jitter_ms=3, recent_ber=1e-3)

                # Encrypt
                iv, salt, ct = encrypt_bytes(text.encode("utf-8"), password)

                # FEC encode + channel noise
                fec_mode = "rep3"
                fec_ct = rep3_encode(ct)
                ber = ber_for_scheme(snr, scheme)
                fec_bits = bytes_to_bits(fec_ct)
                I_clean, Q_clean = bits_to_constellation(fec_bits, scheme)
                I_noisy, Q_noisy = add_awgn(I_clean, Q_clean, snr)
                noisy_bits = demodulate_bits(I_noisy, Q_noisy, scheme)
                noisy_bytes = np.packbits(noisy_bits).tobytes()

                # Constellations (limit points)
                const_clean = iq_points(I_clean, Q_clean, max_pts=200)
                const_noisy = iq_points(I_noisy, Q_noisy, max_pts=200)
                wave_clean = iq_series(I_clean, Q_clean, max_samples=256)
                wave_noisy = iq_series(I_noisy, Q_noisy, max_samples=256)

                # Bitstream previews (first 256 bits)
                bits_raw   = bits_str(ct)
                bits_clean = bits_str(fec_ct)
                bits_noisy = bits_str(noisy_bytes)
                bits_plot_raw   = bits_list(ct)
                bits_plot_clean = bits_list(fec_ct)
                bits_plot_noisy = bits_list(noisy_bytes)

                frame_payload = {
                    "type": "frame_rx",
                    "kind": "text",
                    "scheme": scheme,
                    "snr": snr,
                    "ber": ber,
                    "fec": fec_mode,
                    "iv": base64.b64encode(iv).decode(),
                    "salt": base64.b64encode(salt).decode(),
                    # encrypted previews
                    "cipher_raw":   base64.b64encode(ct).decode(),      # before FEC/Channel
                    "cipher_clean": base64.b64encode(fec_ct).decode(),  # after FEC, before Channel
                    "cipher":       base64.b64encode(noisy_bytes).decode(),   # after Channel (RX receives)
                    # constellations
                    "const_clean": const_clean,
                    "const_noisy": const_noisy,
                    # bits (0/1)
                    "bits_raw": bits_raw,
                    "bits_clean": bits_clean,
                    "bits_noisy": bits_noisy,
                    # structured previews
                    "wave_clean": wave_clean,
                    "wave_noisy": wave_noisy,
                    "bits_plot_raw": bits_plot_raw,
                    "bits_plot_clean": bits_plot_clean,
                    "bits_plot_noisy": bits_plot_noisy,
                }

                # Send to RX
                rx = room["rx"]
                if rx:
                    await rx.send_json(frame_payload)

                # Also preview back to TX (so TX page can display graphs too)
                tx = room["tx"]
                if tx:
                    preview = dict(frame_payload)
                    preview["type"] = "frame_preview"
                    await tx.send_json(preview)

                await ws.send_json({"type": "tx_ack", "info": f"TEXT via {scheme} @ {snr:.1f}dB (BER~{ber:.2e})"})
                continue

            # --- TX: send FILE (encrypt → FEC encode → channel → previews → forward) ---
            if data.get("type") == "send_file":
                room = get_room(room_id)
                snr = room["snr"]
                password = data["password"]
                name = data["name"]
                content_b64 = data["content_b64"]
                buf = base64.b64decode(content_b64)

                scheme = select_modulation(ml_model, snr, delay_ms=20, jitter_ms=3, recent_ber=1e-3)

                iv, salt, ct = encrypt_bytes(buf, password)

                fec_mode = "rep3"
                fec_ct = rep3_encode(ct)
                ber = ber_for_scheme(snr, scheme)
                fec_bits = bytes_to_bits(fec_ct)
                I_clean, Q_clean = bits_to_constellation(fec_bits, scheme)
                I_noisy, Q_noisy = add_awgn(I_clean, Q_clean, snr)
                noisy_bits = demodulate_bits(I_noisy, Q_noisy, scheme)
                noisy_bytes = np.packbits(noisy_bits).tobytes()

                const_clean = iq_points(I_clean, Q_clean, max_pts=200)
                const_noisy = iq_points(I_noisy, Q_noisy, max_pts=200)
                wave_clean = iq_series(I_clean, Q_clean, max_samples=256)
                wave_noisy = iq_series(I_noisy, Q_noisy, max_samples=256)

                bits_raw   = bits_str(ct)
                bits_clean = bits_str(fec_ct)
                bits_noisy = bits_str(noisy_bytes)
                bits_plot_raw   = bits_list(ct)
                bits_plot_clean = bits_list(fec_ct)
                bits_plot_noisy = bits_list(noisy_bytes)

                frame_payload = {
                    "type": "frame_rx",
                    "kind": "file",
                    "name": name,
                    "scheme": scheme,
                    "snr": snr,
                    "ber": ber,
                    "fec": fec_mode,
                    "iv": base64.b64encode(iv).decode(),
                    "salt": base64.b64encode(salt).decode(),
                    "cipher_raw":   base64.b64encode(ct).decode(),
                    "cipher_clean": base64.b64encode(fec_ct).decode(),
                    "cipher":       base64.b64encode(noisy_bytes).decode(),
                    "const_clean": const_clean,
                    "const_noisy": const_noisy,
                    "bits_raw": bits_raw,
                    "bits_clean": bits_clean,
                    "bits_noisy": bits_noisy,
                    "wave_clean": wave_clean,
                    "wave_noisy": wave_noisy,
                    "bits_plot_raw": bits_plot_raw,
                    "bits_plot_clean": bits_plot_clean,
                    "bits_plot_noisy": bits_plot_noisy,
                }

                # Send to RX
                rx = room["rx"]
                if rx:
                    await rx.send_json(frame_payload)

                # TX preview
                tx = room["tx"]
                if tx:
                    preview = dict(frame_payload)
                    preview["type"] = "frame_preview"
                    await tx.send_json(preview)

                await ws.send_json({"type": "tx_ack", "info": f'FILE "{name}" via {scheme} @ {snr:.1f}dB (BER~{ber:.2e})'})
                continue

            # --- RX: decrypt request (server-side to keep Python-only core) ---
            if data.get("type") == "rx_decrypt":
                password = data["password"]
                iv = base64.b64decode(data["iv"])
                salt = base64.b64decode(data["salt"])
                cipher = base64.b64decode(data["cipher"])
                fec_mode = data.get("fec")  # might be None if old client

                pt = None

                # If client says FEC=rep3 → decode then decrypt
                if fec_mode == "rep3":
                    try_first = rep3_decode(cipher)
                    pt = decrypt_bytes(try_first, password, iv, salt)

                # Robust fallback: if still None, try decrypting raw (handles old clients without fec flag)
                if pt is None:
                    pt = decrypt_bytes(cipher, password, iv, salt)

                if pt is None:
                    await ws.send_json({"type": "rx_result", "ok": False})
                else:
                    if data.get("kind") == "text":
                        try:
                            text = pt.decode()
                        except Exception:
                            text = "<binary>"
                        await ws.send_json({"type": "rx_result", "ok": True, "kind": "text", "text": text})
                    else:
                        await ws.send_json({
                            "type": "rx_result",
                            "ok": True,
                            "kind": "file",
                            "file_b64": base64.b64encode(pt).decode()
                        })
                continue

    except WebSocketDisconnect:
        pass
    finally:
        if room_id and role:
            room = get_room(room_id)
            if room.get(role) is ws:
                room[role] = None
