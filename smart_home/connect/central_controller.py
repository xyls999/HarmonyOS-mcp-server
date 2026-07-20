import argparse
import getpass
import hashlib
import hmac
import json
import os
import secrets
import socket
import sys
import time
import zlib
from pathlib import Path


HEADER = bytes([0xAA, 0x55])
TAIL = bytes([0x55, 0xAA])
PACKET_SIZE = 32
CONTENT_SIZE = 24
AUTH_NONCE_OFFSET = 16
AUTH_TAG_OFFSET = 20
AUTH_SIGNED_SIZE = 20
DOOR_PASSWORD_ENV = "A9_DOOR_PASSWORD"
DOOR_PASSWORD_ALGORITHM = "pbkdf2_sha256"
DOOR_PASSWORD_ITERATIONS = 120000
SAFETY_STATE_FILE = ".central_controller_state.json"

DEFAULT_RATE_LIMITS_MS = {
    "living_room.door": 3000,
    "living_room.ac": 2000,
    "living_room.beep": 1000,
    "living_room.light": 500,
    "kitchen.light": 500,
    "bathroom.light": 500,
    "bathroom.fan": 1000,
    "bedroom.light": 500,
    "bedroom.curtain": 3000,
}

CMD_KITCHEN_STATUS = 4
CMD_KITCHEN_LIGHT = 5
CMD_BATHROOM_STATUS = 6
CMD_BATHROOM_LIGHT = 7
CMD_BATHROOM_MOTOR = 8
CMD_BEDROOM_STATUS = 9
CMD_BEDROOM_LIGHT = 10
CMD_BEDROOM_CURTAIN = 11
CMD_BEDROOM_ACTION = 12

BEDROOM_CURTAIN_STOP = 0
BEDROOM_CURTAIN_HOME = 1

LIVING_DOOR_QUERY = 0
LIVING_DOOR_SET = 1
LIVING_DOOR_ROOM = 0
LIVING_DOOR_REPORT_TARGET = 1

MOTOR_DIRECTIONS = {
    "stop": 0,
    "forward": 1,
    "reverse": 2,
}

_last_nonce = 0


def auth_enabled(config):
    return bool(config.get("security", {}).get("enable_auth", False))


def auth_key(config):
    return str(config.get("security", {}).get("shared_key", "")).encode(
        "utf-8"
    )


def door_password_config(config):
    return config.get("security", {}).get("door_password", {})


def door_password_required(config):
    return bool(door_password_config(config).get("require_password", False))


def door_password_hash(password, salt, iterations):
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        int(iterations),
    ).hex()


def read_door_password(config, provided_password=None):
    if provided_password:
        return provided_password

    password_config = door_password_config(config)
    env_name = password_config.get("password_env", DOOR_PASSWORD_ENV)
    env_password = os.environ.get(env_name)
    if env_password:
        return env_password

    if sys.stdin.isatty():
        return getpass.getpass("Door password: ")

    raise ValueError(
        f"door password required; use --password or set {env_name}"
    )


def verify_door_password(config, provided_password=None):
    if not door_password_required(config):
        return False

    password_config = door_password_config(config)
    algorithm = password_config.get("algorithm", DOOR_PASSWORD_ALGORITHM)
    if algorithm != DOOR_PASSWORD_ALGORITHM:
        raise ValueError(f"unsupported door password algorithm: {algorithm}")

    salt = str(password_config.get("salt", ""))
    expected_hash = str(password_config.get("hash", "")).lower()
    iterations = int(password_config.get("iterations", DOOR_PASSWORD_ITERATIONS))
    if not salt or not expected_hash:
        raise ValueError("door password is required but salt/hash is not configured")

    password = read_door_password(config, provided_password)
    actual_hash = door_password_hash(password, salt, iterations)
    if not hmac.compare_digest(actual_hash.lower(), expected_hash):
        raise ValueError("door password verification failed")
    return True


def make_door_password_snippet(password=None, salt=None, iterations=DOOR_PASSWORD_ITERATIONS):
    if password is None:
        password = getpass.getpass("New door password: ")
    if not password:
        raise ValueError("door password cannot be empty")
    if salt is None:
        salt = secrets.token_hex(16)
    return {
        "require_password": True,
        "algorithm": DOOR_PASSWORD_ALGORITHM,
        "iterations": int(iterations),
        "salt": salt,
        "hash": door_password_hash(password, salt, iterations),
        "password_env": DOOR_PASSWORD_ENV,
    }


def next_nonce():
    global _last_nonce

    nonce = int(time.time() * 1000) & 0xFFFFFFFF
    if nonce <= _last_nonce:
        nonce = (_last_nonce + 1) & 0xFFFFFFFF
    _last_nonce = nonce
    return nonce


def auth_tag(content, key):
    signed = bytes(content[:AUTH_SIGNED_SIZE])
    return zlib.crc32(signed + key) & 0xFFFFFFFF


