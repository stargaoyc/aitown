"""API Key 管理 - 内存存储（Phase 4 再持久化）

职责：
1. 生成 `sk-` 前缀的随机 API Key
2. 验证 API Key 有效性
3. 撤销 API Key

设计要点：
- 内存存储（dict），进程重启后丢失，Phase 4 迁移至数据库
- 单进程 asyncio 模型下无需加锁
- 单例模式：模块级 manager 实例供全局使用
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from structlog import get_logger

logger = get_logger(__name__)

# API Key 前缀
_API_KEY_PREFIX = "sk-"


class APIKeyManager:
    """API Key 管理器 - 内存单例"""

    def __init__(self) -> None:
        self._keys: dict[str, dict[str, Any]] = {}

    def generate_key(self, user_id: str, scopes: list[str] | None = None) -> str:
        """生成新的 API Key

        Args:
            user_id: 关联的用户标识
            scopes: 权限范围列表（可选）

        Returns:
            `sk-` 前缀的 API Key 字符串
        """
        # 生成 32 字节随机串（urlsafe 编码约 43 字符）
        random_part = secrets.token_urlsafe(32)
        key = f"{_API_KEY_PREFIX}{random_part}"

        self._keys[key] = {
            "user_id": user_id,
            "scopes": scopes or [],
            "created_at": datetime.now(timezone.utc),
        }
        logger.info("api_key_generated", user_id=user_id, scopes=scopes)
        return key

    def validate_key(self, key: str) -> dict[str, Any] | None:
        """验证 API Key

        Args:
            key: API Key 字符串

        Returns:
            key 关联的 info dict（含 user_id/scopes/created_at），无效返回 None
        """
        info = self._keys.get(key)
        if info is None:
            return None
        # 返回副本，避免外部修改内部状态
        return dict(info)

    def revoke_key(self, key: str) -> bool:
        """撤销 API Key

        Args:
            key: API Key 字符串

        Returns:
            是否成功撤销（key 不存在返回 False）
        """
        if key not in self._keys:
            return False
        del self._keys[key]
        logger.info("api_key_revoked", key_prefix=key[:8])
        return True


# 模块级单例
api_key_manager = APIKeyManager()
