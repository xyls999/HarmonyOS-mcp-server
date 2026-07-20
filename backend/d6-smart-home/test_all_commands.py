#!/usr/bin/env python3
"""Test all 22 remote commands via WebSocket, verify voice feedback and fallback responses"""
import json
import socket
import base64
import hashlib
import os
import struct
import time
import sys

WS_HOST = "yuanzhe.tech"
WS_PORT = 80
WS_PATH = "/ws/smart-home"

def ws_handshake(host, port, path):
    key = base64.b64encode(os.urandom(16)).decode()
    headers = [
        "GET {} HTTP/1.1".format(path),
        "Host: {}".format(host),
        "Upgrade: websocket",
        "Connection: Upgrade",
        "Sec-WebSocket-Key: {}".format(key),
        "Sec-WebSocket-Version: 13",
        "",
        ""
    ]
    sock = socket.create_connection((host, port), timeout=15)
    sock.sendall("\r\n".join(headers).encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = sock.recv(4096)
        if not chunk:
            sock.close()
            raise ConnectionError("Handshake failed")
        resp += chunk
    if b"101" not in resp.split(b"\r\n")[0]:
        sock.close()
        raise ConnectionError("Handshake failed")
    return sock

def ws_send(sock, data):
    payload = data.encode("utf-8") if isinstance(data, str) else data
    mask = os.urandom(4)
    masked = bytearray(len(payload))
    for i in range(len(payload)):
        masked[i] = payload[i] ^ mask[i % 4]
    frame = bytearray()
    frame.append(0x80 | 0x1)
    length = len(payload)
    if length < 126:
        frame.append(0x80 | length)
    elif length < 65536:
        frame.append(0x80 | 126)
        frame.extend(struct.pack("!H", length))
    else:
        frame.append(0x80 | 127)
        frame.extend(struct.pack("!Q", length))
    frame.extend(mask)
    frame.extend(masked)
    sock.sendall(bytes(frame))

def ws_recv(sock, timeout=10):
    sock.settimeout(timeout)
    def recv_exact(n):
        buf = bytearray()
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf)
    header = recv_exact(2)
    if not header:
        return None
    opcode = header[0] & 0x0F
    masked = bool(header[1] & 0x80)
    length = header[1] & 0x7F
    if length == 126:
        ext = recv_exact(2)
        if not ext: return None
        length = struct.unpack("!H", ext)[0]
    elif length == 127:
        ext = recv_exact(8)
        if not ext: return None
        length = struct.unpack("!Q", ext)[0]
    mask_key = None
    if masked:
        mask_key = recv_exact(4)
        if not mask_key: return None
    payload = recv_exact(length)
    if payload is None: return None
    if masked and mask_key:
        unmasked = bytearray(length)
        for i in range(length):
            unmasked[i] = payload[i] ^ mask_key[i % 4]
        payload = bytes(unmasked)
    if opcode == 0x1:
        try:
            return json.loads(payload.decode("utf-8"))
        except:
            return None
    return None

# All 22 test commands
ALL_COMMANDS = [
    {"action": "ping", "msgId": 1},
    {"action": "get_server_status", "msgId": 2},
    {"action": "get_status", "msgId": 3},
    {"action": "get_devices", "msgId": 4},
    {"action": "get_sensors", "msgId": 5},
    {"action": "get_scenes", "msgId": 6},
    {"action": "get_user", "msgId": 7},
    {"action": "get_operations", "msgId": 8},
    {"action": "get_chat_history", "msgId": 9},
    {"action": "get_alerts", "msgId": 10},
    {"action": "get_cameras", "msgId": 11},
    {"action": "toggle_device", "msgId": 12, "deviceId": "light_01", "isOn": True},
    {"action": "control_device", "msgId": 13, "deviceId": "ac_01", "subAction": "set_temp", "params": {"value": 26}},
    {"action": "control_device", "msgId": 14, "deviceId": "light_05", "subAction": "set_brightness", "params": {"value": 80}},
    {"action": "control_device", "msgId": 15, "deviceId": "ac_01", "subAction": "set_mode", "params": {"mode": "cool"}},
    {"action": "activate_scene", "msgId": 16, "sceneId": "s1"},
    {"action": "add_device", "msgId": 17, "id": "test_dev_01", "name": "test_light", "type": "light", "room": "living"},
    {"action": "remove_device", "msgId": 18, "deviceId": "test_dev_01"},
    {"action": "update_user", "msgId": 19, "nickname": "test_user"},
    {"action": "send_chat", "msgId": 20, "content": "hello"},
    {"action": "activate_scene_by_name", "msgId": 21, "name": "home"},
    {"action": "rag_search", "msgId": 22, "query": "how to use ac"},
]

