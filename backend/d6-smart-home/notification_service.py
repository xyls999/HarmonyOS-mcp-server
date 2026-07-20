"""QQ/Qmsg notification adapter with cooldown and secret-safe logging."""

from __future__ import annotations

import json
import os
import ssl
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Callable
from urllib.request import Request, urlopen


_CST = timezone(timedelta(hours=8))


class NotificationService:
    def __init__(
        self,
        config: dict[str, Any],
        *,
        opener: Callable[..., Any] = urlopen,
        logger: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.time,
        ssl_context: ssl.SSLContext | None = None,
    ):
        self.config = dict(config or {})
        self.opener = opener
        self.logger = logger or (lambda _text: None)
        self.clock = clock
        self.ssl_context = ssl_context
        self.last_sent: dict[str, float] = {}

    @classmethod
    def from_environment(cls, *, logger=None, ssl_context=None):
        qmsg_key = os.environ.get("QMSG_KEY", "")
        webhook = os.environ.get("QQ_PUSH_URL", "")
        return cls({
            "enabled": bool(qmsg_key or webhook),
            "mode": os.environ.get("QQ_PUSH_MODE", "qmsg" if qmsg_key else "onebot"),
            "qmsgKey": qmsg_key,
            "webhookUrl": webhook,
            "groupId": os.environ.get("QQ_GROUP_ID", ""),
            "userId": os.environ.get("QQ_USER_ID", ""),
            "token": os.environ.get("QQ_PUSH_TOKEN", ""),
            "cooldownSeconds": int(os.environ.get("QQ_PUSH_COOLDOWN", "60")),
        }, logger=logger, ssl_context=ssl_context)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.config.get("enabled")),
            "mode": self.config.get("mode", "onebot"),
            "configured": bool(self.config.get("qmsgKey") or self.config.get("webhookUrl")),
            "groupConfigured": bool(self.config.get("groupId")),
            "userConfigured": bool(self.config.get("userId")),
            "cooldownSeconds": int(self.config.get("cooldownSeconds", 60)),
        }

    def send(self, event_type: str, title: str, message: str, extra: dict[str, Any] | None = None) -> bool:
        if not self.config.get("enabled"):
            return False
        key = f"{event_type}:{title[:80]}"
        now = float(self.clock())
        cooldown = max(0, int(self.config.get("cooldownSeconds", 60)))
        if now - self.last_sent.get(key, -1e12) < cooldown:
            return False
        mode = str(self.config.get("mode", "onebot")).lower()
        timestamp = datetime.now(_CST).strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"【{title[:120]}】", f"时间：{timestamp}", str(message)[:2000]]
        for item_key, value in (extra or {}).items():
            if str(item_key).lower() in ("password", "token", "secret", "authorization"):
                continue
            lines.append(f"{str(item_key)[:80]}：{str(value)[:200]}")
        text = "\n".join(lines)
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if mode == "qmsg":
            qmsg_key = str(self.config.get("qmsgKey", "")).strip()
            if not qmsg_key:
                return False
            url = f"https://qmsg.zendee.cn/send/{qmsg_key}"
            body = {"msg": text}
        else:
            url = str(self.config.get("webhookUrl", "")).strip()
            if not url:
                return False
            token = str(self.config.get("token", "")).strip()
            if token:
                headers["Authorization"] = f"Bearer {token}"
            if "send_group_msg" in url and self.config.get("groupId"):
                body = {"group_id": int(self.config["groupId"]), "message": text}
            elif "send_private_msg" in url and self.config.get("userId"):
                body = {"user_id": int(self.config["userId"]), "message": text}
            else:
                body = {"title": title[:120], "content": text, "event_type": event_type, "timestamp": timestamp}
        request = Request(
            url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            kwargs: dict[str, Any] = {"timeout": 10}
            if self.ssl_context is not None and url.startswith("https://"):
                kwargs["context"] = self.ssl_context
            with self.opener(request, **kwargs) as response:
                response.read()
                success = 200 <= int(getattr(response, "status", 200)) < 300
            if success:
                self.last_sent[key] = now
                self.logger(f"[NOTIFY] sent type={event_type} mode={mode}")
                return True
            self.logger(f"[NOTIFY] failed type={event_type} mode={mode} status=non_2xx")
        except Exception as exc:
            self.logger(f"[NOTIFY] failed type={event_type} mode={mode} error={type(exc).__name__}")
        return False
