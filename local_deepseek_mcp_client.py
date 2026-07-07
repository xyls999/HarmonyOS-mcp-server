#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import socket
import subprocess
import sys
import termios
import time
import tty
import unicodedata
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen


ROOT = os.path.dirname(os.path.abspath(__file__))
SERVER_CMD = [os.path.join(ROOT, "run_mcp.sh")]
MAX_CONTEXT_MESSAGES = 28
TCP_REQUEST_STATS = {
    "total_requests": 0,
    "per_second": {},
    "last_request": {},
}


class McpStdioClient:
    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            SERVER_CMD,
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._next_id = 1

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if self.proc.stdin is None or self.proc.stdout is None:
            raise RuntimeError("MCP process stdio is unavailable")
        message_id = self._next_id
        self._next_id += 1
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": message_id, "method": method}
        if params is not None:
            payload["params"] = params
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

        while True:
            line = self.proc.stdout.readline()
            if not line:
                err = self.proc.stderr.read() if self.proc.stderr else ""
                raise RuntimeError(f"MCP server exited unexpectedly. {err}")
            response = json.loads(line)
            if response.get("id") != message_id:
                continue
            if "error" in response:
                raise RuntimeError(response["error"])
            return response.get("result")

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        if self.proc.stdin is None:
            raise RuntimeError("MCP process stdin is unavailable")
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()


def display_width(text: str) -> int:
    width = 0
    for char in text:
        if unicodedata.east_asian_width(char) in {"W", "F"}:
            width += 2
        else:
            width += 1
    return width


def refresh_input_line(prompt: str, buffer: list[str], cursor: int) -> None:
    text = "".join(buffer)
    sys.stdout.write("\r")
    sys.stdout.write(prompt + text)
    sys.stdout.write("\x1b[K")

    tail = display_width(text[cursor:])
    if tail > 0:
        sys.stdout.write(f"\x1b[{tail}D")
    sys.stdout.flush()


def read_escape_sequence() -> str:
    first = sys.stdin.read(1)
    if not first:
        return "\x1b"
    sequence = "\x1b" + first
    if first != "[":
        return sequence

    while True:
        char = sys.stdin.read(1)
        if not char:
            return sequence
        sequence += char
        if char.isalpha() or char == "~":
            return sequence


def read_line_with_editing(prompt: str, history: list[str]) -> str:
    if not sys.stdin.isatty():
        return input(prompt)

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    buffer: list[str] = []
    cursor = 0
    history_index = len(history)

    try:
        tty.setraw(fd)
        sys.stdout.write(prompt)
        sys.stdout.flush()

        while True:
            char = sys.stdin.read(1)
            if char in {"\r", "\n"}:
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                return "".join(buffer)
            if char == "\x03":
                raise KeyboardInterrupt
            if char == "\x04":
                if not buffer:
                    raise EOFError
                if cursor < len(buffer):
                    del buffer[cursor]
                    refresh_input_line(prompt, buffer, cursor)
                continue
            if char in {"\x08", "\x7f"}:
                if cursor > 0:
                    cursor -= 1
                    del buffer[cursor]
                    refresh_input_line(prompt, buffer, cursor)
                continue
            if char == "\x01":
                cursor = 0
                refresh_input_line(prompt, buffer, cursor)
                continue
            if char == "\x05":
                cursor = len(buffer)
                refresh_input_line(prompt, buffer, cursor)
                continue
            if char == "\x1b":
                sequence = read_escape_sequence()
                if sequence == "\x1b[D" and cursor > 0:
                    cursor -= 1
                elif sequence == "\x1b[C" and cursor < len(buffer):
                    cursor += 1
                elif sequence == "\x1b[H":
                    cursor = 0
                elif sequence == "\x1b[F":
                    cursor = len(buffer)
                elif sequence == "\x1b[3~" and cursor < len(buffer):
                    del buffer[cursor]
                elif sequence == "\x1b[A" and history:
                    if history_index > 0:
                        history_index -= 1
                    buffer = list(history[history_index])
                    cursor = len(buffer)
                elif sequence == "\x1b[B":
                    if history_index < len(history) - 1:
                        history_index += 1
                        buffer = list(history[history_index])
                    else:
                        history_index = len(history)
                        buffer = []
                    cursor = len(buffer)
                refresh_input_line(prompt, buffer, cursor)
                continue
            if char.isprintable():
                buffer.insert(cursor, char)
                cursor += 1
                refresh_input_line(prompt, buffer, cursor)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def http_get(url: str, timeout: int = 20) -> str:
    request = Request(url, headers={"User-Agent": "HarmonyOS-MCP-Console/0.2"})
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def clean_text(value: str, limit: int = 5000) -> str:
    value = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", value)
    value = re.sub(r"(?is)<br\s*/?>", "\n", value)
    value = re.sub(r"(?is)</p\s*>|</div\s*>|</li\s*>|</h[1-6]\s*>", "\n", value)
    value = re.sub(r"(?is)<.*?>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\n\s+", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value).strip()
    return value[:limit]


