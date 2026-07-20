#!/usr/bin/env python3
"""D6 串口语音桥接。

串口可以明确指定，也可以使用自动识别模式。自动识别只对现场允许的
`/dev/ttyS3`、`/dev/ttyS4`、`/dev/ttyS8` 做只读监听，不发送探测帧；
第一条已知语音帧到达后锁定实际端口。未配置时安全退出。
支持现场包中的 AA 55 ... FB 二进制帧和 $Bxxx# 兼容帧，并把已识别的中文
指令送入本机网关。门禁帧不会绕过密码校验，只播报需要密码。
"""
from __future__ import annotations

import argparse
import json
import os
import select
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows 开发机仅用于协议解析测试
    fcntl = None
try:
    import termios
except ImportError:  # D6 Linux 设备运行时可用
    termios = None

CONFIG_PATH = Path(os.environ.get("A9_VOICE_CONFIG", "/data/A9/smart_home/voice_control.json"))
STATUS_PATH = CONFIG_PATH.with_name("voice_bridge_status.json")
LOCK_PATH = CONFIG_PATH.with_name("voice_bridge.lock")
DEFAULT_BAUD = 115200
MAX_BUFFER = 4096
DEBOUNCE_SECONDS = 0.8
AUTO_PORTS = ("/dev/ttyS3", "/dev/ttyS4", "/dev/ttyS8")


def _hx(value: str) -> bytes:
    return bytes.fromhex(value)


def _action(name: str, *, door: bool = False) -> dict:
    return {"name": name, "door": door}


# 与现场启动包的协议表保持同一命令编号，所有播报词保持中文。
FRAME_ACTIONS = {
    _hx("AA 55 00 01 FB"): _action("打开门禁", door=True),
    _hx("AA 55 00 02 FB"): _action("关闭门禁", door=True),
    _hx("AA 55 00 03 FB"): _action("查询门禁"),
    _hx("AA 55 00 04 FB"): _action("打开空调"),
    _hx("AA 55 00 05 FB"): _action("关闭空调"),
    _hx("AA 55 00 06 FB"): _action("查询空调"),
    _hx("AA 55 00 07 FB"): _action("打开报警"),
    _hx("AA 55 00 08 FB"): _action("关闭报警"),
    _hx("AA 55 00 09 FB"): _action("查询温湿度"),
    _hx("AA 55 00 0A FB"): _action("查询客厅状态"),
    _hx("AA 55 00 0B FB"): _action("查询厨房状态"),
    _hx("AA 55 00 0C FB"): _action("查询卧室状态"),
    _hx("AA 55 00 0D FB"): _action("查询卫生间状态"),
    _hx("AA 55 00 0F FB"): _action("回家模式"),
    _hx("AA 55 00 10 FB"): _action("离家模式"),
    _hx("AA 55 00 11 FB"): _action("打开客厅灯"),
    _hx("AA 55 00 12 FB"): _action("关闭客厅灯"),
    _hx("AA 55 00 13 FB"): _action("打开卧室灯"),
    _hx("AA 55 00 14 FB"): _action("关闭卧室灯"),
    _hx("AA 55 00 15 FB"): _action("打开厨房灯"),
    _hx("AA 55 00 16 FB"): _action("关闭厨房灯"),
    _hx("AA 55 00 17 FB"): _action("打开换气扇"),
    _hx("AA 55 00 18 FB"): _action("关闭换气扇"),
    _hx("AA 55 00 19 FB"): _action("打开窗帘"),
    _hx("AA 55 00 1A FB"): _action("关闭窗帘"),
    _hx("AA 55 00 1B FB"): _action("打开卫生间灯"),
    _hx("AA 55 00 1C FB"): _action("关闭卫生间灯"),
    _hx("AA 55 00 1F FB"): _action("查询全部设备"),
    _hx("AA 55 00 23 FB"): _action("查询系统状态"),
    _hx("AA 55 00 25 FB"): _action("窗帘半开"),
    _hx("AA 55 00 28 FB"): _action("空调二十四度"),
    _hx("AA 55 00 29 FB"): _action("空调二十五度"),
    _hx("AA 55 00 2A FB"): _action("空调二十六度"),
    _hx("AA 55 00 2B FB"): _action("空调二十七度"),
    _hx("AA 55 00 2C FB"): _action("空调二十八度"),
    _hx("AA 55 00 2D FB"): _action("空调制冷模式"),
    _hx("AA 55 00 2F FB"): _action("空调除湿模式"),
    _hx("AA 55 00 30 FB"): _action("空调送风模式"),
    _hx("AA 55 00 35 FB"): _action("开启空调扫风"),
    _hx("AA 55 00 36 FB"): _action("关闭空调扫风"),
}

