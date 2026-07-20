"""并发硬件命令使用的中央控制器状态持久化补丁。"""

from __future__ import annotations

import functools
import json
import os
import secrets
import threading
from pathlib import Path
from typing import Any


_LOCKS_GUARD = threading.Lock()
_STATE_LOCKS: dict[str, threading.RLock] = {}


def _state_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        lock = _STATE_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _STATE_LOCKS[key] = lock
        return lock


def _atomic_json_write(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f"{path.name}.tmp.{os.getpid()}.{threading.get_ident()}.{secrets.token_hex(4)}"
    )
    try:
        with open(temporary, "w", encoding="utf-8") as state_file:
            json.dump(state, state_file, ensure_ascii=False, indent=2)
            state_file.write("\n")
            state_file.flush()
            os.fsync(state_file.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def install_controller_concurrency(controller: Any) -> bool:
    """只串行化限流状态事务，硬件网络调用仍可并发执行。"""
    if controller is None or not hasattr(controller, "state_file_path"):
        return False
    if getattr(controller, "_a9_concurrency_patch_installed", False):
        return True
    if not hasattr(controller, "enforce_rate_limit"):
        return False

    original_enforce_rate_limit = controller.enforce_rate_limit

    def save_state(config: dict[str, Any], state: dict[str, Any]) -> None:
        path = Path(controller.state_file_path(config))
        with _state_lock(path):
            _atomic_json_write(path, state)

    @functools.wraps(original_enforce_rate_limit)
    def enforce_rate_limit(config: dict[str, Any], action_key: str) -> Any:
        path = Path(controller.state_file_path(config))
        with _state_lock(path):
            return original_enforce_rate_limit(config, action_key)

    controller.save_state = save_state
    controller.enforce_rate_limit = enforce_rate_limit
    controller._a9_concurrency_patch_installed = True
    return True
