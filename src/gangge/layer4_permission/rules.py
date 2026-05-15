"""Permission rules — user-configurable allow/deny patterns."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class RuleAction(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass
class PermissionRule:
    """A single permission rule."""

    action: RuleAction
    pattern: str
    description: str = ""
    scope: str = "bash"  # "bash" | "file_read" | "file_write" | "network"

    def matches(self, target: str) -> bool:
        try:
            return bool(re.search(self.pattern, target, re.IGNORECASE))
        except re.error:
            return False


# Default rules
DEFAULT_RULES: list[PermissionRule] = [
    # Auto-allow safe read operations
    PermissionRule(RuleAction.ALLOW, r"^cat\s", "cat 读取文件", "bash"),
    PermissionRule(RuleAction.ALLOW, r"^ls\b", "列出目录", "bash"),
    PermissionRule(RuleAction.ALLOW, r"^pwd$", "显示当前目录", "bash"),
    PermissionRule(RuleAction.ALLOW, r"^echo\b", "echo 输出", "bash"),
    PermissionRule(RuleAction.ALLOW, r"^git\s+(status|log|branch|diff|show)", "Git 只读命令", "bash"),
    PermissionRule(RuleAction.ALLOW, r"^(python|python3)\s+.*--version", "查看 Python 版本", "bash"),
    PermissionRule(RuleAction.ALLOW, r"^which\b", "查找命令位置", "bash"),
    PermissionRule(RuleAction.ALLOW, r"^(npm|pip)\s+list", "列出已安装包", "bash"),

    # Auto-deny dangerous operations
    PermissionRule(RuleAction.DENY, r"\brm\s+(-[rfRF]+\s+)?/", "禁止删除根目录", "bash"),
    PermissionRule(RuleAction.DENY, r":\s*\(\)\s*\{", "禁止 Fork 炸弹", "bash"),

    # Everything else requires asking
    PermissionRule(RuleAction.ASK, r".*", "其他命令需要确认", "bash"),
]