def web_search(query: str, max_results: int = 5) -> dict[str, Any]:
    max_results = max(1, min(int(max_results or 5), 8))
    search_urls = [
        "https://www.bing.com/search?q=" + quote_plus(query),
        "https://duckduckgo.com/html/?q=" + quote_plus(query),
    ]
    last_error = ""
    page = ""
    source = ""
    for url in search_urls:
        try:
            page = http_get(url)
            source = url
            break
        except Exception as exc:
            last_error = str(exc)
    if not page:
        return {"query": query, "results": [], "error": last_error}

    results: list[dict[str, str]] = []

    bing_pattern = re.compile(
        r'<li class="b_algo".*?<h2[^>]*>.*?<a[^>]+href="(?P<link>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?'
        r'(?:<p[^>]*>(?P<snippet>.*?)</p>)',
        re.I | re.S,
    )
    for match in bing_pattern.finditer(page):
        link = html.unescape(match.group("link"))
        title = clean_text(match.group("title"), 200)
        snippet = clean_text(match.group("snippet") or "", 400)
        results.append({"title": title, "url": link, "snippet": snippet})
        if len(results) >= max_results:
            break

    ddg_pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="(?P<link>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?'
        r'<a[^>]+class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
        re.I | re.S,
    )
    for match in ddg_pattern.finditer(page):
        if len(results) >= max_results:
            break
        link = html.unescape(match.group("link"))
        title = clean_text(match.group("title"), 200)
        snippet = clean_text(match.group("snippet"), 400)
        results.append({"title": title, "url": link, "snippet": snippet})

    if not results:
        simple_links = re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', page, re.I | re.S)
        for link, title in simple_links[:max_results]:
            results.append({"title": clean_text(title, 200), "url": html.unescape(link), "snippet": ""})

    return {"query": query, "source": source, "results": results[:max_results]}


def fetch_url(url: str, max_chars: int = 5000) -> dict[str, Any]:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    page = http_get(url)
    text = clean_text(page, max(1000, min(int(max_chars or 5000), 12000)))
    title = ""
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", page)
    if match:
        title = clean_text(match.group(1), 200)
    return {"url": url, "title": title, "text": text}