def load_config(path):
    with open(path, "r", encoding="utf-8") as config_file:
        return json.load(config_file)


def state_file_path(config):
    state_name = config.get("safety", {}).get("state_file", SAFETY_STATE_FILE)
    state_path = Path(state_name)
    if not state_path.is_absolute():
        state_path = Path(__file__).with_name(state_name)
    return state_path


def load_state(config):
    path = state_file_path(config)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as state_file:
            return json.load(state_file)
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(config, state):
    path = state_file_path(config)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as state_file:
        json.dump(state, state_file, ensure_ascii=False, indent=2)
        state_file.write("\n")
    os.replace(tmp_path, path)


def rate_limit_ms(config, action_key):
    configured = config.get("safety", {}).get("rate_limits_ms", {})
    if action_key in configured:
        return int(configured[action_key])
    return int(DEFAULT_RATE_LIMITS_MS.get(action_key, 0))


def enforce_rate_limit(config, action_key):
    limit_ms = rate_limit_ms(config, action_key)
    if limit_ms <= 0:
        return

    now_ms = int(time.time() * 1000)
    state = load_state(config)
    last_by_key = state.setdefault("last_control_ms", {})
    last_ms = int(last_by_key.get(action_key, 0) or 0)
    if last_ms > 0 and now_ms >= last_ms and now_ms - last_ms < limit_ms:
        wait_ms = limit_ms - (now_ms - last_ms)
        raise ValueError(
            f"rate limit active for {action_key}; wait {wait_ms}ms before retry"
        )

    last_by_key[action_key] = now_ms
    save_state(config, state)


def parse_key_value_reply(reply):
    values = {}
    for part in str(reply).replace("\r", "").replace("\n", ",").split(","):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def normalize_hex_payload(payload):
    tokens = []
    for token in payload.replace(",", " ").replace(":", " ").split():
        if token.lower().startswith("0x"):
            token = token[2:]
        if len(token) != 2:
            raise ValueError(f"invalid IR byte token: {token}")
        int(token, 16)
        tokens.append(token.upper())
    if not tokens:
        raise ValueError("IR payload cannot be empty")
    return " ".join(tokens)


def load_ac_codebook(config):
    codebook_name = config.get("living_room", {}).get("ac_codebook", "ac_ir_codes.json")
    codebook_path = Path(codebook_name)
    if not codebook_path.is_absolute():
        codebook_path = Path(__file__).with_name(codebook_name)
    if not codebook_path.exists():
        return {}
    with open(codebook_path, "r", encoding="utf-8") as codebook_file:
        codebook = json.load(codebook_file)
    return codebook.get("profiles", {})


def device_endpoint(config, device_name):
    device = config[device_name]
    return device["ip"], int(device.get("port", 8000))


def make_packet(command, value1=0, value2=0, key=None):
    content = bytearray(CONTENT_SIZE)
    content[0] = command
    content[1] = value1
    content[2] = value2
    if key:
        content[AUTH_NONCE_OFFSET : AUTH_NONCE_OFFSET + 4] = next_nonce().to_bytes(
            4, "little"
        )
        content[AUTH_TAG_OFFSET : AUTH_TAG_OFFSET + 4] = auth_tag(content, key).to_bytes(
            4, "little"
        )
    crc = zlib.crc32(content) & 0xFFFFFFFF
    return HEADER + crc.to_bytes(4, "little") + bytes(content) + TAIL


def recv_exact(sock, size):
    chunks = []
    received = 0
    while received < size:
        chunk = sock.recv(size - received)
        if not chunk:
            raise ConnectionError("remote device closed the connection")
        chunks.append(chunk)
        received += len(chunk)
    return b"".join(chunks)


def parse_packet(packet):
    if len(packet) != PACKET_SIZE:
        raise ValueError(f"invalid packet size: {len(packet)}")
    if packet[:2] != HEADER or packet[-2:] != TAIL:
        raise ValueError(f"invalid packet markers: {packet.hex(' ')}")

    expected_crc = int.from_bytes(packet[2:6], "little")
    content = packet[6:30]
    actual_crc = zlib.crc32(content) & 0xFFFFFFFF
    if expected_crc != actual_crc:
        raise ValueError(
            f"invalid crc expected=0x{expected_crc:08x} actual=0x{actual_crc:08x}"
        )
    return content


