"""
Dependency-free MCP stdio server for running directly on HarmonyOS.

It implements the small MCP surface needed by clients:
- initialize
- notifications/initialized
- tools/list
- tools/call
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any, Callable
from urllib.parse import quote
from urllib.request import Request, urlopen


COMMON_HARMONY_APPS = {
    "settings": "com.ohos.settings",
    "设置": "com.ohos.settings",
    "camera": "com.ohos.camera",
    "相机": "com.ohos.camera",
    "gallery": "com.ohos.photos",
    "图库": "com.ohos.photos",
    "browser": "ohos.samples.browser1",
    "浏览器": "ohos.samples.browser1",
    "contacts": "com.ohos.contacts",
    "联系人": "com.ohos.contacts",
    "messages": "com.ohos.mms",
    "短信": "com.ohos.mms",
    "files": "com.ohos.filemanager",
    "文件": "com.ohos.filemanager",
    "clock": "ohos.samples.etsclock",
    "时钟": "ohos.samples.etsclock",
    "notes": "com.ohos.note",
    "备忘录": "com.ohos.note",
    "music": "ohos.samples.distributedmusicplayer",
    "音乐": "ohos.samples.distributedmusicplayer",
    "recorder": "ohos.samples.recorder",
    "录音": "ohos.samples.recorder",
    "device_info": "org.ohosdev.deviceinfo",
    "设备信息": "org.ohosdev.deviceinfo",
    "bilibili": "com.wathinst.ohbili",
    "b站": "com.wathinst.ohbili",
    "tetris": "org.ohosdev.tetris",
    "俄罗斯方块": "org.ohosdev.tetris",
}


def run_cmd(cmd: list[str], timeout: int = 10) -> tuple[bool, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        output = result.stdout if result.returncode == 0 else result.stderr
        return result.returncode == 0, output
    except Exception as exc:
        return False, str(exc)


def list_app() -> list[str]:
    ok, output = run_cmd(["bm", "dump", "-a"])
    if not ok:
        return [f"[Fail] {output}"]
    return [line.strip() for line in output.splitlines() if line.strip() and not line.startswith("ID")]


def list_common_harmony_apps() -> dict[str, str]:
    return COMMON_HARMONY_APPS


def launch_harmony_app(name_or_alias: str) -> str:
    query = name_or_alias.strip()
    package_name = COMMON_HARMONY_APPS.get(query, query)
    apps = list_app()
    if package_name not in apps:
        matches = [app for app in apps if query.lower() in app.lower()]
        if len(matches) == 1:
            package_name = matches[0]
        elif len(matches) > 1:
            return f"[Fail] multiple apps matched: {matches[:20]}"
        else:
            return f"[Fail] app `{name_or_alias}` not found."

    ok, output = run_cmd(["bm", "dump", "-n", package_name])
    if not ok:
        return f"[Fail] {output}"

    json_start = output.find("{")
    if json_start == -1:
        return f"[Fail] cannot parse package info for {package_name}"

    info = json.loads(output[json_start:])
    module = info["hapModuleInfos"][0]
    bundle_name = module["bundleName"]
    ability = module["mainAbility"]
    ok, output = run_cmd(["aa", "start", "-b", bundle_name, "-a", ability])
    return f"[Success] {output}" if ok else f"[Fail] {output}"


def get_local_weather(location: str = "") -> dict[str, Any]:
    path = f"/{quote(location.strip())}" if location.strip() else ""
    request = Request(f"https://wttr.in{path}?format=j1", headers={"User-Agent": "HarmonyOS-MCP/standalone"})
    with urlopen(request, timeout=10) as response:
        data = json.loads(response.read().decode("utf-8"))
    current = data.get("current_condition", [{}])[0]
    nearest = data.get("nearest_area", [{}])[0]
    area = nearest.get("areaName", [{}])[0].get("value", "")
    country = nearest.get("country", [{}])[0].get("value", "")
    return {
        "location": location or f"{area}, {country}".strip(", "),
        "temperature_c": current.get("temp_C"),
        "feels_like_c": current.get("FeelsLikeC"),
        "humidity": current.get("humidity"),
        "wind_kmph": current.get("windspeedKmph"),
        "condition": current.get("weatherDesc", [{}])[0].get("value", ""),
        "observation_time": current.get("observation_time"),
    }


TOOLS: dict[str, Callable[..., Any]] = {
    "list_app": list_app,
    "list_common_harmony_apps": list_common_harmony_apps,
    "launch_harmony_app": launch_harmony_app,
    "get_local_weather": get_local_weather,
}


def tool_schema() -> list[dict[str, Any]]:
    return [
        {
            "name": "list_app",
            "description": "List installed HarmonyOS bundle names.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "list_common_harmony_apps",
            "description": "List friendly aliases for common HarmonyOS apps.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "launch_harmony_app",
            "description": "Launch a HarmonyOS app by alias, bundle name, or fuzzy keyword.",
            "inputSchema": {
                "type": "object",
                "properties": {"name_or_alias": {"type": "string"}},
                "required": ["name_or_alias"],
            },
        },
        {
            "name": "get_local_weather",
            "description": "Get current weather by IP location or city name.",
            "inputSchema": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
            },
        },
    ]


def respond(message_id: Any, result: Any = None, error: Any = None) -> None:
    payload = {"jsonrpc": "2.0", "id": message_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        request = json.loads(line)
        method = request.get("method")
        message_id = request.get("id")

        if method == "initialize":
            respond(
                message_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "harmonyos-standalone", "version": "0.1.0"},
                },
            )
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            respond(message_id, {"tools": tool_schema()})
        elif method == "tools/call":
            params = request.get("params", {})
            name = params.get("name", "")
            args = params.get("arguments", {})
            if name not in TOOLS:
                respond(message_id, error={"code": -32602, "message": f"Unknown tool: {name}"})
                continue
            try:
                result = TOOLS[name](**args)
                respond(message_id, {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]})
            except Exception as exc:
                respond(message_id, error={"code": -32000, "message": str(exc)})
        else:
            respond(message_id, error={"code": -32601, "message": f"Unknown method: {method}"})


if __name__ == "__main__":
    main()