def run_shell_command(command: str, timeout: int = 20) -> dict[str, Any]:
    timeout = max(1, min(int(timeout or 20), 60))
    result = subprocess.run(
        command,
        shell=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return {"returncode": result.returncode, "output": output[-12000:]}


def run_device_command(command: str, timeout: int = 20) -> dict[str, Any]:
    timeout = max(1, min(int(timeout or 20), 60))
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return {"returncode": result.returncode, "output": output.strip()}


def get_foreground_app() -> dict[str, str]:
    result = run_device_command("aa dump -l", timeout=20)
    output = result.get("output", "")
    mission_match = re.search(r"mission name #\[#(?P<mission>[^\]]+)\].*?app state #FOREGROUND", output, re.S)
    bundle_match = re.search(r"bundle name \[(?P<bundle>[^\]]+)\].*?app state #FOREGROUND", output, re.S)
    ability_match = re.search(r"main name \[(?P<ability>[^\]]+)\].*?app state #FOREGROUND", output, re.S)
    return {
        "mission": mission_match.group("mission") if mission_match else "",
        "bundle": bundle_match.group("bundle") if bundle_match else "",
        "ability": ability_match.group("ability") if ability_match else "",
    }


def launch_and_confirm(
    command: str,
    expected_bundle: str,
    action: str,
    wait_seconds: float = 1.5,
) -> dict[str, Any]:
    result = run_device_command(command)
    time.sleep(wait_seconds)
    foreground = get_foreground_app()
    result["action"] = action
    result["foreground"] = foreground
    result["success"] = result["returncode"] == 0 and foreground.get("bundle") == expected_bundle
    return result


def get_current_time() -> dict[str, str]:
    now = dt.datetime.now().astimezone()
    return {"datetime": now.isoformat(timespec="seconds"), "timezone": now.tzname() or ""}


def open_camera() -> dict[str, Any]:
    return launch_and_confirm(
        "aa start -b com.ohos.camera -a com.ohos.camera.MainAbility",
        "com.ohos.camera",
        "open_camera",
    )


def take_photo() -> dict[str, Any]:
    open_result = open_camera()
    shutter_result = run_device_command("uitest uiInput keyEvent 19")
    return {
        "action": "take_photo",
        "open_camera": open_result,
        "shutter": shutter_result,
        "success": open_result["returncode"] == 0 and shutter_result["returncode"] == 0,
    }


def dial_phone_number(phone_number: str) -> dict[str, Any]:
    digits = re.sub(r"[^\d+#*]", "", phone_number or "")
    if not digits:
        return {"action": "dial_phone_number", "success": False, "error": "phone number is empty"}
    result = launch_and_confirm(
        f"aa start -b com.ohos.contacts -a com.ohos.contacts.MainAbility -U tel:{digits}",
        "com.ohos.contacts",
        "dial_phone_number",
    )
    result["phone_number"] = digits
    return result


def open_browser_search(query: str) -> dict[str, Any]:
    query = (query or "").strip()
    if not query:
        return {"action": "open_browser_search", "success": False, "error": "query is empty"}
    url = "https://www.bing.com/search?q=" + quote_plus(query)
    result = launch_and_confirm(
        f"aa start -b ohos.samples.browser1 -a MainAbility -U {url}",
        "ohos.samples.browser1",
        "open_browser_search",
    )
    result["query"] = query
    result["url"] = url
    return result


def open_music() -> dict[str, Any]:
    return launch_and_confirm(
        "aa start -b ohos.samples.distributedmusicplayer -a ohos.samples.distributedmusicplayer.MainAbility",
        "ohos.samples.distributedmusicplayer",
        "open_music",
    )


def music_play_pause() -> dict[str, Any]:
    result = run_device_command("uitest uiInput keyEvent 10")
    result["action"] = "music_play_pause"
    result["success"] = result["returncode"] == 0
    return result


def music_next() -> dict[str, Any]:
    result = run_device_command("uitest uiInput keyEvent 12")
    result["action"] = "music_next"
    result["success"] = result["returncode"] == 0
    return result


def music_previous() -> dict[str, Any]:
    result = run_device_command("uitest uiInput keyEvent 13")
    result["action"] = "music_previous"
    result["success"] = result["returncode"] == 0
    return result


def volume_up_tool() -> dict[str, Any]:
    result = run_device_command("uitest uiInput keyEvent 16")
    result["action"] = "volume_up"
    result["success"] = result["returncode"] == 0
    return result


def volume_down_tool() -> dict[str, Any]:
    result = run_device_command("uitest uiInput keyEvent 17")
    result["action"] = "volume_down"
    result["success"] = result["returncode"] == 0
    return result


def _record_tcp_request(host: str, port: int, message: str, response: str, success: bool) -> None:
    now = int(time.time())
    per_second = {
        key: value for key, value in TCP_REQUEST_STATS["per_second"].items() if now - int(key) <= 60
    }
    bucket = str(now)
    per_second[bucket] = per_second.get(bucket, 0) + 1
    TCP_REQUEST_STATS["per_second"] = per_second
    TCP_REQUEST_STATS["total_requests"] += 1
    TCP_REQUEST_STATS["last_request"] = {
        "timestamp": now,
        "host": host,
        "port": port,
        "message": message,
        "response": response,
        "success": success,
    }


def tcp_line_request(host: str = "192.168.1.62", port: int = 8000, message: str = "1", timeout: int = 5) -> dict[str, Any]:
    port = int(port)
    timeout = max(1, min(int(timeout or 5), 30))
    payload = str(message)
    response = ""
    success = False
    error = ""
    try:
        with socket.create_connection((host, port), timeout=timeout) as client:
            client.settimeout(timeout)
            with client.makefile("r", encoding="utf-8", errors="replace", newline="\n") as reader:
                with client.makefile("w", encoding="utf-8", errors="replace", newline="\n") as writer:
                    writer.write(payload + "\n")
                    writer.flush()
                    line = reader.readline()
                    response = line.rstrip("\r\n")
        success = True
    except Exception as exc:
        error = str(exc)
    _record_tcp_request(host, port, payload, response or error, success)
    return {
        "action": "tcp_line_request",
        "host": host,
        "port": port,
        "message": payload,
        "response": response,
        "success": success,
        "error": error,
    }


def tcp_request_stats() -> dict[str, Any]:
    now = int(time.time())
    per_second = {
        key: value for key, value in TCP_REQUEST_STATS["per_second"].items() if now - int(key) <= 60
    }
    TCP_REQUEST_STATS["per_second"] = per_second
    current_second = str(now)
    return {
        "action": "tcp_request_stats",
        "total_requests": TCP_REQUEST_STATS["total_requests"],
        "requests_this_second": per_second.get(current_second, 0),
        "requests_last_60_seconds": sum(per_second.values()),
        "per_second": per_second,
        "last_request": TCP_REQUEST_STATS["last_request"],
    }


def tcp_request_reset_stats() -> dict[str, Any]:
    TCP_REQUEST_STATS["total_requests"] = 0
    TCP_REQUEST_STATS["per_second"] = {}
    TCP_REQUEST_STATS["last_request"] = {}
    return {
        "action": "tcp_request_reset_stats",
        "success": True,
    }


LOCAL_TOOL_FUNCS: dict[str, Callable[..., Any]] = {
    "web_search": web_search,
    "fetch_url": fetch_url,
    "run_shell_command": run_shell_command,
    "get_current_time": get_current_time,
    "open_camera": open_camera,
    "take_photo": take_photo,
    "dial_phone_number": dial_phone_number,
    "open_browser_search": open_browser_search,
    "open_music": open_music,
    "music_play_pause": music_play_pause,
    "music_next": music_next,
    "music_previous": music_previous,
    "volume_up_tool": volume_up_tool,
    "volume_down_tool": volume_down_tool,
    "tcp_line_request": tcp_line_request,
    "tcp_request_stats": tcp_request_stats,
    "tcp_request_reset_stats": tcp_request_reset_stats,
}


LOCAL_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information and return result titles, URLs, and snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch a web page and return cleaned text content for reading or summarizing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "max_chars": {"type": "integer", "default": 5000},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell_command",
            "description": "Run a shell command on the HarmonyOS device. Use only when the user asks for terminal/device operations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout": {"type": "integer", "default": 20},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get current date, time, and timezone on the HarmonyOS device.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_camera",
            "description": "Open the HarmonyOS camera app.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_photo",
            "description": "Open the camera app and trigger the shutter key to take a photo.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dial_phone_number",
            "description": "Open the phone dialer with a phone number and trigger dialing flow.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone_number": {"type": "string"},
                },
                "required": ["phone_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_browser_search",
            "description": "Open the browser and search the given query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_music",
            "description": "Open the HarmonyOS music app.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "music_play_pause",
            "description": "Toggle music play or pause.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "music_next",
            "description": "Play the next music track.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "music_previous",
            "description": "Play the previous music track.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "volume_up_tool",
            "description": "Increase media volume on the device.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "volume_down_tool",
            "description": "Decrease media volume on the device.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tcp_line_request",
            "description": "Open a TCP connection, send one line, read one line, then close. Defaults match 192.168.1.62:8000 with payload 1.",
            "parameters": {
                "type": "object",
                "properties": {
                    "host": {"type": "string", "default": "192.168.1.62"},
                    "port": {"type": "integer", "default": 8000},
                    "message": {"type": "string", "default": "1"},
                    "timeout": {"type": "integer", "default": 5},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tcp_request_stats",
            "description": "Get TCP request statistics including total requests and requests per second.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tcp_request_reset_stats",
            "description": "Reset TCP request statistics counters.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def chat_completion(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set")

    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
    body = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0.25,
    }
    request = Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"API request failed: {exc}") from exc


