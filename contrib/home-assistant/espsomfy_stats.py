#!/usr/bin/env python3
# Copyright (c) 2026 Al Ruiz. All rights reserved.
"""Print the ESPSomfy-RTS board's live Wi-Fi signal and memory as JSON.

ESPSomfy-RTS only sends these on the websocket its web page uses (port 8080),
not over MQTT or its HTTP API. Home Assistant reads this script's output with a
command_line sensor (see shade_board_sensors.yaml). Standard library only, so
it runs inside Home Assistant OS without installing anything.

Usage: python3 espsomfy_stats.py [host] [timeout_seconds]
Output: {"online": true, "rssi": -16, "channel": 6, "free": 151600,
         "min_free": 105412, "max_block": 110580, "total": 259828}
        or {"online": false} if the board does not answer.
"""

import base64
import json
import os
import re
import socket
import struct
import sys
import time

WANTED = ("wifiStrength", "memStatus")


def read_exact(sock, n):
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("closed")
        data += chunk
    return data


def read_frame(sock):
    """Return (opcode, payload) of one server frame (servers do not mask)."""
    b1, b2 = read_exact(sock, 2)
    length = b2 & 0x7F
    if length == 126:
        length = struct.unpack(">H", read_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", read_exact(sock, 8))[0]
    mask = read_exact(sock, 4) if b2 & 0x80 else None
    payload = read_exact(sock, length)
    if mask:
        payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
    return b1 & 0x0F, payload


def parse_events(text, found):
    """ESPSomfy frames look like 42[eventName,{json}]."""
    m = re.match(r"^\d*\[(\w+),(.*)\]$", text, re.S)
    if m and m.group(1) in WANTED:
        found[m.group(1)] = json.loads(m.group(2))


def to_result(found):
    out = {"online": True}
    w = found.get("wifiStrength")
    if w:
        out["rssi"] = w.get("strength")
        out["channel"] = w.get("channel")
    m = found.get("memStatus")
    if m:
        out["free"] = m.get("free")
        out["min_free"] = m.get("min")
        out["max_block"] = m.get("max")
        out["total"] = m.get("total")
    return out


def collect(host, timeout):
    found = {}
    deadline = time.monotonic() + timeout
    with socket.create_connection((host, 8080), timeout=timeout) as sock:
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall((
            f"GET / HTTP/1.1\r\nHost: {host}:8080\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            head += read_exact(sock, 1)
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise ConnectionError("no websocket upgrade")
        while len(found) < len(WANTED) and time.monotonic() < deadline:
            sock.settimeout(max(0.1, deadline - time.monotonic()))
            try:
                opcode, payload = read_frame(sock)
            except socket.timeout:
                break
            if opcode == 1:
                parse_events(payload.decode("utf-8", "replace"), found)
            elif opcode == 8:
                break
    return found


def main(argv):
    host = argv[1] if len(argv) > 1 else "192.168.1.38"
    timeout = float(argv[2]) if len(argv) > 2 else 20
    try:
        found = collect(host, timeout)
    except (OSError, ConnectionError, ValueError):
        print(json.dumps({"online": False}))
        return 0
    print(json.dumps(to_result(found)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
