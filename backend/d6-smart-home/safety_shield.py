#!/usr/bin/env python3
"""
智慧家居安全护栏 v1.0
参考 Aperion Shield 规则引擎思路，纯标准库 Python 实现
嵌入 gateway_v5.py 消息处理链最前端，拦截不安全指令

严重度 → 处理方式:
  Critical → 直接拦截 + TTS播报 + 高危日志
  High     → 拦截 + 警告 + 日志
  Medium   → 放行 + 警告标记 + 日志
  Low      → 仅审计日志
"""
from __future__ import annotations
import re
import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════

@dataclass
class ShieldResult:
    """安全检查结果"""
    blocked: bool = False
    rule_id: str = ""
    severity: str = "Low"       # Critical / High / Medium / Low
    category: str = ""          # shell / prompt / device / network / config
    reason: str = ""
    matched_text: str = ""      # 命中的具体文本片段
    safer_alternative: str = "" # 安全替代建议


@dataclass
class _Rule:
    """单条安全规则"""
    rule_id: str
    severity: str
    category: str
    patterns: list             # 正则表达式列表
    reason: str
    safer_alternative: str = ""
    context_filter: list = field(default_factory=list)  # 适用的 context 列表，空=全部
    _compiled: list = field(default_factory=list, repr=False)

    def __post_init__(self):
        self._compiled = []
        for p in self.patterns:
            try:
                self._compiled.append(re.compile(p, re.IGNORECASE))
            except re.error:
                pass  # 跳过无效正则


# ═══════════════════════════════════════════════════════════════
# 频率追踪器 (防暴力/防滥用)
# ═══════════════════════════════════════════════════════════════

class _RateTracker:
    """线程安全的频率追踪器"""
    def __init__(self):
        self._lock = threading.Lock()
        self._events: dict[str, list[float]] = defaultdict(list)

    def record(self, key: str, window: float = 300.0) -> int:
        """记录一次事件，返回窗口内该 key 的总次数"""
        now = time.time()
        with self._lock:
            events = self._events[key]
            # 清理过期记录
            self._events[key] = [t for t in events if now - t < window]
            self._events[key].append(now)
            return len(self._events[key])

    def count(self, key: str, window: float = 300.0) -> int:
        """查询窗口内该 key 的次数"""
        now = time.time()
        with self._lock:
            events = self._events[key]
            return sum(1 for t in events if now - t < window)


# ═══════════════════════════════════════════════════════════════
# 安全规则定义
# ═══════════════════════════════════════════════════════════════

