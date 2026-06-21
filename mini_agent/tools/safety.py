"""
工具安全审批模块

三层审批机制：
- 白名单：只读操作，自动放行
- 灰名单：有副作用操作，需用户确认
- 黑名单：危险命令，直接阻断
"""

import re
from typing import Any, Dict, Optional

# 白名单：自动放行
WHITELIST = {
    "read_file",
    "recall_notes",
    "bash_output",
    "bash_kill",
    "get_skill",
}

# 灰名单：需用户确认
GREYLIST = {
    "write_file",
    "edit_file",
    "record_note",
    "bash",
}

# 黑名单：危险命令关键词（bash 命令级别）
BLACKLIST_PATTERNS = [
    r"rm\s+-rf",
    r"rm\s+-fr",
    r"del\s+/f",
    r"del\s+/s",
    r"rmdir\s+/s",
    r"rd\s+/s",
    r"format\s+[a-zA-Z]:",
    r"mkfs\.",
    r"dd\s+if=",
    r":(\(\)\{:|:&\};\:)",
]


def _is_blacklisted_command(command: str) -> Optional[str]:
    """检查 bash 命令是否包含黑名单关键词"""
    for pattern in BLACKLIST_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return pattern
    return None


def _format_args(tool_name: str, arguments: Dict[str, Any]) -> str:
    """格式化工具参数用于显示"""
    if tool_name == "bash":
        return f"命令: {arguments.get('command', '')}"
    elif tool_name == "write_file":
        return f"路径: {arguments.get('path', '')}"
    elif tool_name == "edit_file":
        return f"路径: {arguments.get('path', '')}"
    elif tool_name == "record_note":
        return f"内容: {arguments.get('content', '')[:50]}"
    return str(arguments)[:100]


class SafetyGuard:
    """工具安全审批守卫"""

    def __init__(self, auto_approve: bool = False):
        """
        Args:
            auto_approve: 是否自动批准所有操作（测试用）
        """
        self.auto_approve = auto_approve
        self.approved_count = 0
        self.blocked_count = 0
        self.auto_count = 0

    def check(self, tool_name: str, arguments: Dict[str, Any]) -> tuple[bool, str]:
        """
        检查工具调用是否允许执行

        Returns:
            (allowed, reason)
            allowed: True 允许执行，False 阻断
            reason: 说明
        """
        # 1. 白名单：直接放行
        if tool_name in WHITELIST:
            self.auto_count += 1
            return True, "whitelist"

        # 2. 黑名单检测（bash 命令级别）
        if tool_name == "bash":
            command = arguments.get("command", "")
            matched = _is_blacklisted_command(command)
            if matched:
                self.blocked_count += 1
                reason = f"危险命令被阻断: 匹配黑名单规则 `{matched}`"
                print(f"\n🚫 \033[91m{reason}\033[0m")
                return False, reason

        # 3. 灰名单：需用户确认
        if tool_name in GREYLIST:
            if self.auto_approve:
                self.approved_count += 1
                return True, "auto_approve"

            args_display = _format_args(tool_name, arguments)
            print(f"\n⚠️  \033[93mAgent 请求执行: \033[1m{tool_name}\033[0m")
            print(f"   \033[93m{args_display}\033[0m")
            try:
                answer = input("   是否允许？(y/n，直接回车默认允许): ").strip().lower()
            except EOFError:
                answer = "y"

            if answer in ("", "y", "yes"):
                self.approved_count += 1
                print(f"   \033[92m✓ 已允许\033[0m")
                return True, "user_approved"
            else:
                self.blocked_count += 1
                print(f"   \033[91m✗ 已拒绝\033[0m")
                return False, "user_rejected"

        # 4. MCP 动态工具默认灰名单处理
        if self.auto_approve:
            return True, "auto_approve"

        args_display = str(arguments)[:100]
        print(f"\n⚠️  \033[93mAgent 请求执行未知工具: \033[1m{tool_name}\033[0m")
        print(f"   \033[93m{args_display}\033[0m")
        try:
            answer = input("   是否允许？(y/n，直接回车默认允许): ").strip().lower()
        except EOFError:
            answer = "y"

        if answer in ("", "y", "yes"):
            self.approved_count += 1
            return True, "user_approved"
        else:
            self.blocked_count += 1
            return False, "user_rejected"

    def stats(self) -> str:
        total = self.auto_count + self.approved_count + self.blocked_count
        return (f"工具审批统计: 总调用={total}, "
                f"自动放行={self.auto_count}, "
                f"用户批准={self.approved_count}, "
                f"已阻断={self.blocked_count}")