CONTROL_ACTIONS = {"toggle_device", "control_device", "activate_scene",
                   "activate_scene_by_name", "add_device", "remove_device",
                   "send_chat", "get_alerts", "get_cameras"}

def main():
    print("=" * 70)
    print("Smart Home Backend - Full Command Test")
    print("=" * 70)

    # Connect
    print("\n[1] Connecting to ws://{}:{}{} ...".format(WS_HOST, WS_PORT, WS_PATH))
    try:
        sock = ws_handshake(WS_HOST, WS_PORT, WS_PATH)
    except Exception as e:
        print("  X Connection failed: {}".format(e))
        sys.exit(1)
    print("  OK WebSocket connected")

    # Wait for initial snapshot
    print("\n[2] Waiting for initial registration/snapshot...")
    time.sleep(3)
    sock.settimeout(2)
    try:
        while True:
            msg = ws_recv(sock, timeout=1)
            if msg is None:
                break
    except:
        pass

    # Test each command
    print("\n[3] Testing {} commands one by one".format(len(ALL_COMMANDS)))
    print("-" * 70)

    results = []
    for i, cmd in enumerate(ALL_COMMANDS):
        action = cmd["action"]
        msg_id = cmd["msgId"]

        # Send command
        cmd_msg = {"type": "command"}
        cmd_msg.update(cmd)
        try:
            ws_send(sock, json.dumps(cmd_msg, ensure_ascii=False))
        except Exception as e:
            print("  {:2d}. {:30s} X Send failed: {}".format(i+1, action, e))
            results.append({"action": action, "status": "SEND_FAIL", "error": str(e)})
            continue

        # Wait for response
        response = None
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                msg = ws_recv(sock, timeout=5)
                if msg is None:
                    continue
                if isinstance(msg, dict) and msg.get("msgId") == msg_id:
                    response = msg
                    break
            except socket.timeout:
                continue
            except Exception as e:
                break

        if response is None:
            print("  {:2d}. {:30s} X No response (timeout 15s)".format(i+1, action))
            results.append({"action": action, "status": "NO_RESPONSE", "error": "timeout"})
            continue

        # Analyze response
        success = response.get("success", False)
        has_hardware_online = "hardwareOnline" in response
        has_offline = response.get("offline", False)
        has_channel_ok = response.get("channelOk", False)
        has_message = bool(response.get("message", ""))
        hardware_online = response.get("hardwareOnline", None)

        is_control = action in CONTROL_ACTIONS

        status_icon = "OK" if success else "XX"
        details = []

        if is_control:
            if has_hardware_online and hardware_online == False:
                details.append("hwOffline:Y")
            elif has_hardware_online:
                details.append("hwOnline:{}".format(hardware_online))
            else:
                details.append("!!NO hwFlag")

            if has_message:
                msg_preview = response.get("message", "")[:35]
                details.append("msg:{}".format(msg_preview))
            else:
                details.append("!!NO msg")
        else:
            if success:
                details.append("query OK")
            else:
                details.append("err:{}".format(response.get("error", "?")))

        if has_offline:
            details.append("offline:T")
        if has_channel_ok:
            details.append("chOk:T")

        detail_str = " | ".join(details)
        print("  {:2d}. {:30s} {} {}".format(i+1, action, status_icon, detail_str))

        results.append({
            "action": action,
            "status": "OK" if success else "FAIL",
            "success": success,
            "hardwareOnline": hardware_online,
            "hasMessage": has_message,
            "message": response.get("message", ""),
            "offline": has_offline,
            "channelOk": has_channel_ok,
        })

        time.sleep(0.5)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    ok_count = sum(1 for r in results if r["status"] == "OK")
    fail_count = sum(1 for r in results if r["status"] != "OK")
    control_with_hw = sum(1 for r in results if r.get("hardwareOnline") == False)
    control_with_msg = sum(1 for r in results if r.get("hasMessage"))

    print("  Total commands:       {}".format(len(results)))
    print("  Successful responses: {}".format(ok_count))
    print("  Failed/no response:   {}".format(fail_count))
    print("  hardwareOnline:false: {}".format(control_with_hw))
    print("  Has message field:    {}".format(control_with_msg))

    # Check missing
    print("\nMissing check:")
    issues_found = False
    for r in results:
        if r["action"] in CONTROL_ACTIONS and r["status"] == "OK":
            issues = []
            if r.get("hardwareOnline") is not False:
                issues.append("missing hardwareOnline:false")
            if not r.get("hasMessage"):
                issues.append("missing message")
            if issues:
                issues_found = True
                print("  !! {}: {}".format(r["action"], ", ".join(issues)))

    if not issues_found:
        print("  All control commands have hardwareOnline:false + message!")

    sock.close()
    print("\nTest complete!")

if __name__ == "__main__":
    main()