LEGACY_FRAME_ACTIONS = {
    "$B004#": FRAME_ACTIONS[_hx("AA 55 00 01 FB")],
    "$B005#": FRAME_ACTIONS[_hx("AA 55 00 02 FB")],
    "$B001#": FRAME_ACTIONS[_hx("AA 55 00 03 FB")],
    "$B011#": FRAME_ACTIONS[_hx("AA 55 00 04 FB")],
    "$B010#": FRAME_ACTIONS[_hx("AA 55 00 05 FB")],
    "$B012#": FRAME_ACTIONS[_hx("AA 55 00 06 FB")],
}


def extract_frames(buffer: bytes):
    """从任意分片/噪声缓冲区提取完整帧，返回(帧列表, 未完成尾部)。"""
    frames = []
    buffer = bytes(buffer)[-MAX_BUFFER:]
    while buffer:
        starts = [p for p in (buffer.find(b"\xAA\x55"), buffer.find(b"$B"), buffer.find(b"$A")) if p >= 0]
        if not starts:
            return frames, b""
        start = min(starts)
        buffer = buffer[start:]
        if buffer.startswith(b"\xAA\x55"):
            if len(buffer) < 5:
                return frames, buffer
            frame, buffer = buffer[:5], buffer[5:]
            if frame[2] == 0 and frame[4] == 0xFB:
                frames.append(frame)
            continue
        end = buffer.find(b"#", 2)
        if end < 0:
            return frames, buffer[:32]
        raw, buffer = buffer[:end + 1], buffer[end + 1:]
        try:
            text = raw.decode("ascii")
        except UnicodeDecodeError:
            continue
        if len(text) == 6 and text[0] == "$" and text[1] in ("A", "B") and text[2:5].isdigit():
            frames.append(text)
    return frames, b""


