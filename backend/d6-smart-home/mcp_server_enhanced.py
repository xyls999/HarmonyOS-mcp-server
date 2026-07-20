#!/usr/bin/env python3
"""A9 SuperMCP stdio transport.

One JSON-RPC object is read per line. Protocol output is the only content sent
to stdout; gateway initialization and business logs are redirected to stderr.
"""

from __future__ import annotations

import json
import sys
from contextlib import redirect_stdout


MAX_LINE_BYTES = 1024 * 1024


def _prepare_gateway():
    with redirect_stdout(sys.stderr):
        import gateway_v6 as gateway

        gateway.db_init()
        gateway._init_api_key_db()
        if gateway._intent_engine is None:
            gateway._intent_engine = gateway.IntentEngine(
                get_context_fn=gateway._get_intent_context,
                get_status_fn=gateway._get_anomaly_status,
                db_path=str(gateway.DB_PATH),
                log_fn=gateway.log,
                tts_fn=gateway._tts_speak,
            )

            def linkage_executor(intent):
                intent_type = intent.get("type", "")
                device_id = intent.get("device_id", "")
                if device_id == "door_01":
                    return {"success": False, "error": "door actions require one-call manual password"}
                if intent_type == "device_toggle":
                    return gateway.hw_toggle(device_id, intent.get("isOn", True))
                if intent_type == "device_control":
                    return gateway.hw_control(
                        device_id,
                        intent.get("action", "toggle"),
                        intent.get("params", {}),
                    )
                return None

            gateway._intent_engine.set_linkage_executor(linkage_executor)
        gateway._load_linkage_config()
        gateway._sync_kv_from_code()
        gateway._update_kv_realtime()
        gateway._initialize_super_context()
    return gateway


def _write(payload):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main():
    gateway = _prepare_gateway()
    for raw_line in sys.stdin.buffer:
        if not raw_line.strip():
            continue
        if len(raw_line) > MAX_LINE_BYTES:
            _write({
                "jsonrpc": "2.0", "id": None,
                "error": {"code": -32600, "message": "Request exceeds 1 MiB"},
            })
            continue
        try:
            message = json.loads(raw_line.decode("utf-8"))
        except (UnicodeError, ValueError):
            _write({
                "jsonrpc": "2.0", "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            })
            continue
        with redirect_stdout(sys.stderr):
            response = gateway._super_mcp.dispatch(message, auth=None)
        if response is not None:
            _write(response)


if __name__ == "__main__":
    main()
