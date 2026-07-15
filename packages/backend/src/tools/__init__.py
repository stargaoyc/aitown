"""工具模块 - 替代 MCP Server 的进程内直接工具调用

将原 MCP Server（shop-simulator/knowledge-base/character-social）的工具收编为
本地 async 函数，新增 world/self_info 只读查询工具，消除 HTTP/SSE 网络开销。

模块组织：
- shop.py: 商店购买/出售/查询（5 个工具）
- knowledge.py: 小镇设定库检索（2 个工具）
- social.py: 角色社交（送礼/约会/冲突解决，3 个工具）
- world.py: 世界状态/角色查找/场景信息（4 个只读工具）
- self_info.py: 关系/记忆查询（2 个只读工具）
- registry.py: ToolRegistry 注册表（替代 MCPClient）

使用方式：
    from src.tools import ToolRegistry
    registry = ToolRegistry()
    tools_text = await registry.format_tools_for_prompt()
    result = await registry.call_tool_with_context("shop.buy_item", args, context)
"""

from src.tools.registry import (
    TOOL_REGISTRY,
    TOOLS_ENABLED_KEY,
    ToolRegistry,
    get_enabled_tools,
    get_tool_metadata,
    is_tool_enabled,
    list_all_tool_names,
)

__all__ = [
    "TOOLS_ENABLED_KEY",
    "TOOL_REGISTRY",
    "ToolRegistry",
    "get_enabled_tools",
    "get_tool_metadata",
    "is_tool_enabled",
    "list_all_tool_names",
]