def binary_command(ip, port, command, value1=0, value2=0, timeout=3.0, key=None):
    with socket.create_connection((ip, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(make_packet(command, value1, value2, key=key))
        return parse_packet(recv_exact(sock, PACKET_SIZE))


def text_command(ip, port, command, timeout=3.0, recv_size=512, key=None):
    if key:
        nonce = next_nonce()
        nonce_hex = f"{nonce:08X}"
        tag = zlib.crc32(f"{command}|{nonce_hex}".encode("utf-8") + key) & 0xFFFFFFFF
        command = f"{command} AUTH {nonce_hex} {tag:08X}"
    payload = command if command.endswith("\n") else command + "\n"
    with socket.create_connection((ip, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(payload.encode("utf-8"))
        data = sock.recv(recv_size)
        if not data:
            raise ConnectionError("remote device returned no data")
        return data.decode("utf-8", errors="replace").strip()


def kitchen_status(config, timeout):
    ip, port = device_endpoint(config, "kitchen")
    content = binary_command(
        ip, port, CMD_KITCHEN_STATUS, timeout=timeout, key=auth_key(config) if auth_enabled(config) else None
    )
    return {
        "device": "kitchen",
        "ip": ip,
        "port": port,
        "smoke_level": content[1],
        "smoke_alarm": content[2],
        "temp_alarm": content[3],
        "alarm": content[4],
        "light_on": content[5],
        "brightness": content[6],
        "thermal_mv": int.from_bytes(content[7:9], "little"),
    }


def kitchen_set_light(config, brightness, timeout):
    device = config["kitchen"]
    ip, port = device_endpoint(config, "kitchen")
    wire_value = 100 - brightness if device.get("light_command_inverted") else brightness
    enforce_rate_limit(config, "kitchen.light")
    content = binary_command(
        ip,
        port,
        CMD_KITCHEN_LIGHT,
        wire_value,
        timeout=timeout,
        key=auth_key(config) if auth_enabled(config) else None,
    )
    status = {
        "device": "kitchen",
        "ip": ip,
        "port": port,
        "requested_brightness": brightness,
        "wire_brightness": wire_value,
        "smoke_level": content[1],
        "smoke_alarm": content[2],
        "temp_alarm": content[3],
        "alarm": content[4],
        "light_on": content[5],
        "brightness": content[6],
        "thermal_mv": int.from_bytes(content[7:9], "little"),
    }
    return status


def bathroom_status(config, timeout):
    ip, port = device_endpoint(config, "bathroom")
    content = binary_command(
        ip, port, CMD_BATHROOM_STATUS, timeout=timeout, key=auth_key(config) if auth_enabled(config) else None
    )
    return {
        "device": "bathroom",
        "ip": ip,
        "port": port,
        "light_brightness": content[1],
        "motor_direction": content[2],
        "motor_speed": content[3],
        "motor_running": content[4],
    }


def bathroom_set_light(config, brightness, timeout):
    device = config["bathroom"]
    ip, port = device_endpoint(config, "bathroom")
    wire_value = 100 - brightness if device.get("light_command_inverted") else brightness
    enforce_rate_limit(config, "bathroom.light")
    content = binary_command(
        ip,
        port,
        CMD_BATHROOM_LIGHT,
        wire_value,
        timeout=timeout,
        key=auth_key(config) if auth_enabled(config) else None,
    )
    return {
        "device": "bathroom",
        "ip": ip,
        "port": port,
        "requested_brightness": brightness,
        "wire_brightness": wire_value,
        "light_brightness": content[1],
        "motor_direction": content[2],
        "motor_speed": content[3],
        "motor_running": content[4],
    }


def bathroom_set_fan(config, direction, speed, timeout):
    ip, port = device_endpoint(config, "bathroom")
    direction_value = MOTOR_DIRECTIONS[direction]
    if direction == "stop":
        speed = 0
    enforce_rate_limit(config, "bathroom.fan")
    content = binary_command(
        ip,
        port,
        CMD_BATHROOM_MOTOR,
        direction_value,
        speed,
        timeout,
        key=auth_key(config) if auth_enabled(config) else None,
    )
    return {
        "device": "bathroom",
        "ip": ip,
        "port": port,
        "motor_direction": content[2],
        "motor_speed": content[3],
        "motor_running": content[4],
        "light_brightness": content[1],
    }


def bedroom_status(config, timeout):
    ip, port = device_endpoint(config, "bedroom")
    content = binary_command(
        ip, port, CMD_BEDROOM_STATUS, timeout=timeout, key=auth_key(config) if auth_enabled(config) else None
    )
    return {
        "device": "bedroom",
        "ip": ip,
        "port": port,
        "light_brightness": content[1],
        "curtain_position": content[2],
        "curtain_target": content[3],
        "curtain_moving": content[4],
        "curtain_homed": content[5],
        "close_limit": content[6],
        "open_limit": content[7],
        "last_error": content[8],
    }


def bedroom_set_light(config, brightness, timeout):
    device = config["bedroom"]
    ip, port = device_endpoint(config, "bedroom")
    wire_value = 100 - brightness if device.get("light_command_inverted") else brightness
    enforce_rate_limit(config, "bedroom.light")
    content = binary_command(
        ip,
        port,
        CMD_BEDROOM_LIGHT,
        wire_value,
        timeout=timeout,
        key=auth_key(config) if auth_enabled(config) else None,
    )
    status = bedroom_status_from_content(ip, port, content)
    status["requested_brightness"] = brightness
    status["wire_brightness"] = wire_value
    return status


def bedroom_status_from_content(ip, port, content):
    return {
        "device": "bedroom",
        "ip": ip,
        "port": port,
        "light_brightness": content[1],
        "curtain_position": content[2],
        "curtain_target": content[3],
        "curtain_moving": content[4],
        "curtain_homed": content[5],
        "close_limit": content[6],
        "open_limit": content[7],
        "last_error": content[8],
    }


def bedroom_set_curtain(config, position, timeout):
    ip, port = device_endpoint(config, "bedroom")
    enforce_rate_limit(config, "bedroom.curtain")
    content = binary_command(
        ip,
        port,
        CMD_BEDROOM_CURTAIN,
        position,
        timeout=timeout,
        key=auth_key(config) if auth_enabled(config) else None,
    )
    return bedroom_status_from_content(ip, port, content)


def bedroom_curtain_action(config, action, timeout):
    ip, port = device_endpoint(config, "bedroom")
    action_value = (
        BEDROOM_CURTAIN_HOME if action == "home" else BEDROOM_CURTAIN_STOP
    )
    enforce_rate_limit(config, "bedroom.curtain")
    content = binary_command(
        ip,
        port,
        CMD_BEDROOM_ACTION,
        action_value,
        timeout=timeout,
        key=auth_key(config) if auth_enabled(config) else None,
    )
    return bedroom_status_from_content(ip, port, content)


def living_door(config, action, timeout, password=None):
    ip, port = device_endpoint(config, "living_room")
    if action == "open":
        command, value = LIVING_DOOR_SET, 1
    elif action == "close":
        command, value = LIVING_DOOR_SET, 0
    else:
        command, value = LIVING_DOOR_QUERY, LIVING_DOOR_REPORT_TARGET

    password_verified = False
    if action in ("open", "close"):
        password_verified = verify_door_password(config, password)
        enforce_rate_limit(config, "living_room.door")

    content = binary_command(
        ip,
        port,
        command,
        LIVING_DOOR_ROOM,
        value,
        timeout,
        key=auth_key(config) if auth_enabled(config) else None,
    )
    return {
        "device": "living_room",
        "service": "door",
        "ip": ip,
        "port": port,
        "state": "open" if content[2] else "closed",
        "raw_cmd": content[0],
        "raw_room": content[1],
        "raw_value": content[2],
        "password_required": door_password_required(config),
        "password_verified": password_verified,
    }


def living_ac_command(action, value=None, config=None):
    normalized = action.lower()
    if normalized in ("on", "off", "query"):
        return f"AC {normalized.upper()}"
    if value is None:
        raise ValueError(f"living ac {normalized} requires a value")
    if normalized == "temp":
        temperature = int(value)
        return f"AC TEMP {temperature}"
    if normalized == "mode":
        mode = value.lower()
        if mode not in ("cool", "heat", "dry", "fan"):
            raise ValueError("AC mode must be cool, heat, dry, or fan")
        return f"AC MODE {mode.upper()}"
    if normalized == "fan":
        fan = value.lower()
        if fan not in ("auto", "low", "mid", "high"):
            raise ValueError("AC fan must be auto, low, mid, or high")
        return f"AC FAN {fan.upper()}"
    if normalized == "swing":
        swing = value.lower()
        if swing not in ("on", "off"):
            raise ValueError("AC swing must be on or off")
        return f"AC SWING {swing.upper()}"
    if normalized == "preset":
        profile = value.upper()
        if config is not None:
            codebook = load_ac_codebook(config)
            entry = codebook.get(profile)
            if entry is not None:
                payload = normalize_hex_payload(str(entry.get("payload", "")))
                return f"AC RAW {profile} {payload}"
        return f"AC PRESET {profile}"
    raise ValueError(f"unsupported AC action: {action}")


def living_ac_profiles(config):
    profiles = load_ac_codebook(config)
    summary = {}
    for name in sorted(profiles):
        entry = profiles[name]
        summary[name] = {
            "description": entry.get("description", ""),
            "mode": entry.get("mode", "unknown"),
            "temperature": entry.get("temperature"),
            "fan": entry.get("fan", "unknown"),
            "swing": entry.get("swing", "unknown"),
            "has_payload": bool(entry.get("payload")),
        }
    return {
        "device": "living_room",
        "service": "ac",
        "profile_count": len(summary),
        "profiles": summary,
    }


def living_text(config, service, action, timeout, value=None):
    ip, port = device_endpoint(config, "living_room")
    commands = {
        "temp": "TEMP QUERY",
        "event": "EVENT QUERY",
        "ac": living_ac_command(action, value, config) if service == "ac" else "",
        "beep": f"BEEP {action.upper()}",
        "light": f"LIGHT {action.upper()}",
    }
    if service in ("ac", "beep", "light") and action != "query":
        enforce_rate_limit(config, f"living_room.{service}")
    reply = text_command(
        ip,
        port,
        commands[service],
        timeout,
        key=auth_key(config) if auth_enabled(config) else None,
    )
    return {
        "device": "living_room",
        "service": service,
        "ip": ip,
        "port": port,
        "reply": reply,
    }


def parse_brightness(value):
    normalized = value.strip().lower()
    if normalized == "on":
        return 100
    if normalized == "off":
        return 0
    brightness = int(normalized)
    if not 0 <= brightness <= 100:
        raise ValueError("brightness must be on, off, or 0-100")
    return brightness


def print_result(result):
    print(json.dumps(result, ensure_ascii=False, indent=2))


def safe_query(name, callback):
    start = time.perf_counter()
    try:
        status = callback()
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return {"online": True, "elapsed_ms": elapsed_ms, "status": status}
    except (OSError, ValueError, ConnectionError) as exc:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return {
            "online": False,
            "elapsed_ms": elapsed_ms,
            "error": f"{type(exc).__name__}: {exc}",
            "device": name,
        }


def all_status(config, timeout):
    result = {
        "living_room": {
            "temp": safe_query(
                "living_room.temp",
                lambda: living_text(config, "temp", "query", timeout),
            ),
            "light": safe_query(
                "living_room.light",
                lambda: living_text(config, "light", "query", timeout),
            ),
            "event": safe_query(
                "living_room.event",
                lambda: living_text(config, "event", "query", timeout),
            ),
            "ac": safe_query(
                "living_room.ac",
                lambda: living_text(config, "ac", "query", timeout),
            ),
        },
        "kitchen": safe_query(
            "kitchen",
            lambda: kitchen_status(config, timeout),
        ),
        "bathroom": safe_query(
            "bathroom",
            lambda: bathroom_status(config, timeout),
        ),
        "bedroom": safe_query(
            "bedroom",
            lambda: bedroom_status(config, timeout),
        ),
    }
    return result


def selftest_once(config, timeout):
    return {
        "living_room": safe_query(
            "living_room.temp",
            lambda: living_text(config, "temp", "query", timeout),
        ),
        "kitchen": safe_query("kitchen", lambda: kitchen_status(config, timeout)),
        "bathroom": safe_query("bathroom", lambda: bathroom_status(config, timeout)),
        "bedroom": safe_query("bedroom", lambda: bedroom_status(config, timeout)),
    }


def selftest(config, timeout, wait_seconds, interval):
    start = time.perf_counter()
    first_online = {}
    last_result = {}
    checks = 0
    devices = ("living_room", "kitchen", "bathroom", "bedroom")

    while True:
        checks += 1
        last_result = selftest_once(config, timeout)
        elapsed_s = time.perf_counter() - start
        for device in devices:
            result = last_result.get(device, {})
            if result.get("online") and device not in first_online:
                first_online[device] = round(elapsed_s, 2)

        if len(first_online) == len(devices) or elapsed_s >= wait_seconds:
            break
        time.sleep(interval)

    return {
        "selftest": {
            "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "wait_seconds": wait_seconds,
            "checks": checks,
            "all_online": len(first_online) == len(devices),
            "first_online_after_s": first_online,
            "note": "time is measured from this central-side selftest start, not from device firmware boot timestamp",
        },
        "devices": last_result,
    }


def automation_rule(config, name):
    return config.get("automation", {}).get(name, {})


def automation_enabled(config, name, force=False):
    return force or bool(automation_rule(config, name).get("enabled", False))


def parse_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def run_living_temp_ac_rule(config, timeout, force=False):
    if not automation_enabled(config, "living_temp_ac", force):
        return {"enabled": False}

    rule = automation_rule(config, "living_temp_ac")
    temp_reply = living_text(config, "temp", "query", timeout)["reply"]
    values = parse_key_value_reply(temp_reply)
    temp = parse_number(values.get("temp"))
    if temp is None:
        return {"enabled": True, "action": "skip", "reason": "TEMP_REPLY_PARSE_FAILED", "reply": temp_reply}

    on_temp = float(rule.get("cool_on_temp_c", 30))
    off_temp = float(rule.get("cool_off_temp_c", 27))
    profile = str(rule.get("cool_profile", "COOL_26_AUTO"))
    if temp >= on_temp:
        result = living_text(config, "ac", "preset", timeout, profile)
        return {"enabled": True, "action": "AC_COOL", "temp": temp, "profile": profile, "result": result}
    if bool(rule.get("turn_off_below_threshold", False)) and temp <= off_temp:
        result = living_text(config, "ac", "off", timeout)
        return {"enabled": True, "action": "AC_OFF", "temp": temp, "result": result}
    return {"enabled": True, "action": "none", "temp": temp}


def run_living_humidity_dry_rule(config, timeout, force=False):
    if not automation_enabled(config, "living_humidity_dry", force):
        return {"enabled": False}

    rule = automation_rule(config, "living_humidity_dry")
    temp_reply = living_text(config, "temp", "query", timeout)["reply"]
    values = parse_key_value_reply(temp_reply)
    humi = parse_number(values.get("humi"))
    if humi is None:
        return {"enabled": True, "action": "skip", "reason": "TEMP_REPLY_PARSE_FAILED", "reply": temp_reply}

    on_humi = float(rule.get("dry_on_humi_pct", 75))
    off_humi = float(rule.get("dry_off_humi_pct", 65))
    profile = str(rule.get("dry_profile", "DRY_26_AUTO"))
    if humi >= on_humi:
        result = living_text(config, "ac", "preset", timeout, profile)
        return {"enabled": True, "action": "AC_DRY", "humi": humi, "profile": profile, "result": result}
    if bool(rule.get("turn_off_below_threshold", False)) and humi <= off_humi:
        result = living_text(config, "ac", "off", timeout)
        return {"enabled": True, "action": "AC_OFF", "humi": humi, "result": result}
    return {"enabled": True, "action": "none", "humi": humi}


def maybe_security_alarm(config, timeout, reason):
    rule = automation_rule(config, "security_alarm_buzzer")
    if not bool(rule.get("enabled", False)):
        return

    reason_text = str(reason)
    keywords = rule.get("trigger_keywords", ["password", "rate limit", "auth", "invalid"])
    if not any(str(keyword).lower() in reason_text.lower() for keyword in keywords):
        return

    ip, port = device_endpoint(config, "living_room")
    enforce_rate_limit(config, "living_room.beep")
    text_command(
        ip,
        port,
        "BEEP ALARM",
        timeout,
        key=auth_key(config) if auth_enabled(config) else None,
    )


def monitor(config, timeout, interval, trigger_buzzer, clear_buzzer, udp_port, automation):
    living_ip, living_port = device_endpoint(config, "living_room")
    last_alarm = None
    udp_sock = None
    last_automation = 0.0
    automation_interval = float(
        config.get("automation", {}).get("interval_seconds", max(interval, 5.0))
    )
    buzzer_rule = automation_rule(config, "kitchen_alarm_buzzer")
    trigger_buzzer = trigger_buzzer or bool(buzzer_rule.get("enabled", False))
    clear_buzzer = clear_buzzer or bool(buzzer_rule.get("clear_on_recovery", False))

    try:
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_sock.bind(("", udp_port))
        udp_sock.setblocking(False)
        print(f"UDP kitchen alarm listener active on 0.0.0.0:{udp_port}")
    except OSError as exc:
        if udp_sock is not None:
            udp_sock.close()
        udp_sock = None
        print(f"UDP listener unavailable, polling will continue: {exc}", file=sys.stderr)

    print("Monitoring kitchen alarm and device reachability. Press Ctrl+C to stop.")
    print(f"Automatic living-room buzzer linkage: {'ON' if trigger_buzzer else 'OFF'}")
    print(f"Configured automation rules: {'ON' if automation else 'OFF'}")

    try:
        while True:
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            status = None
            try:
                status = kitchen_status(config, timeout)
                print(
                    f"[{now}] kitchen alarm={status['alarm']} "
                    f"smoke_alarm={status['smoke_alarm']} "
                    f"temp_alarm={status['temp_alarm']} "
                    f"thermal={status['thermal_mv']}mV "
                    f"brightness={status['brightness']}"
                )
            except (OSError, ValueError, ConnectionError) as exc:
                print(f"[{now}] kitchen poll error: {type(exc).__name__}: {exc}")

            if udp_sock is not None:
                while True:
                    try:
                        data, address = udp_sock.recvfrom(1024)
                    except BlockingIOError:
                        break
                    except OSError as exc:
                        print(f"[{now}] UDP receive error: {exc}")
                        break
                    text = data.decode("utf-8", errors="replace").strip()
                    print(f"[{now}] kitchen UDP from {address[0]}: {text}")

            if status is not None:
                alarm = int(status["alarm"])
                if trigger_buzzer and alarm == 1 and last_alarm != 1:
                    try:
                        enforce_rate_limit(config, "living_room.beep")
                        reply = text_command(
                            living_ip,
                            living_port,
                            "BEEP ALARM",
                            timeout,
                            key=auth_key(config) if auth_enabled(config) else None,
                        )
                        print(f"[{now}] living-room buzzer alarm: {reply}")
                    except (OSError, ValueError, ConnectionError) as exc:
                        print(f"[{now}] buzzer alarm failed: {exc}")
                elif (
                    trigger_buzzer
                    and clear_buzzer
                    and alarm == 0
                    and last_alarm == 1
                ):
                    try:
                        enforce_rate_limit(config, "living_room.beep")
                        reply = text_command(
                            living_ip,
                            living_port,
                            "BEEP OFF",
                            timeout,
                            key=auth_key(config) if auth_enabled(config) else None,
                        )
                        print(f"[{now}] living-room buzzer cleared: {reply}")
                    except (OSError, ValueError, ConnectionError) as exc:
                        print(f"[{now}] buzzer clear failed: {exc}")
                last_alarm = alarm

            if automation and time.monotonic() - last_automation >= automation_interval:
                last_automation = time.monotonic()
                for rule_name, callback in (
                    ("living_temp_ac", run_living_temp_ac_rule),
                    ("living_humidity_dry", run_living_humidity_dry_rule),
                ):
                    try:
                        result = callback(config, timeout)
                        if result.get("enabled"):
                            print(f"[{now}] automation {rule_name}: {json.dumps(result, ensure_ascii=False)}")
                    except (OSError, ValueError, ConnectionError, KeyError) as exc:
                        print(f"[{now}] automation {rule_name} failed: {type(exc).__name__}: {exc}")

            time.sleep(interval)
    except KeyboardInterrupt:
        print("Monitor stopped.")
    finally:
        if udp_sock is not None:
            udp_sock.close()


def add_living_parser(subparsers):
    living = subparsers.add_parser("living", help="control living-room Hi3861 hub")
    services = living.add_subparsers(dest="service", required=True)

    door = services.add_parser("door", help="control door servo")
    door.add_argument("action", choices=["open", "close", "query"])
    door.add_argument(
        "--password",
        help=f"door password; safer option is environment variable {DOOR_PASSWORD_ENV}",
    )

    services.add_parser("temp", help="query temperature and humidity")
    services.add_parser("event", help="query latest passive event")

    ac = services.add_parser(
        "ac",
        help="control infrared air conditioner",
        epilog=(
            "Examples: "
            "living ac query | living ac on | living ac off | "
            "living ac temp 28 | living ac mode heat | living ac fan high | "
            "living ac swing on | living ac preset COOL_28_AUTO | living ac profiles"
        ),
    )
    ac.add_argument(
        "action",
        choices=["on", "off", "query", "temp", "mode", "fan", "swing", "preset", "profiles"],
    )
    ac.add_argument(
        "value",
        nargs="?",
        help=(
            "temp: 24-28; mode: cool/heat/dry/fan; fan: auto/low/mid/high; "
            "swing: on/off; preset: COOL_26_AUTO. profiles does not need a value."
        ),
    )

    beep = services.add_parser("beep", help="control buzzer")
    beep.add_argument("action", choices=["on", "off", "alarm", "query"])

    light = services.add_parser("light", help="control living-room light")
    light.add_argument("action", choices=["on", "off", "auto", "test", "query"])


def add_kitchen_parser(subparsers):
    kitchen = subparsers.add_parser("kitchen", help="control kitchen H3863")
    services = kitchen.add_subparsers(dest="service", required=True)
    services.add_parser("status", help="query sensors and light")
    light = services.add_parser("light", help="set light brightness")
    light.add_argument("brightness", help="on, off, or 0-100")


def add_bathroom_parser(subparsers):
    bathroom = subparsers.add_parser("bathroom", help="control bathroom H3863")
    services = bathroom.add_subparsers(dest="service", required=True)
    services.add_parser("status", help="query light and fan")
    light = services.add_parser("light", help="set light brightness")
    light.add_argument("brightness", help="on, off, or 0-100")
    fan = services.add_parser("fan", help="control TB6612 fan motor")
    fan.add_argument("direction", choices=["stop", "forward", "reverse"])
    fan.add_argument("speed", nargs="?", type=int, default=100, choices=range(0, 101))


def add_bedroom_parser(subparsers):
    bedroom = subparsers.add_parser("bedroom", help="control bedroom H3863")
    services = bedroom.add_subparsers(dest="service", required=True)
    services.add_parser("status", help="query light and curtain")

    light = services.add_parser("light", help="set light brightness")
    light.add_argument("brightness", help="on, off, or 0-100")

    curtain = services.add_parser("curtain", help="control 28BYJ-48 curtain")
    curtain.add_argument(
        "action",
        choices=["position", "stop"],
        help="position <0-100> moves by target position; stop is the only direct action kept for demo",
    )
    curtain.add_argument(
        "position",
        nargs="?",
        type=int,
        choices=range(0, 101),
        metavar="0-100",
    )


def build_parser():
    default_config = Path(__file__).with_name("devices.json")
    parser = argparse.ArgumentParser(
        description="Unified central controller for living room, kitchen, bathroom, and bedroom."
    )
    parser.add_argument("--config", default=str(default_config))
    parser.add_argument("--timeout", type=float)

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="query all devices without changing outputs")
    selftest_parser = subparsers.add_parser(
        "selftest",
        help="poll devices and measure central-side time until each becomes reachable",
    )
    selftest_parser.add_argument("--wait-seconds", type=float, default=20.0)
    selftest_parser.add_argument("--interval", type=float, default=1.0)
    add_living_parser(subparsers)
    add_kitchen_parser(subparsers)
    add_bathroom_parser(subparsers)
    add_bedroom_parser(subparsers)

    automation_parser = subparsers.add_parser(
        "automation",
        help="run optional automation linkage rules once",
    )
    automation_parser.add_argument("action", choices=["run-once"])
    automation_parser.add_argument(
        "--force",
        action="store_true",
        help="run rules even if their config enabled flag is false",
    )

    security_parser = subparsers.add_parser("security", help="security helper tools")
    security_subparsers = security_parser.add_subparsers(dest="service", required=True)
    door_password = security_subparsers.add_parser(
        "hash-door-password",
        help="generate a PBKDF2-SHA256 door password config snippet",
    )
    door_password.add_argument("--password")
    door_password.add_argument("--salt")
    door_password.add_argument(
        "--iterations",
        type=int,
        default=DOOR_PASSWORD_ITERATIONS,
    )

    monitor_parser = subparsers.add_parser(
        "monitor",
        help="monitor kitchen alarms and optionally trigger living-room buzzer",
    )
    monitor_parser.add_argument("--interval", type=float)
    monitor_parser.add_argument("--udp-port", type=int)
    monitor_parser.add_argument("--trigger-buzzer", action="store_true")
    monitor_parser.add_argument("--clear-buzzer", action="store_true")
    monitor_parser.add_argument(
        "--automation",
        action="store_true",
        help="enable configured automation rules such as temperature/humidity AC linkage",
    )
    return parser


def main():
    args = build_parser().parse_args()
    config = load_config(args.config)
    defaults = config.get("defaults", {})
    timeout = (
        args.timeout
        if args.timeout is not None
        else float(defaults.get("timeout_seconds", 3.0))
    )

    try:
        if args.command == "status":
            print_result(all_status(config, timeout))
        elif args.command == "selftest":
            print_result(
                selftest(
                    config,
                    timeout,
                    args.wait_seconds,
                    args.interval,
                )
            )
        elif args.command == "living":
            if args.service == "door":
                print_result(living_door(config, args.action, timeout, args.password))
            elif args.service in ("temp", "event"):
                print_result(living_text(config, args.service, "query", timeout))
            elif args.service == "ac" and args.action == "profiles":
                print_result(living_ac_profiles(config))
            elif args.service == "ac":
                print_result(living_text(config, args.service, args.action, timeout, args.value))
            else:
                print_result(living_text(config, args.service, args.action, timeout))
        elif args.command == "kitchen":
            if args.service == "status":
                print_result(kitchen_status(config, timeout))
            else:
                print_result(
                    kitchen_set_light(
                        config,
                        parse_brightness(args.brightness),
                        timeout,
                    )
                )
        elif args.command == "bathroom":
            if args.service == "status":
                print_result(bathroom_status(config, timeout))
            elif args.service == "light":
                print_result(
                    bathroom_set_light(
                        config,
                        parse_brightness(args.brightness),
                        timeout,
                    )
                )
            else:
                print_result(
                    bathroom_set_fan(
                        config,
                        args.direction,
                        args.speed,
                        timeout,
                    )
                )
        elif args.command == "bedroom":
            if args.service == "status":
                print_result(bedroom_status(config, timeout))
            elif args.service == "light":
                print_result(
                    bedroom_set_light(
                        config,
                        parse_brightness(args.brightness),
                        timeout,
                    )
                )
            elif args.action == "position":
                if args.position is None:
                    raise ValueError(
                        "bedroom curtain position requires a value from 0 to 100"
                    )
                position = args.position
                print_result(bedroom_set_curtain(config, position, timeout))
            else:
                print_result(
                    bedroom_curtain_action(config, args.action, timeout)
                )
        elif args.command == "monitor":
            interval = (
                args.interval
                if args.interval is not None
                else float(defaults.get("monitor_interval_seconds", 1.0))
            )
            udp_port = (
                args.udp_port
                if args.udp_port is not None
                else int(config["kitchen"].get("alarm_udp_port", 8001))
            )
            monitor(
                config,
                timeout,
                interval,
                args.trigger_buzzer,
                args.clear_buzzer,
                udp_port,
                args.automation,
            )
        elif args.command == "automation":
            if args.action == "run-once":
                print_result(
                    {
                        "living_temp_ac": run_living_temp_ac_rule(
                            config, timeout, args.force
                        ),
                        "living_humidity_dry": run_living_humidity_dry_rule(
                            config, timeout, args.force
                        ),
                    }
                )
        elif args.command == "security":
            if args.service == "hash-door-password":
                print_result(
                    make_door_password_snippet(
                        password=args.password,
                        salt=args.salt,
                        iterations=args.iterations,
                    )
                )
    except (OSError, ValueError, ConnectionError, KeyError) as exc:
        try:
            maybe_security_alarm(config, timeout, exc)
        except (OSError, ValueError, ConnectionError, KeyError):
            pass
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