def _build_rules() -> list[_Rule]:
    """构建内置安全规则集"""
    rules = []

    # ── Critical: 系统破坏 ──
    rules.append(_Rule(
        rule_id="shell.dangerous_command",
        severity="Critical", category="shell",
        patterns=[
            r'\brm\s+-rf\b', r'\brm\s+-fr\b', r'\brm\s+--no-preserve-root\b',
            r'\bdel\s+/[sS]\b', r'\bformat\s+[A-Za-z]:', r'\bmkfs\b',
            r'\bdd\s+if=.*of=/dev/', r'\bshred\b', r'\btruncate\s+-s\s+0\b',
        ],
        reason="破坏性系统命令，可能导致数据不可恢复",
        safer_alternative="如需清理，请指定具体目录而非根目录",
    ))

    # ── Critical: 反弹Shell ──
    rules.append(_Rule(
        rule_id="shell.reverse_shell",
        severity="Critical", category="shell",
        patterns=[
            r'\bnc\s+.*-[el]\b', r'\bncat\b.*-[el]', r'\bbash\s+-i\b',
            r'/dev/tcp/', r'/dev/udp/', r'\bsocat\b.*EXEC:',
            r'\bpython[23]?\s+-c\s+.*socket\b', r'\bperl\s+-e\b.*socket\b',
            r'\bruby\s+-e\b.*socket\b', r'\bphp\s+-r\b.*fsockopen\b',
        ],
        reason="检测到反弹Shell攻击特征",
        safer_alternative="如需远程管理，请使用SSH等安全协议",
    ))

    # ── Critical: 提权 ──
    rules.append(_Rule(
        rule_id="shell.privilege_escalation",
        severity="Critical", category="shell",
        patterns=[
            r'\bsudo\s+su\b', r'\bsudo\s+-i\b', r'\bsudo\s+root\b',
            r'\bchmod\s+(777|666|4777)\b', r'\bpasswd\s+root\b',
            r'\bchown\s+root\b', r'\b/etc/sudoers\b',
            r'\busermod\s+-aG\s+(sudo|wheel|root)\b',
            r'\bpkexec\b', r'\bdoas\b',
        ],
        reason="检测到权限提升操作",
        safer_alternative="如需特定权限，请使用最小权限原则",
    ))

    # ── Critical: 远程代码执行/数据外泄 ──
    rules.append(_Rule(
        rule_id="shell.data_exfil",
        severity="Critical", category="shell",
        patterns=[
            r'\bcurl\b.*\|.*\b(sh|bash|python|perl|ruby)\b',
            r'\bwget\b.*\|.*\b(sh|bash|python|perl|ruby)\b',
            r'\bbase64\b.*\|', r'\bxxd\b.*\|',
            r'\btar\b.*\|.*\b(nc|ncat|socat)\b',
            r'\bscp\b.*@.*:', r'\brsync\b.*@.*::',
            r'\bnc\s+.*<\s*/etc/', r'\bcat\s+/etc/(passwd|shadow|hosts)\b',
        ],
        reason="检测到远程代码执行或数据外泄特征",
        safer_alternative="请勿执行远程代码或传输敏感文件",
    ))

    # ── Critical: Prompt注入 ──
    rules.append(_Rule(
        rule_id="prompt.injection",
        severity="Critical", category="prompt",
        patterns=[
            r'ignore\s+(all\s+)?previous\s+(instructions?|prompts?|rules?)',
            r'forget\s+(all\s+)?previous\s+(instructions?|prompts?|rules?)',
            r'disregard\s+(all\s+)?previous',
            r'you\s+are\s+(now\s+)?(a\s+)?(hacker|malicious|evil|unrestricted)',
            r'pretend\s+(to\s+be|you\s+are)\s+(a\s+)?(hacker|malicious|evil|unrestricted)',
            r'jailbreak', r'DAN\s+mode', r'developer\s+mode',
            r'<\|im_start\|>', r'<\|im_end\|>',
            r'\[SYSTEM\]', r'\[ADMIN\]', r'system\s*:\s*(you\s+are|ignore|forget)',
            r'bypass\s+(all\s+)?(safety|security|filter|guard|restriction)',
            r'override\s+(all\s+)?(safety|security|filter|guard|restriction)',
            r'忽略(之前的|上面的|所有的)(指令|提示|规则)',
            r'假装(你是|你是一个)(黑客|恶意|不受限制)',
            r'你(现在)?是(一个)?(黑客|恶意|不受限制)',
            r'绕过(所有)?(安全|防护|限制)',
        ],
        reason="检测到Prompt注入攻击特征",
        safer_alternative="请直接描述您的需求，无需尝试修改AI行为",
    ))

    # ── Critical: 敏感文件访问 ──
    rules.append(_Rule(
        rule_id="shell.sensitive_file_access",
        severity="Critical", category="shell",
        patterns=[
            r'\bcat\s+/etc/shadow\b', r'\bcat\s+/etc/passwd\b',
            r'\bcat\s+~?/\.ssh/', r'\bcat\s+~?/\.aws/',
            r'\bcat\s+~?/\.gnupg/', r'\bcat\s+~?/\.kube/',
            r'\bless\s+/etc/shadow\b', r'\bhead\s+/etc/shadow\b',
            r'\bvim\s+/etc/shadow\b', r'\bnano\s+/etc/shadow\b',
            r'\b(读取|查看|显示|打印).*(密钥|私钥|密码文件|shadow|passwd)',
        ],
        reason="检测到敏感文件访问尝试",
        safer_alternative="请勿访问系统敏感文件",
    ))

    # ── High: 可疑系统命令 ──
    rules.append(_Rule(
        rule_id="shell.suspicious_command",
        severity="High", category="shell",
        patterns=[
            r'\bshutdown\b', r'\breboot\b', r'\binit\s+[06]\b',
            r'\bkill\s+-9\b', r'\bkillall\b', r'\bpkill\s+-9\b',
            r'\bsystemctl\s+(stop|disable)\b', r'\bservice\s+\w+\s+stop\b',
            r'\bhalt\b', r'\bpoweroff\b',
        ],
        reason="检测到系统控制命令，可能影响系统稳定性",
        safer_alternative="如需重启服务，请使用 systemctl restart",
    ))

    # ── High: 网络扫描 ──
    rules.append(_Rule(
        rule_id="network.scan",
        severity="High", category="network",
        patterns=[
            r'\bnmap\b', r'\bmasscan\b', r'\bzmap\b',
            r'\bping\s+-[fs]', r'\bport\s+scan\b',
            r'\bnetdiscover\b', r'\barp-scan\b',
            r'\b(端口|网络)(扫描|探测)',
        ],
        reason="检测到网络扫描行为",
        safer_alternative="请勿扫描网络，如需检查设备状态请使用 /api/check",
    ))

    # ── High: 防火墙/安全控制禁用 ──
    rules.append(_Rule(
        rule_id="shell.disable_security",
        severity="High", category="shell",
        patterns=[
            r'\biptables\s+-F\b', r'\bufw\s+disable\b',
            r'\bsetenforce\s+0\b', r'\bfirewall-cmd\s+--disable\b',
            r'\bnetsh\s+advfirewall\s+set\s+off\b',
            r'\bselinux\s+disabled\b',
        ],
        reason="检测到禁用安全控制的操作",
        safer_alternative="请勿禁用防火墙或安全策略",
    ))

    # ── High: 数据库破坏 ──
    rules.append(_Rule(
        rule_id="sql.destructive",
        severity="High", category="shell",
        patterns=[
            r'\bDROP\s+DATABASE\b', r'\bDROP\s+TABLE\b',
            r'\bTRUNCATE\s+TABLE\b', r'\bDELETE\s+FROM\s+\w+\s*;',
            r'\bDROP\s+SCHEMA\b',
        ],
        reason="检测到破坏性数据库操作",
        safer_alternative="如需删除数据，请先备份再操作",
    ))

    # ── Medium: 敏感信息查询 ──
    rules.append(_Rule(
        rule_id="ai.sensitive_query",
        severity="Medium", category="prompt",
        patterns=[
            r'(API|api)[_-]?(key|secret|token)',
            r'(密码|口令|密钥|私钥).*(查看|显示|告诉我|输出|打印)',
            r'(password|secret|token|credential).*(show|display|tell|print|reveal)',
            r'\b(AWS|aws)_(SECRET|ACCESS)_KEY\b',
            r'\bGH_TOKEN\b', r'\bGITHUB_TOKEN\b',
        ],
        reason="检测到敏感信息查询请求",
        safer_alternative="请勿查询或泄露敏感凭证信息",
    ))

    # ── Medium: Windows 危险命令 ──
    rules.append(_Rule(
        rule_id="shell.windows_dangerous",
        severity="Medium", category="shell",
        patterns=[
            r'\bpowershell\b.*-enc\b', r'\bpowershell\b.*-ExecutionPolicy\s+Bypass\b',
            r'\bcmd\.exe\b.*/c\b.*\b(del|format|rd)\b',
            r'\breg\s+(delete|add)\s+HKLM\b',
            r'\bnet\s+user\b.*/add\b', r'\bnet\s+localgroup\b.*administrators\b.*/add\b',
        ],
        reason="检测到Windows危险命令",
        safer_alternative="请勿执行Windows系统破坏命令",
    ))

    return rules