def mcp_tools_to_openai(tools_result: dict[str, Any]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for tool in tools_result.get("tools", []):
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
                },
            }
        )
    return converted


def system_message() -> dict[str, str]:
    return {
        "role": "system",
        "content": (
            "你是运行在鸿蒙设备控制台里的助手。你能进行常规对话，也能调用工具。"
            "需要最新信息时使用 web_search，打开或查询网页时使用 fetch_url。"
            "需要操作鸿蒙应用时使用 MCP 应用工具；需要设备命令行时使用 run_shell_command。"
            "执行 shell 命令前要确认用户确实在请求设备/终端操作，避免危险破坏性命令。"
            "回答使用中文，简洁直接；涉及网络结果时给出来源 URL。"
        ),
    }


def initialize_mcp() -> tuple[McpStdioClient, list[dict[str, Any]]]:
    mcp = McpStdioClient()
    mcp.request(
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "harmonyos-local-console", "version": "0.2.0"},
        },
    )
    mcp.notify("notifications/initialized")
    return mcp, mcp_tools_to_openai(mcp.request("tools/list", {}))


def trim_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(messages) <= MAX_CONTEXT_MESSAGES:
        return messages
    return [messages[0]] + messages[-(MAX_CONTEXT_MESSAGES - 1) :]


