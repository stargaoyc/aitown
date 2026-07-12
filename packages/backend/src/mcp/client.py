"""MCP 客户端 - 角色调用 MCP 工具的桥梁

功能：
- 列出所有可用工具及其描述
- 通过 HTTP/SSE 调用 MCP Server 的工具
- 工具结果返回给角色 Tick 引擎，注入记忆

使用方式：
    client = MCPClient()
    tools = await client.list_tools()
    result = await client.call_tool("weather", "get_current_weather", {"city": "东京"})
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from structlog import get_logger

logger = get_logger(__name__)


# MCP Server 配置（与 main.py 中的 _MCP_SERVERS_CONFIG 保持一致）
MCP_SERVERS: list[dict[str, Any]] = [
    {
        "name": "web-search",
        "env_key": "MCP_SEARCH_SERVER",
        "default_port": 8002,
        "tools": {
            "search": {"desc": "网络搜索（获取实时信息、新闻、知识）", "params": {"query": "搜索关键词"}},
            "search_news": {"desc": "搜索最新新闻", "params": {"query": "新闻关键词", "max_results": 5}},
        },
    },
    {
        "name": "weather",
        "env_key": "MCP_WEATHER_SERVER",
        "default_port": 8003,
        "tools": {
            "get_current_weather": {"desc": "查询当前天气", "params": {"city": "城市名"}},
            "get_forecast": {"desc": "查询天气预报", "params": {"city": "城市名", "days": 3}},
        },
    },
    {
        "name": "shop-simulator",
        "env_key": "MCP_SHOP_SERVER",
        "default_port": 8004,
        "tools": {
            "list_items": {"desc": "查看商店商品列表", "params": {"category": "商品类别（可选）"}},
            "get_item_details": {"desc": "查看商品详情", "params": {"item_id": "商品ID"}},
            "buy_item": {"desc": "购买商品", "params": {"item_id": "商品ID", "quantity": 1}},
        },
    },
    {
        "name": "knowledge-base",
        "env_key": "MCP_KB_SERVER",
        "default_port": 8005,
        "tools": {
            "query_kb": {"desc": "查询小镇设定库（世界规则、角色关系、场景信息）", "params": {"question": "查询问题"}},
        },
    },
    {
        "name": "character-social",
        "env_key": "MCP_SOCIAL_SERVER",
        "default_port": 8006,
        "tools": {
            "give_gift": {"desc": "给其他角色送礼", "params": {"target": "目标角色", "item": "礼物名称"}},
            "invite_date": {"desc": "邀请其他角色约会", "params": {"target": "目标角色", "location": "地点"}},
        },
    },
]


class MCPClient:
    """MCP 工具客户端

    通过 HTTP 调用 MCP Server 的工具接口。
    如果 Server 离线，返回错误信息但不中断 Tick 流程。
    """

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    def get_server_endpoint(self, server_name: str) -> str | None:
        """获取 MCP Server 的 HTTP 端点"""
        for cfg in MCP_SERVERS:
            if cfg["name"] == server_name:
                return os.environ.get(
                    cfg["env_key"],
                    f"http://localhost:{cfg['default_port']}",
                )
        return None

    def list_tools(self) -> list[dict[str, Any]]:
        """列出所有可用工具（静态配置，不依赖 Server 在线）"""
        tools = []
        for cfg in MCP_SERVERS:
            for tool_name, tool_info in cfg["tools"].items():
                tools.append({
                    "server": cfg["name"],
                    "tool": tool_name,
                    "description": tool_info["desc"],
                    "params": tool_info["params"],
                    "full_name": f"{cfg['name']}.{tool_name}",
                })
        return tools

    def format_tools_for_prompt(self) -> str:
        """格式化工具列表供 LLM Prompt 使用"""
        lines = []
        for t in self.list_tools():
            params_str = ", ".join(f'{k}: {v}' for k, v in t["params"].items())
            lines.append(f"- {t['full_name']}({params_str}): {t['description']}")
        return "\n".join(lines)

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """调用 MCP Server 的工具

        Args:
            server_name: 服务器名称（如 "weather"）
            tool_name: 工具名称（如 "get_current_weather"）
            args: 工具参数

        Returns:
            {"success": bool, "result": ..., "error": ...}
        """
        args = args or {}
        endpoint = self.get_server_endpoint(server_name)
        if not endpoint:
            return {"success": False, "error": f"Unknown server: {server_name}", "result": None}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # 尝试通过 MCP JSON-RPC 协议调用
                # FastMCP 2.0+ SSE 端点
                resp = await client.post(
                    f"{endpoint}/messages/",
                    json={
                        "method": "tools/call",
                        "params": {
                            "name": tool_name,
                            "arguments": args,
                        },
                    },
                )
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        return {"success": True, "result": data, "error": None}
                    except Exception:
                        return {"success": True, "result": resp.text, "error": None}
                else:
                    return {
                        "success": False,
                        "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
                        "result": None,
                    }
        except httpx.ConnectError:
            return {
                "success": False,
                "error": f"MCP Server '{server_name}' is not running at {endpoint}",
                "result": None,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "result": None}

    async def call_tool_by_full_name(
        self,
        full_name: str,
        args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """通过全名调用工具（如 "weather.get_current_weather"）"""
        parts = full_name.split(".", 1)
        if len(parts) != 2:
            return {"success": False, "error": f"Invalid tool name: {full_name}", "result": None}
        return await self.call_tool(parts[0], parts[1], args)
