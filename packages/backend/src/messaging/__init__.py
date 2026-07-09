"""消息服务模块 - 用户与角色的对话管理

模块包含：
- MessageService: 消息处理核心服务（用户消息接收、LLM 回复生成、上下文压缩）
- WebSocketManager: Web 客户端 WebSocket 连接管理（单例）
- ProactiveSharingService: 角色主动分享链路（意图评估 + 文案生成 + 推送）
"""
from src.messaging.proactive_sharing import ProactiveSharingService
from src.messaging.service import MessageService
from src.messaging.websocket import WebSocketManager

__all__ = [
    "MessageService",
    "WebSocketManager",
    "ProactiveSharingService",
]
