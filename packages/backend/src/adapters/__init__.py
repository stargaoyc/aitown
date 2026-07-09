"""平台适配器模块 - 对接外部消息平台

模块包含：
- OneBotAdapter: QQ 机器人接入（OneBot v12 反向 WebSocket）
- LarkAdapter: 飞书接入（HTTP Webhook + Lark Open API）

两者均为骨架实现，需通过环境变量配置凭证与默认对话角色后可用：
- OneBot: ONEBOT_DEFAULT_CHARACTER_ID
- Lark:   LARK_APP_ID, LARK_APP_SECRET, LARK_DEFAULT_CHARACTER_ID
"""
from src.adapters.lark import LarkAdapter
from src.adapters.onebot import OneBotAdapter

__all__ = [
    "OneBotAdapter",
    "LarkAdapter",
]
