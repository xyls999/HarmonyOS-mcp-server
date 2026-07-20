"""MCP 2025-11-25 protocol core for the A9 smart-home backend.

The dispatcher is transport-neutral: HTTP and stdio wrappers share the same
resource catalogue, tool schemas, validation, authorization, and audit logic.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote


PROTOCOL_VERSION = "2025-11-25"
COMPATIBLE_VERSIONS = {PROTOCOL_VERSION, "2025-03-26"}


def _object_schema(properties=None, required=None, *, additional=False):
    return {
        "type": "object",
        "properties": properties or {},
        "required": required or [],
        "additionalProperties": additional,
    }


def _tool(name, description, schema, *, read_only, destructive=False, idempotent=False):
    return {
        "name": name,
        "description": description,
        "inputSchema": schema,
        "annotations": {
            "readOnlyHint": read_only,
            "destructiveHint": destructive,
            "idempotentHint": idempotent,
            "openWorldHint": False,
        },
    }


TOOL_DEFINITIONS = [
    _tool("search_context", "搜索全部项目源码、文档、设备、能力、操作和日志上下文。", _object_schema({"query": {"type": "string", "minLength": 1}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, ["query"]), read_only=True),
    _tool("get_project_overview", "读取脱敏后的项目总览和上下文清单。", _object_schema(), read_only=True),
    _tool("get_context_stats", "读取上下文文档、实体和事件统计。", _object_schema(), read_only=True),
    _tool("get_live_status", "读取服务端、设备和传感器实时状态。", _object_schema(), read_only=True),
    _tool("list_devices", "列出当前全部设备；新注册设备会自动出现。", _object_schema(), read_only=True),
    _tool("get_device", "按设备 ID 读取状态与能力。", _object_schema({"device_id": {"type": "string", "minLength": 1}}, ["device_id"]), read_only=True),
    _tool("list_sensors", "列出当前全部传感器及读数。", _object_schema(), read_only=True),
    _tool("get_recent_operations", "读取近期设备操作。", _object_schema({"device_id": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 500}}), read_only=True),
    _tool("get_recent_logs", "读取近期脱敏日志事件。", _object_schema({"limit": {"type": "integer", "minimum": 1, "maximum": 500}, "severity": {"type": "string"}}), read_only=True),
    _tool("get_linkage_config", "读取联动配置。", _object_schema(), read_only=True),
    _tool("get_guard_status", "读取主动/被动警戒状态、当前等级、最近事件和待主人评分数量。", _object_schema(), read_only=True),
    _tool("get_pending_guard_feedback", "读取等待主人进行 0-10 评分的自动联动事件。", _object_schema({"limit": {"type": "integer", "minimum": 1, "maximum": 200}}), read_only=True),
    _tool("get_guard_learning", "按问题匹配历史评分、改进建议和长期学习摘要。", _object_schema({"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}), read_only=True),
    _tool("get_radar_config", "读取毫米波存在感知与灯光联动两个独立开关。", _object_schema(), read_only=True),
    _tool("list_capabilities", "列出所有内置和自定义能力。", _object_schema(), read_only=True),
    _tool("toggle_device", "开关普通设备；门禁设备不得使用此工具绕过人工密码。", _object_schema({"device_id": {"type": "string", "minLength": 1}, "is_on": {"type": "boolean"}}, ["device_id", "is_on"]), read_only=False, idempotent=True),
    _tool("control_device", "控制设备参数；门禁设备不得使用此工具绕过人工密码。", _object_schema({"device_id": {"type": "string", "minLength": 1}, "action": {"type": "string", "minLength": 1}, "value": {}, "mode": {"type": "string"}}, ["device_id", "action"]), read_only=False),
    _tool("activate_scene", "执行场景；自动场景不得包含门禁开关。", _object_schema({"scene_id": {"type": "string", "minLength": 1}}, ["scene_id"]), read_only=False),
    _tool("set_linkage_config", "更新指定自动联动配置。", _object_schema({"rule_key": {"type": "string", "minLength": 1}, "config": {"type": "object"}}, ["rule_key", "config"]), read_only=False, idempotent=True),
    _tool("set_guard_config", "更新自适应警戒总开关、主动 AI 和规则阈值；开启/关闭会语音汇报。", _object_schema({"config": {"type": "object"}}, ["config"]), read_only=False, idempotent=True),
    _tool("submit_guard_feedback", "主人对自动联动提交 0-10 分和改进建议，持久化用于后续同类警戒。", _object_schema({"incident_id": {"type": "integer", "minimum": 1}, "score": {"type": "integer", "minimum": 0, "maximum": 10}, "better_action": {"type": "string"}, "notes": {"type": "string"}}, ["incident_id", "score"]), read_only=False, idempotent=True),
    _tool("set_radar_enabled", "单独设置毫米波人体存在功能，不改变雷达灯光联动。", _object_schema({"enabled": {"type": "boolean"}}, ["enabled"]), read_only=False, idempotent=True),
    _tool("register_device", "注册自定义设备并立即同步到 JSON、数据库、RAG 和通用控制工具。", _object_schema({"device": {"type": "object"}}, ["device"]), read_only=False),
    _tool("unregister_device", "注销自定义设备。", _object_schema({"device_id": {"type": "string", "minLength": 1}}, ["device_id"]), read_only=False, destructive=True),
    _tool("register_capability", "注册白名单执行器类型的自定义能力。", _object_schema({"capability": {"type": "object"}}, ["capability"]), read_only=False),
    _tool("invoke_capability", "调用已注册的自定义能力；只允许服务端安全白名单执行器，禁止门禁、shell、文件、表达式和任意 URL。", _object_schema({"capability_id": {"type": "string", "minLength": 1}, "arguments": {"type": "object"}}, ["capability_id"]), read_only=False),
    _tool("rebuild_context", "重新采集项目资料、数据库状态并原子生成 JSON 快照。", _object_schema(), read_only=False, idempotent=True),
    _tool("door_control", "门禁查询或开关。开门/关门必须由用户在本次调用人工输入 password；禁止历史、环境变量、模型或自动化补取。", _object_schema({"action": {"type": "string", "enum": ["query", "open", "close"]}, "password": {"type": "string", "minLength": 1}}, ["action"]), read_only=False, destructive=True),
]


RESOURCE_DEFINITIONS = [
    ("a9://project/manifest", "A9 project manifest", "完整脱敏项目上下文清单"),
    ("a9://project/capabilities", "A9 capabilities", "设备与自定义能力"),
    ("a9://devices", "A9 devices", "全部设备及状态"),
    ("a9://sensors", "A9 sensors", "全部传感器及状态"),
    ("a9://scenes", "A9 scenes", "全部场景"),
    ("a9://automations", "A9 automations", "联动与自动化规则"),
    ("a9://apis", "A9 APIs", "HTTP 和内部接口"),
    ("a9://security/policy", "A9 security policy", "门禁、毫米波与凭据安全边界"),
    ("a9://context/stats", "A9 context statistics", "上下文采集统计"),
]


class InvalidParams(ValueError):
    pass


class SuperMCP:
    def __init__(self, context_engine, tool_handlers: dict[str, Callable] | None = None):
        self.context_engine = context_engine
        self.tool_handlers = dict(tool_handlers or {})
        self._definitions = {tool["name"]: tool for tool in TOOL_DEFINITIONS}
        self.tool_handlers.update(
            {
                "search_context": self._search_context,
                "get_project_overview": self._project_overview,
                "get_context_stats": self._context_stats,
                "rebuild_context": self._rebuild_context,
            }
        )

    @staticmethod
    def _response(request_id, *, result=None, error=None):
        response = {"jsonrpc": "2.0", "id": request_id}
        if error is not None:
            response["error"] = error
        else:
            response["result"] = result
        return response

    @classmethod
    def _error(cls, request_id, code, message, data=None):
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return cls._response(request_id, error=error)

    def list_tools(self):
        return [dict(tool) for tool in TOOL_DEFINITIONS]

    def list_resources(self):
        return [
            {"uri": uri, "name": name, "description": description, "mimeType": "application/json"}
            for uri, name, description in RESOURCE_DEFINITIONS
        ]

    def _snapshot(self):
        path = Path(self.context_engine.snapshot_path)
        if not path.exists():
            return self.context_engine.rebuild_snapshot()
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return self.context_engine.rebuild_snapshot()

    def read_resource(self, uri: str):
        snapshot = self._snapshot()
        mapping = {
            "a9://project/manifest": snapshot,
            "a9://project/capabilities": snapshot.get("capabilities", []),
            "a9://devices": snapshot.get("devices", []),
            "a9://sensors": snapshot.get("sensors", []),
            "a9://scenes": snapshot.get("scenes", []),
            "a9://automations": snapshot.get("automations", []),
            "a9://apis": snapshot.get("apis", []),
            "a9://security/policy": snapshot.get("safety", {}),
            "a9://context/stats": snapshot.get("collectionStats", {}),
        }
        if uri.startswith("a9://context/search/"):
            query = unquote(uri.removeprefix("a9://context/search/"))
            if not query:
                raise InvalidParams("search resource requires a query")
            return self.context_engine.search(query)
        if uri not in mapping:
            raise InvalidParams(f"unknown resource URI: {uri}")
        return mapping[uri]

    def _search_context(self, query, limit=40):
        return {"query": query, "matches": self.context_engine.search(query, limit=limit)}

    def _project_overview(self):
        return self._snapshot()

    def _context_stats(self):
        return self._snapshot().get("collectionStats", {})

    def _rebuild_context(self):
        static = self.context_engine.collect_static_sources()
        database = self.context_engine.collect_database_state()
        snapshot = self.context_engine.rebuild_snapshot()
        return {"static": static, "database": database, "snapshot": snapshot["collectionStats"]}

    @classmethod
    def _validate(cls, value, schema, path="arguments"):
        expected = schema.get("type")
        type_map = {
            "object": dict, "array": list, "string": str,
            "integer": int, "number": (int, float), "boolean": bool,
        }
        if expected in type_map:
            expected_type = type_map[expected]
            if expected == "integer" and isinstance(value, bool):
                raise InvalidParams(f"{path} must be an integer")
            if not isinstance(value, expected_type):
                raise InvalidParams(f"{path} must be {expected}")
        if "enum" in schema and value not in schema["enum"]:
            raise InvalidParams(f"{path} must be one of {schema['enum']}")
        if isinstance(value, str) and len(value) < schema.get("minLength", 0):
            raise InvalidParams(f"{path} is too short")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                raise InvalidParams(f"{path} is below minimum")
            if "maximum" in schema and value > schema["maximum"]:
                raise InvalidParams(f"{path} exceeds maximum")
        if expected == "object":
            for required in schema.get("required", []):
                if required not in value:
                    raise InvalidParams(f"missing required parameter: {required}")
            properties = schema.get("properties", {})
            if schema.get("additionalProperties") is False:
                unknown = set(value) - set(properties)
                if unknown:
                    raise InvalidParams(f"unknown parameters: {', '.join(sorted(unknown))}")
            for key, item in value.items():
                if key in properties and properties[key]:
                    cls._validate(item, properties[key], f"{path}.{key}")

    @staticmethod
    def _tool_result(value, *, is_error=False):
        if isinstance(value, str):
            text = value
            structured = {"message": value}
        else:
            structured = value if isinstance(value, dict) else {"result": value}
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        return {
            "content": [{"type": "text", "text": text}],
            "structuredContent": structured,
            "isError": bool(is_error),
        }

    @staticmethod
    def _has_write_scope(auth):
        if auth is None:  # Local stdio transport is trusted by its process boundary.
            return True
        scopes = set(auth.get("scopes", []))
        return bool(scopes & {"write", "admin"})

    def _call_tool(self, name, arguments, auth):
        definition = self._definitions.get(name)
        if definition is None:
            raise InvalidParams(f"unknown tool: {name}")
        self._validate(arguments, definition["inputSchema"])
        is_write = not definition["annotations"]["readOnlyHint"]
        if name == "door_control" and arguments.get("action") == "query":
            is_write = False
        if is_write and not self._has_write_scope(auth):
            return self._tool_result({"error": "write scope required"}, is_error=True)
        if name == "door_control" and arguments.get("action") in {"open", "close"}:
            if not arguments.get("password"):
                self._audit(name, arguments, False, 0, "password required for this request")
                return self._tool_result(
                    {"error": "door password must be manually supplied for this request"},
                    is_error=True,
                )
        handler = self.tool_handlers.get(name)
        if handler is None:
            return self._tool_result({"error": f"tool handler unavailable: {name}"}, is_error=True)
        started = time.monotonic()
        try:
            result = handler(**arguments)
            safe_result = self.context_engine.redact_sensitive(result)
            business_failed = isinstance(safe_result, dict) and (
                safe_result.get("success") is False
                or bool(safe_result.get("error"))
            )
            error_text = str(safe_result.get("error", "")) if business_failed else ""
            self._audit(
                name, arguments, not business_failed,
                int((time.monotonic() - started) * 1000), error_text,
            )
            return self._tool_result(safe_result, is_error=business_failed)
        except Exception as exc:  # Business failure belongs in CallToolResult.
            safe_error = str(self.context_engine.redact_sensitive(str(exc)))
            self._audit(name, arguments, False, int((time.monotonic() - started) * 1000), safe_error)
            return self._tool_result({"error": safe_error}, is_error=True)

    def _audit(self, name, arguments, success, elapsed_ms, error=""):
        safe_arguments = dict(arguments)
        if "password" in safe_arguments:
            safe_arguments.pop("password", None)
            safe_arguments["passwordProvided"] = bool(arguments.get("password"))
        self.context_engine.record_event(
            "mcp_tool_call",
            f"MCP tool {name} {'succeeded' if success else 'failed'}",
            details={
                "tool": name, "arguments": safe_arguments, "success": success,
                "elapsedMs": elapsed_ms, "error": error,
            },
            source="mcp",
            severity="info" if success else "warning",
        )

    def dispatch(self, message: dict, auth: dict | None = None):
        request_id = message.get("id") if isinstance(message, dict) else None
        is_notification = isinstance(message, dict) and "id" not in message
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            return None if is_notification else self._error(request_id, -32600, "Invalid Request")
        method = message["method"]
        params = message.get("params", {})
        try:
            if method == "notifications/initialized":
                return None
            if method == "initialize":
                if not isinstance(params, dict):
                    raise InvalidParams("initialize params must be an object")
                requested = params.get("protocolVersion", PROTOCOL_VERSION)
                if requested not in COMPATIBLE_VERSIONS:
                    raise InvalidParams(f"unsupported protocol version: {requested}")
                result = {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": True}, "resources": {"subscribe": False, "listChanged": True}},
                    "serverInfo": {"name": "a9-super-context-mcp", "version": "1.0.0"},
                    "instructions": "Use resources and search_context before control. Door open/close requires a manually supplied one-call password.",
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self.list_tools()}
            elif method == "tools/call":
                if not isinstance(params, dict) or not isinstance(params.get("name"), str):
                    raise InvalidParams("tools/call requires a tool name")
                arguments = params.get("arguments", {})
                if not isinstance(arguments, dict):
                    raise InvalidParams("tool arguments must be an object")
                result = self._call_tool(params["name"], arguments, auth)
            elif method == "resources/list":
                result = {"resources": self.list_resources()}
            elif method == "resources/templates/list":
                result = {"resourceTemplates": [{
                    "uriTemplate": "a9://context/search/{query}",
                    "name": "A9 context search", "description": "Search the full A9 context corpus",
                    "mimeType": "application/json",
                }]}
            elif method == "resources/read":
                if not isinstance(params, dict) or not isinstance(params.get("uri"), str):
                    raise InvalidParams("resources/read requires uri")
                resource = self.read_resource(params["uri"])
                result = {"contents": [{
                    "uri": params["uri"], "mimeType": "application/json",
                    "text": json.dumps(self.context_engine.redact_sensitive(resource), ensure_ascii=False, sort_keys=True),
                }]}
            else:
                return None if is_notification else self._error(request_id, -32601, "Method not found")
        except InvalidParams as exc:
            return None if is_notification else self._error(request_id, -32602, "Invalid params", str(exc))
        return None if is_notification else self._response(request_id, result=result)