# ═══════════════════════════════════════════════════════════════
# 安全护栏主类
# ═══════════════════════════════════════════════════════════════

class SafetyShield:
    """智慧家居安全护栏"""

    # 严重度等级映射
    SEVERITY_RANK = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}
    BLOCK_THRESHOLD = 3  # High 及以上拦截

    # 频率限制配置
    RATE_LIMITS = {
        "device_toggle": {"window": 10, "max": 3},   # 10秒内同一设备最多3次
        "door_open":     {"window": 300, "max": 3},   # 5分钟内开门最多3次
        "alarm_trigger": {"window": 300, "max": 3},   # 5分钟内警报最多3次
    }

    def __init__(self):
        self.rules = _build_rules()
        self._rate = _RateTracker()
        self._lock = threading.Lock()

    def check(self, text: str, context: str = "chat") -> ShieldResult:
        """
        检查文本是否命中安全规则

        Args:
            text: 用户输入文本
            context: 上下文 (chat / voice / api / ws_chat)

        Returns:
            ShieldResult: 检查结果
        """
        if not text or not text.strip():
            return ShieldResult(blocked=False)

        text = text.strip()

        # 1. 正则规则匹配
        best_result = ShieldResult(blocked=False)
        best_rank = 0

        for rule in self.rules:
            # 上下文过滤
            if rule.context_filter and context not in rule.context_filter:
                continue

            for compiled, raw_pattern in zip(rule._compiled, rule.patterns):
                m = compiled.search(text)
                if m:
                    rank = self.SEVERITY_RANK.get(rule.severity, 0)
                    if rank > best_rank:
                        best_rank = rank
                        matched = m.group(0)
                        # 截断过长的匹配
                        if len(matched) > 100:
                            matched = matched[:100] + "..."
                        best_result = ShieldResult(
                            blocked=rank >= self.BLOCK_THRESHOLD,
                            rule_id=rule.rule_id,
                            severity=rule.severity,
                            category=rule.category,
                            reason=rule.reason,
                            matched_text=matched,
                            safer_alternative=rule.safer_alternative,
                        )
                    break  # 一条规则只匹配一次

        return best_result

    def check_device_rate(self, device_id: str, action: str) -> ShieldResult:
        """
        检查设备操作频率限制

        Args:
            device_id: 设备ID
            action: 操作类型 (toggle / door_open / alarm_trigger)

        Returns:
            ShieldResult: 频率超限结果
        """
        limit_key = f"device:{device_id}:{action}"
        config = self.RATE_LIMITS.get(action)
        if not config:
            return ShieldResult(blocked=False)

        count = self._rate.record(limit_key, config["window"])
        if count > config["max"]:
            return ShieldResult(
                blocked=True,
                rule_id=f"device.rate_limit.{action}",
                severity="High",
                category="device",
                reason=f"设备操作频率超限: {config['window']}秒内已操作{count}次，上限{config['max']}次",
                matched_text=f"{device_id} x{count}",
                safer_alternative="请稍后再试，避免频繁操作损坏设备",
            )

        return ShieldResult(blocked=False)

    def check_door_rate(self) -> ShieldResult:
        """检查门禁开启频率"""
        count = self._rate.record("door:open", 300)
        if count > 3:
            return ShieldResult(
                blocked=True,
                rule_id="door.force_open",
                severity="Critical",
                category="device",
                reason=f"门禁暴力开启: 5分钟内已尝试{count}次，上限3次",
                matched_text=f"开门 x{count}",
                safer_alternative="门禁频繁开启可能存在安全隐患，请确认身份",
            )
        return ShieldResult(blocked=False)

    def check_alarm_rate(self) -> ShieldResult:
        """检查警报触发频率"""
        count = self._rate.record("alarm:trigger", 300)
        if count > 3:
            return ShieldResult(
                blocked=True,
                rule_id="alarm.false_trigger",
                severity="Critical",
                category="device",
                reason=f"警报滥用: 5分钟内已触发{count}次，上限3次",
                matched_text=f"蜂鸣器 x{count}",
                safer_alternative="频繁触发警报可能影响他人，请谨慎使用",
            )
        return ShieldResult(blocked=False)

    def get_stats(self) -> dict:
        """获取安全护栏统计信息"""
        return {
            "total_rules": len(self.rules),
            "critical_rules": sum(1 for r in self.rules if r.severity == "Critical"),
            "high_rules": sum(1 for r in self.rules if r.severity == "High"),
            "medium_rules": sum(1 for r in self.rules if r.severity == "Medium"),
            "categories": list(set(r.category for r in self.rules)),
            "rate_limits": {k: v for k, v in self.RATE_LIMITS.items()},
        }


# ═══════════════════════════════════════════════════════════════
# 全局实例
# ═══════════════════════════════════════════════════════════════

shield = SafetyShield()
