"""有界并发执行设备命令，保持输入顺序并隔离单设备失败。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable


def _success(result: Any) -> bool:
    if isinstance(result, dict):
        return bool(result.get("success", False))
    return bool(result)


def execute_device_commands(
    commands: list[dict[str, Any]],
    executor: Callable[[dict[str, Any]], Any],
    *,
    max_workers: int = 4,
) -> dict[str, Any]:
    safe_commands = [dict(command) for command in commands if isinstance(command, dict)][:16]
    if not safe_commands:
        return {"success": True, "successCount": 0, "failureCount": 0, "results": []}
    workers = max(1, min(int(max_workers), len(safe_commands), 6))
    ordered: list[dict[str, Any] | None] = [None] * len(safe_commands)

    def run(index: int, command: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        device_id = str(command.get("device_id", command.get("scene_id", "")))
        action = str(command.get("action", command.get("type", "")))
        try:
            raw = executor(command)
            ok = _success(raw)
            return index, {
                "deviceId": device_id, "action": action, "success": ok,
                "params": dict(command.get("params") or {}),
                "result": raw, "error": "" if ok else "设备返回失败",
            }
        except Exception as exc:
            return index, {
                "deviceId": device_id, "action": action, "success": False,
                "result": None, "error": str(exc)[:300],
            }

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="a9-device") as pool:
        futures = [pool.submit(run, index, command) for index, command in enumerate(safe_commands)]
        for future in as_completed(futures):
            index, item = future.result()
            ordered[index] = item

    results = [item for item in ordered if item is not None]
    success_count = sum(1 for item in results if item["success"])
    failure_count = len(results) - success_count
    return {
        "success": failure_count == 0,
        "successCount": success_count,
        "failureCount": failure_count,
        "results": results,
    }