def run_tool_call(mcp: McpStdioClient, name: str, arguments: dict[str, Any]) -> str:
    if name in LOCAL_TOOL_FUNCS:
        result = LOCAL_TOOL_FUNCS[name](**arguments)
        return json.dumps(result, ensure_ascii=False)
    result = mcp.request("tools/call", {"name": name, "arguments": arguments})
    return result["content"][0]["text"]


def run_turn(mcp: McpStdioClient, tools: list[dict[str, Any]], messages: list[dict[str, Any]]) -> str:
    for _ in range(10):
        response = chat_completion(trim_messages(messages), tools)
        message = response["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []
        messages.append(message)
        if not tool_calls:
            return message.get("content", "")

        for call in tool_calls:
            function = call["function"]
            name = function["name"]
            raw_args = function.get("arguments") or "{}"
            arguments = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            text = run_tool_call(mcp, name, arguments)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": text})

    raise RuntimeError("Tool loop reached the maximum number of steps")


def print_help() -> None:
    print(
        """
命令：
  /help              显示帮助
  /tools             查看全部工具
  /reset             清空对话上下文
  /web 关键词         直接联网搜索
  /url 地址           抓取网页正文
  /sh 命令            在鸿蒙设备上执行 shell 命令
  /apps              列出常用鸿蒙应用别名
  /camera            打开相机
  /photo             打开相机并拍照
  /dial 电话号        打开拨号并填入号码
  /browse 关键词      打开浏览器并搜索
  /music             打开音乐
  /play              音乐播放/暂停
  /next              下一首
  /prev              上一首
  /volup             音量增加
  /voldown           音量减小
  /tcp               按默认参数请求 192.168.1.62:8000，发送 1
  /tcpsend 内容       按默认参数发送自定义一行
  /tcpstats          查看 TCP 请求统计
  /tcpreset          清空 TCP 请求统计
  /weather [城市]     查询天气
  /time              查看设备时间
  /exit              退出

也可以直接自然语言输入：
  打开设置
  给 10086 拨号
  打开浏览器搜索 OpenHarmony
  打开相机并拍照
  打开音乐然后下一首
  请求 192.168.1.62:8000 并发送 1
  执行 ls -la /data/A9
""".strip()
    )


def print_banner(tools: list[dict[str, Any]]) -> None:
    print("=" * 58)
    print(" HarmonyOS MCP Console")
    print(" 常规对话 | 联网搜索 | 鸿蒙操作 | 设备命令行")
    print(f" 工具数量: {len(tools)}    输入 /help 查看命令")
    print("=" * 58)


def handle_slash_command(
    command: str,
    mcp: McpStdioClient,
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> tuple[bool, bool]:
    try:
        if command in {"/exit", "exit", "quit", "q"}:
            return True, True
        if command == "/help":
            print_help()
            return True, False
        if command == "/reset":
            messages[:] = [system_message()]
            print("已清空上下文。")
            return True, False
        if command == "/tools":
            names = [tool["function"]["name"] for tool in tools]
            print("可用工具：")
            for name in names:
                print(f"  - {name}")
            return True, False
        if command == "/time":
            print(json.dumps(get_current_time(), ensure_ascii=False, indent=2))
            return True, False
        if command == "/apps":
            print(run_tool_call(mcp, "list_common_harmony_apps", {}))
            return True, False
        if command == "/camera":
            print(json.dumps(open_camera(), ensure_ascii=False, indent=2))
            return True, False
        if command == "/photo":
            print(json.dumps(take_photo(), ensure_ascii=False, indent=2))
            return True, False
        if command.startswith("/dial "):
            phone_number = command[6:].strip()
            print(json.dumps(dial_phone_number(phone_number), ensure_ascii=False, indent=2))
            return True, False
        if command.startswith("/browse "):
            query = command[8:].strip()
            print(json.dumps(open_browser_search(query), ensure_ascii=False, indent=2))
            return True, False
        if command == "/music":
            print(json.dumps(open_music(), ensure_ascii=False, indent=2))
            return True, False
        if command == "/play":
            print(json.dumps(music_play_pause(), ensure_ascii=False, indent=2))
            return True, False
        if command == "/next":
            print(json.dumps(music_next(), ensure_ascii=False, indent=2))
            return True, False
        if command == "/prev":
            print(json.dumps(music_previous(), ensure_ascii=False, indent=2))
            return True, False
        if command == "/volup":
            print(json.dumps(volume_up_tool(), ensure_ascii=False, indent=2))
            return True, False
        if command == "/voldown":
            print(json.dumps(volume_down_tool(), ensure_ascii=False, indent=2))
            return True, False
        if command == "/tcp":
            print(json.dumps(tcp_line_request(), ensure_ascii=False, indent=2))
            return True, False
        if command.startswith("/tcpsend "):
            message = command[9:].strip()
            print(json.dumps(tcp_line_request(message=message), ensure_ascii=False, indent=2))
            return True, False
        if command == "/tcpstats":
            print(json.dumps(tcp_request_stats(), ensure_ascii=False, indent=2))
            return True, False
        if command == "/tcpreset":
            print(json.dumps(tcp_request_reset_stats(), ensure_ascii=False, indent=2))
            return True, False
        if command.startswith("/weather"):
            location = command[len("/weather") :].strip()
            print(run_tool_call(mcp, "get_local_weather", {"location": location}))
            return True, False
        if command.startswith("/web "):
            query = command[5:].strip()
            print(json.dumps(web_search(query), ensure_ascii=False, indent=2))
            return True, False
        if command.startswith("/url "):
            url = command[5:].strip()
            print(json.dumps(fetch_url(url), ensure_ascii=False, indent=2))
            return True, False
        if command.startswith("/sh "):
            shell_command = command[4:].strip()
            print(json.dumps(run_shell_command(shell_command), ensure_ascii=False, indent=2))
            return True, False
        return False, False
    except Exception as exc:
        print(f"命令执行失败：{exc}")
        return True, False


def run_once(user_message: str) -> int:
    mcp, mcp_tools = initialize_mcp()
    tools = mcp_tools + LOCAL_TOOLS
    try:
        messages: list[dict[str, Any]] = [system_message(), {"role": "user", "content": user_message}]
        print(run_turn(mcp, tools, messages))
        return 0
    finally:
        mcp.close()


def run_repl() -> int:
    mcp, mcp_tools = initialize_mcp()
    tools = mcp_tools + LOCAL_TOOLS
    messages: list[dict[str, Any]] = [system_message()]
    history: list[str] = []
    try:
        print_banner(tools)
        while True:
            try:
                user_message = read_line_with_editing("\n你> ", history).strip()
            except EOFError:
                print()
                return 0
            except KeyboardInterrupt:
                print("\n已取消当前输入。")
                continue

            if not user_message:
                continue
            history.append(user_message)

            handled, should_exit = handle_slash_command(user_message, mcp, tools, messages)
            if should_exit:
                return 0
            if handled:
                continue

            messages.append({"role": "user", "content": user_message})
            try:
                answer = run_turn(mcp, tools, messages)
                print(f"\n助手> {answer}")
            except Exception as exc:
                print(f"\n错误> {exc}")


    finally:
        mcp.close()


def main() -> int:
    user_message = " ".join(sys.argv[1:]).strip()
    if user_message:
        return run_once(user_message)
    return run_repl()


if __name__ == "__main__":
    raise SystemExit(main())