def action_for_frame(frame):
    return FRAME_ACTIONS.get(frame) if isinstance(frame, bytes) else LEGACY_FRAME_ACTIONS.get(frame)


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text("utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _write_status(**updates):
    current = _read_json(STATUS_PATH)
    current.update(updates, updatedAt=time.time())
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="voice-status-", dir=str(STATUS_PATH.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(current, stream, ensure_ascii=False)
        os.replace(tmp, STATUS_PATH)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _post(gateway: str, path: str, payload: dict, secret: str = "") -> bool:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(gateway.rstrip("/") + path, data=data,
                                     headers={"Content-Type": "application/json; charset=utf-8",
                                              "Content-Length": str(len(data)),
                                              "X-A9-Voice-Bridge": secret}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=4) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def _configure_serial(fd: int, baud: int):
    if termios is None:
        raise RuntimeError("D6 串口桥接需要 Linux termios")
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CLOCAL | termios.CREAD | termios.CS8
    attrs[3] = 0
    speed = getattr(termios, f"B{baud}", termios.B115200)
    attrs[4] = speed
    attrs[5] = speed
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 5
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


def run(port: str, gateway: str, baud: int):
    if not port or not os.path.isabs(port):
        _write_status(running=False, serialPort=port or "", lastError="未明确配置绝对串口路径")
        return 2
    secret = os.environ.get("A9_VOICE_BRIDGE_SECRET", "")
    lock = open(LOCK_PATH, "a+")
    if fcntl is None:
        _write_status(running=False, serialPort=port, lastError="当前系统不支持 D6 串口锁")
        lock.close()
        return 3
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        _write_status(running=False, serialPort=port, lastError="已有语音桥接实例")
        return 3
    fd = None
    frames_count = 0
    last_frame = 0.0
    _write_status(running=True, pid=os.getpid(), serialPort=port, frames=0, lastError="")
    try:
        fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        _configure_serial(fd, baud)
        pending = b""
        while True:
            ready, _, _ = select.select([fd], [], [], 1.0)
            if not ready:
                continue
            chunk = os.read(fd, 512)
            if not chunk:
                break
            pending += chunk
            parsed, pending = extract_frames(pending)
            for frame in parsed[:8]:
                now = time.monotonic()
                if now - last_frame < DEBOUNCE_SECONDS:
                    continue
                last_frame = now
                item = action_for_frame(frame)
                if not item:
                    continue
                frames_count += 1
                _write_status(frames=frames_count, lastFrameAt=time.time(), lastCommand=item["name"], lastError="")
                if item.get("door"):
                    _post(gateway, "/api/tts/speak", {"text": "门禁操作需要手动输入密码", "category": "door"}, secret)
                    continue
                _post(gateway, "/api/voice/input", {"transcript": item["name"], "source": "D6串口语音"}, secret)
    except Exception as exc:
        _write_status(running=False, serialPort=port, lastError=str(exc), pid=os.getpid())
        return 4
    finally:
        if fd is not None:
            os.close(fd)
        _write_status(running=False, serialPort=port, pid=os.getpid())
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        lock.close()
    return 0


def run_auto(gateway: str, baud: int):
    """只读监听候选串口，并在第一条已知语音帧出现时锁定端口。"""
    secret = os.environ.get("A9_VOICE_BRIDGE_SECRET", "")
    lock = open(LOCK_PATH, "a+")
    if fcntl is None:
        _write_status(running=False, serialPort="自动识别", lastError="当前系统不支持 D6 串口锁")
        lock.close()
        return 3
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        _write_status(running=False, serialPort="自动识别", lastError="已有语音桥接实例")
        lock.close()
        return 3
    fds = {}
    pending = {}
    frames_count = 0
    last_frame = 0.0
    detected_port = ""
    _write_status(running=True, pid=os.getpid(), serialPort="自动识别", candidatePorts=list(AUTO_PORTS),
                  detectedPort="", frames=0, lastError="")
    try:
        for port in AUTO_PORTS:
            try:
                fd = os.open(port, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
                _configure_serial(fd, baud)
                fds[fd] = port
                pending[fd] = b""
            except OSError:
                continue
        if not fds:
            _write_status(running=False, serialPort="自动识别", candidatePorts=list(AUTO_PORTS),
                          lastError="候选语音串口均无法打开")
            return 4
        while True:
            ready, _, _ = select.select(list(fds), [], [], 1.0)
            if not ready:
                continue
            for fd in ready:
                try:
                    chunk = os.read(fd, 512)
                except OSError:
                    chunk = b""
                if not chunk:
                    continue
                pending[fd] += chunk
                parsed, pending[fd] = extract_frames(pending[fd])
                for frame in parsed[:8]:
                    item = action_for_frame(frame)
                    if not item:
                        continue
                    now = time.monotonic()
                    if now - last_frame < DEBOUNCE_SECONDS:
                        continue
                    last_frame = now
                    detected_port = fds[fd]
                    _write_status(detectedPort=detected_port, serialPort="自动识别")
                    # 识别后只保留实际端口，避免其他串口的噪声影响上下文。
                    for other_fd in list(fds):
                        if other_fd != fd:
                            try:
                                os.close(other_fd)
                            except OSError:
                                pass
                            fds.pop(other_fd, None)
                            pending.pop(other_fd, None)
                    frames_count += 1
                    _write_status(frames=frames_count, lastFrameAt=time.time(),
                                  lastCommand=item["name"], lastError="")
                    if item.get("door"):
                        _post(gateway, "/api/tts/speak", {"text": "门禁操作需要手动输入密码", "category": "door"}, secret)
                    else:
                        _post(gateway, "/api/voice/input",
                              {"transcript": item["name"], "source": "D6串口语音"}, secret)
    except Exception as exc:
        _write_status(running=False, serialPort="自动识别", detectedPort=detected_port, lastError=str(exc), pid=os.getpid())
        return 4
    finally:
        for fd in list(fds):
            try:
                os.close(fd)
            except OSError:
                pass
        _write_status(running=False, serialPort="自动识别", detectedPort=detected_port, pid=os.getpid())
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        lock.close()
    return 0


def main():
    parser = argparse.ArgumentParser(description="D6 串口语音桥接")
    parser.add_argument("--port", default=os.environ.get("A9_VOICE_SERIAL", ""))
    parser.add_argument("--gateway", default="http://127.0.0.1:8080")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    args = parser.parse_args()
    if str(args.port).strip().lower() in ("auto", "自动识别"):
        return run_auto(args.gateway, args.baud)
    return run(args.port, args.gateway, args.baud)


if __name__ == "__main__":
    raise SystemExit(main())
