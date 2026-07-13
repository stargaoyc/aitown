"""FastAPI 鉴权依赖 - JWT + API Key 双模式

职责：
1. 从请求头读取凭证（Authorization: Bearer 或 X-API-Key）
2. 优先校验 Bearer JWT，其次校验 API Key
3. 返回 user info dict 供路由使用
4. 无有效凭证统一抛 HTTPException(401, "Not authenticated")

API Key 校验来源：
1. settings.api_key（静态配置，可为 None）
2. APIKeyManager（动态生成的内存 Key）

使用方式：
    from fastapi import Depends
    from src.auth import auth_dependency

    @app.get("/protected")
    async def protected(user: dict = Depends(auth_dependency)):
        return {"user_id": user["user_id"]}
"""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import HTTPException, Request
from structlog import get_logger

from src.auth.api_keys import api_key_manager
from src.auth.jwt_handler import decode_token
from src.config import settings

logger = get_logger(__name__)

# 鉴权失败统一响应
_NOT_AUTHENTICATED = HTTPException(status_code=401, detail="Not authenticated")


async def auth_dependency(request: Request) -> dict[str, Any]:
    """FastAPI 鉴权依赖 - 支持 JWT 与 API Key 双模式

    校验顺序：
    1. Authorization: Bearer <jwt_token>
    2. X-API-Key: <api_key>

    Args:
        request: FastAPI Request 对象

    Returns:
        用户信息 dict: {"user_id": str, "auth_method": "jwt"|"api_key"}

    Raises:
        HTTPException: 401 当无有效凭证
    """
    # 1. 优先检查 Bearer JWT
    auth_header = request.headers.get("Authorization")
    if auth_header:
        parts = auth_header.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1].strip()
            if token:
                try:
                    payload = decode_token(token)
                    user_id = payload.get("sub") or ""
                    return {"user_id": str(user_id), "auth_method": "jwt"}
                except HTTPException:
                    # JWT 无效，降级尝试 API Key
                    pass

    # 2. 检查 X-API-Key
    api_key = request.headers.get("X-API-Key")
    if api_key:
        user_info = _validate_api_key(api_key)
        if user_info is not None:
            return {
                "user_id": str(user_info["user_id"]),
                "auth_method": "api_key",
            }

    # 无有效凭证
    logger.warning(
        "auth_failed",
        path=request.url.path,
        has_auth_header=auth_header is not None,
        has_api_key=api_key is not None,
    )
    raise _NOT_AUTHENTICATED


def _validate_api_key(key: str) -> dict[str, Any] | None:
    """校验 API Key - 同时检查静态配置与动态生成的 Key

    Args:
        key: API Key 字符串

    Returns:
        user info dict（含 user_id）或 None
    """
    # 1. 静态配置的 API Key（settings.api_key）
    # 使用 compare_digest 防止时序攻击
    if settings.api_key and secrets.compare_digest(key, settings.api_key):
        return {
            "user_id": "static",
            "scopes": [],
            "created_at": None,
        }

    # 2. 动态生成的 API Key（APIKeyManager）
    return api_key_manager.validate_key(key)


# auth_dependency 的别名
get_current_user = auth_dependency
