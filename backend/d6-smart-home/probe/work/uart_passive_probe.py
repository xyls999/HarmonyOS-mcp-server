import argparse
import json
import os
import select
import termios
import time


def configure(fd):
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CLOCAL | termios.CREAD | termios.CS8
    attrs[3] = 0
    speed = termios.B115200
    attrs[4] = speed
    attrs[5] = speed
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 1
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


def frames(buffer):
    found = []
    for marker in (b"\xaa\x55", b"$B", b"$A"):
        offset = 0
        while True:
            offset = buffer.find(marker, offset)
            if offset < 0:
                break
            if marker == b"\xaa\x55" and len(buffer) >= offset + 5:
                candidate = buffer[offset:offset + 5]
                if candidate[2] == 0 and candidate[4] == 0xfb:
                    found.append(candidate.hex(" "))
            elif marker != b"\xaa\x55":
                end = buffer.find(b"#", offset + 2)
                if 0 <= end - offset <= 16:
                    found.append(buffer[offset:end + 1].decode("ascii", "replace"))
            offset += 1
    return sorted(set(found))


def probe(port, seconds):
    result = {"port": port, "seconds": seconds, "bytes": 0, "frames": [], "sample": "", "error": ""}
    fd = None
    try:
        fd = os.open(port, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
        configure(fd)
        deadline = time.monotonic() + seconds
        data = bytearray()
        while time.monotonic() < deadline:
            ready, _, _ = select.select([fd], [], [], 0.25)
            if ready:
                chunk = os.read(fd, 1024)
                if chunk:
                    data.extend(chunk)
        result["bytes"] = len(data)
        result["sample"] = bytes(data[:128]).hex(" ")
        result["frames"] = frames(bytes(data))
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if fd is not None:
            os.close(fd)
    print(json.dumps(result, ensure_ascii=False))


parser = argparse.ArgumentParser()
parser.add_argument("port")
parser.add_argument("--seconds", type=float, default=12)
args = parser.parse_args()
probe(args.port, args.seconds)
