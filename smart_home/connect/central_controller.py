import argparse
import json
import socket
import sys
import time
import zlib
from pathlib import Path


HEADER = bytes([0xAA, 0x55])
TAIL = bytes([0x55, 0xAA])
PACKET_SIZE = 32
CONTENT_SIZE = 24

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


def load_config(path):
    with open(path, "r", encoding="utf-8") as config_file:
        return json.load(config_file)


def device_endpoint(config, device_name):
    device = config[device_name]
    return device["ip"], int(device.get("port", 8000))


def make_packet(command, value1=0, value2=0):
    content = bytearray(CONTENT_SIZE)
    content[0] = command
    content[1] = value1
    content[2] = value2
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


def binary_command(ip, port, command, value1=0, value2=0, timeout=3.0):
    with socket.create_connection((ip, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(make_packet(command, value1, value2))
        return parse_packet(recv_exact(sock, PACKET_SIZE))


def text_command(ip, port, command, timeout=3.0, recv_size=512):
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
    content = binary_command(ip, port, CMD_KITCHEN_STATUS, timeout=timeout)
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
    content = binary_command(ip, port, CMD_KITCHEN_LIGHT, wire_value, timeout=timeout)
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
    content = binary_command(ip, port, CMD_BATHROOM_STATUS, timeout=timeout)
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
    content = binary_command(ip, port, CMD_BATHROOM_LIGHT, wire_value, timeout=timeout)
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
    content = binary_command(
        ip,
        port,
        CMD_BATHROOM_MOTOR,
        direction_value,
        speed,
        timeout,
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
    content = binary_command(ip, port, CMD_BEDROOM_STATUS, timeout=timeout)
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
    content = binary_command(ip, port, CMD_BEDROOM_LIGHT, wire_value, timeout=timeout)
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
    content = binary_command(
        ip,
        port,
        CMD_BEDROOM_CURTAIN,
        position,
        timeout=timeout,
    )
    return bedroom_status_from_content(ip, port, content)


def bedroom_curtain_action(config, action, timeout):
    ip, port = device_endpoint(config, "bedroom")
    action_value = (
        BEDROOM_CURTAIN_HOME if action == "home" else BEDROOM_CURTAIN_STOP
    )
    content = binary_command(
        ip,
        port,
        CMD_BEDROOM_ACTION,
        action_value,
        timeout=timeout,
    )
    return bedroom_status_from_content(ip, port, content)


def living_door(config, action, timeout):
    ip, port = device_endpoint(config, "living_room")
    if action == "open":
        command, value = LIVING_DOOR_SET, 1
    elif action == "close":
        command, value = LIVING_DOOR_SET, 0
    else:
        command, value = LIVING_DOOR_QUERY, LIVING_DOOR_REPORT_TARGET

    content = binary_command(ip, port, command, LIVING_DOOR_ROOM, value, timeout)
    return {
        "device": "living_room",
        "service": "door",
        "ip": ip,
        "port": port,
        "state": "open" if content[2] else "closed",
        "raw_cmd": content[0],
        "raw_room": content[1],
        "raw_value": content[2],
    }


def living_text(config, service, action, timeout):
    ip, port = device_endpoint(config, "living_room")
    commands = {
        "temp": "TEMP QUERY",
        "event": "EVENT QUERY",
        "ac": f"AC {action.upper()}",
        "beep": f"BEEP {action.upper()}",
        "light": f"LIGHT {action.upper()}",
    }
    reply = text_command(ip, port, commands[service], timeout)
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
    try:
        return {"online": True, "status": callback()}
    except (OSError, ValueError, ConnectionError) as exc:
        return {
            "online": False,
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


def monitor(config, timeout, interval, trigger_buzzer, clear_buzzer, udp_port):
    living_ip, living_port = device_endpoint(config, "living_room")
    last_alarm = None
    udp_sock = None

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
                        reply = text_command(
                            living_ip,
                            living_port,
                            "BEEP ALARM",
                            timeout,
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
                        reply = text_command(
                            living_ip,
                            living_port,
                            "BEEP OFF",
                            timeout,
                        )
                        print(f"[{now}] living-room buzzer cleared: {reply}")
                    except (OSError, ValueError, ConnectionError) as exc:
                        print(f"[{now}] buzzer clear failed: {exc}")
                last_alarm = alarm

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

    services.add_parser("temp", help="query temperature and humidity")
    services.add_parser("event", help="query latest passive event")

    ac = services.add_parser("ac", help="control infrared air conditioner")
    ac.add_argument("action", choices=["on", "off", "query"])

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
        choices=["open", "close", "position", "stop", "home"],
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
    add_living_parser(subparsers)
    add_kitchen_parser(subparsers)
    add_bathroom_parser(subparsers)
    add_bedroom_parser(subparsers)

    monitor_parser = subparsers.add_parser(
        "monitor",
        help="monitor kitchen alarms and optionally trigger living-room buzzer",
    )
    monitor_parser.add_argument("--interval", type=float)
    monitor_parser.add_argument("--udp-port", type=int)
    monitor_parser.add_argument("--trigger-buzzer", action="store_true")
    monitor_parser.add_argument("--clear-buzzer", action="store_true")
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
        elif args.command == "living":
            if args.service == "door":
                print_result(living_door(config, args.action, timeout))
            elif args.service in ("temp", "event"):
                print_result(living_text(config, args.service, "query", timeout))
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
            elif args.action in ("open", "close", "position"):
                if args.action == "open":
                    position = 100
                elif args.action == "close":
                    position = 0
                else:
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
            )
    except (OSError, ValueError, ConnectionError, KeyError) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
