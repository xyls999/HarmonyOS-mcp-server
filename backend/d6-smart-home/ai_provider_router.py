"""Safe AI provider routing for text and multimodal A9 conversations."""

from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen


TEXT_CHAIN = ("deepseek", "codex")
MULTIMODAL_CHAIN = ("iflytek", "codex")
_MULTIMODAL_TYPES = {
    "image", "image_url", "input_image", "audio", "input_audio",
    "video", "input_video", "file", "input_file",
}


@dataclass(frozen=True)
class CompletionResult:
    text: str
    provider: str
    errors: tuple[str, ...] = ()


def contains_multimodal_content(messages: list[dict[str, Any]]) -> bool:
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and str(part.get("type", "")).lower() in _MULTIMODAL_TYPES:
                return True
    return False


def extract_text_content(content: Any) -> str:
    """Return only textual parts, never embedded binary/data URLs."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    chunks = []
    for part in content:
        if not isinstance(part, dict):
            continue
        if str(part.get("type", "")).lower() in ("text", "input_text", "output_text"):
            value = part.get("text")
            if isinstance(value, str):
                chunks.append(value)
    return "\n".join(chunks)


def _safe_error(provider: str, exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        return f"{provider}:HTTP {exc.code}"
    return f"{provider}:{type(exc).__name__}"


def _responses_content(content: Any) -> Any:
    if not isinstance(content, list):
        return content
    converted = []
    for part in content:
        if not isinstance(part, dict):
            continue
        item = dict(part)
        part_type = str(item.get("type", "")).lower()
        if part_type == "text":
            item = {"type": "input_text", "text": str(item.get("text", ""))}
        elif part_type == "image_url":
            image_url = item.get("image_url")
            if isinstance(image_url, dict):
                image_url = image_url.get("url", "")
            item = {"type": "input_image", "image_url": image_url}
        converted.append(item)
    return converted


def _extract_text(payload: dict[str, Any], wire_api: str) -> str:
    if wire_api == "responses":
        direct = payload.get("output_text")
        if isinstance(direct, str) and direct:
            return direct
        chunks = []
        for output in payload.get("output", []):
            if not isinstance(output, dict):
                continue
            for part in output.get("content", []):
                if isinstance(part, dict) and part.get("type") in ("output_text", "text"):
                    text = part.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
        return "".join(chunks)
    choices = payload.get("choices", [])
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message", {})
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"]
    return ""


class ProviderRouter:
    def __init__(
        self,
        models: dict[str, dict[str, Any]],
        *,
        opener: Callable[..., Any] = urlopen,
        ssl_context: ssl.SSLContext | None = None,
        timeout: float = 30,
        logger: Callable[[str], None] | None = None,
    ):
        self.models = models
        self.opener = opener
        self.ssl_context = ssl_context
        self.timeout = timeout
        self.logger = logger

    def _body(self, cfg: dict[str, Any], messages: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        wire_api = str(cfg.get("wireApi", "chat_completions")).lower()
        if wire_api == "responses":
            response_input = [
                {"role": message.get("role", "user"), "content": _responses_content(message.get("content", ""))}
                for message in messages
            ]
            body = {
                "model": cfg.get("model", ""),
                "input": response_input,
                "max_output_tokens": int(cfg.get("maxTokens", 512)),
                "store": False,
            }
            effort = cfg.get("reasoningEffort")
            if effort:
                body["reasoning"] = {"effort": str(effort).lower()}
            return wire_api, body
        return wire_api, {
            "model": cfg.get("model", ""),
            "messages": messages,
            "temperature": cfg.get("temperature", 0.3),
            "max_tokens": int(cfg.get("maxTokens", 512)),
        }

    def complete(self, messages: list[dict[str, Any]], preferred_provider: str = "") -> CompletionResult:
        default_chain = MULTIMODAL_CHAIN if contains_multimodal_content(messages) else TEXT_CHAIN
        preferred_provider = str(preferred_provider or "").strip()
        chain = ((preferred_provider,) + tuple(item for item in default_chain if item != preferred_provider)
                 if preferred_provider else default_chain)
        errors = []
        for provider in chain:
            cfg = self.models.get(provider, {})
            url = str(cfg.get("url", "")).strip()
            key = str(cfg.get("key", "")).strip()
            requires_key = bool(cfg.get("requiresKey", True))
            if not url or (requires_key and not key):
                errors.append(f"{provider}:not_configured")
                continue
            wire_api, body = self._body(cfg, messages)
            headers = {"Content-Type": "application/json"}
            if key:
                headers["Authorization"] = f"Bearer {key}"
            request = Request(
                url,
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            try:
                kwargs: dict[str, Any] = {"timeout": float(cfg.get("timeout", self.timeout))}
                if self.ssl_context is not None:
                    kwargs["context"] = self.ssl_context
                with self.opener(request, **kwargs) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                text = _extract_text(payload, wire_api)
                if not text:
                    raise ValueError("empty provider response")
                return CompletionResult(text=text, provider=provider, errors=tuple(errors))
            except Exception as exc:
                safe = _safe_error(provider, exc)
                if isinstance(exc, HTTPError):
                    exc.close()
                errors.append(safe)
                if self.logger:
                    self.logger(f"[AI-ROUTER] {safe}")
        return CompletionResult(
            text="（AI上游暂时不可用，请稍后重试）",
            provider="unavailable",
            errors=tuple(errors),
        )
