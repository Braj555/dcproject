import socket

BIND_IP = "0.0.0.0"
RELAY_IN_PORT = 6002
RELAY_OUT_IP = "127.0.0.1"   # set to final RX IP
RELAY_OUT_PORT = 6000

def main():
    r = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    r.bind((BIND_IP, RELAY_IN_PORT))
    t = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"[Relay] {RELAY_IN_PORT} -> {RELAY_OUT_IP}:{RELAY_OUT_PORT}")
    while True:
        data, _ = r.recvfrom(65535)
        t.sendto(data, (RELAY_OUT_IP, RELAY_OUT_PORT))

if __name__ == "__main__":
    main()
