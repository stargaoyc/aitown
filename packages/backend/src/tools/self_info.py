"""角色自省只读工具 - 查询自身关系与记忆

从 MCP Server 迁移为直接工具调用，供角色 LLM 进行自我信息检索。
所有函数仅执行读操作，不修改 Redis/PG 任何状态。

设计：
- 只读：不写入状态，无副作用，可被 LLM 安全调用
- 字符串入参：character_id 由 caller 传入字符串，内部转 UUID
- 错误显式返回：失败时返回 {"success": False, "error": str}，不抛异常给 caller

工具职责：
- get_relationships：查询角色的人际关系图（relations 表）
- search_memories：按关键词模糊匹配角色记忆（memory_episodes 表）
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import text

from src.db.repositories import RelationRepository
from src.db.session import db

logger = structlog.get_logger()


async def get_relationships(character_id: str) -> dict[str, Any]:
    """查询角色对所有其他角色的关系记录

    只读操作，从 PG relations 表读取角色的人际关系图。
    返回每条关系的 target_id、strength、relationship_type、notes。

    Args:
        character_id: 角色 ID（字符串形式 UUID）

    Returns:
        成功：{"success": True, "character_id": str, "relationships": [...], "total": int}
        失败：{"success": False, "error": str, "character_id": str}
    """
    # character_id 来自 LLM 外部输入，需校验 UUID 格式
    try:
        uuid = UUID(character_id)
    except ValueError as exc:
        logger.warning("get_relationships_invalid_uuid", character_id=character_id, error=str(exc))
        return {"success": False, "error": f"Invalid character_id: {exc}", "character_id": character_id}

    try:
        async with db.session() as session:
            repo = RelationRepository(session)
            relations = await repo.get_relations(uuid)
    except Exception as exc:
        logger.exception("get_relationships_failed", character_id=character_id)
        return {"success": False, "error": str(exc), "character_id": character_id}

    relationships = [
        {
            "target_id": str(rel.target_id),
            "strength": rel.strength,
            "relationship_type": rel.relationship_type,
            "notes": rel.notes,
        }
        for rel in relations
    ]

    logger.info(
        "get_relationships_ok",
        character_id=character_id,
        total=len(relationships),
    )

    return {
        "success": True,
        "character_id": character_id,
        "relationships": relationships,
        "total": len(relationships),
    }


async def search_memories(character_id: str, keyword: str, limit: int = 5) -> dict[str, Any]:
    """按关键词搜索角色记忆

    只读操作，对 memory_episodes.content 执行 ILIKE 模糊匹配。
    不使用向量检索（向量检索需要 embedding，由 MemoryRepository.search_hybrid 承担），
    这里提供轻量级文本匹配，供角色 LLM 快速回忆含特定关键词的经历。

    Args:
        character_id: 角色 ID（字符串形式 UUID）
        keyword: 搜索关键词
        limit: 返回数量上限，默认 5

    Returns:
        成功：{"success": True, "character_id": str, "keyword": str,
               "memories": [...], "total": int}
        失败：{"success": False, "error": str}
    """
    # character_id 来自 LLM 外部输入，需校验 UUID 格式
    try:
        uuid = UUID(character_id)
    except ValueError as exc:
        logger.warning("search_memories_invalid_uuid", character_id=character_id, error=str(exc))
        return {"success": False, "error": f"Invalid character_id: {exc}"}

    # ILIKE 模糊匹配：%keyword% 匹配任意位置出现的关键词
    pattern = f"%{keyword}%"

    # MemoryRepository 无文本搜索方法（仅有向量检索 search_hybrid），
    # 此处用原生 SQL ILIKE 查询。timestamp 列对应 MemoryEpisode.timestamp（发生时间）
    query = text(
        """
        SELECT id, content, importance, timestamp, source_type
        FROM memory_episodes
        WHERE character_id = :cid AND content ILIKE :kw
        ORDER BY timestamp DESC
        LIMIT :lim
        """
    )

    try:
        async with db.session() as session:
            result = await session.execute(query, {"cid": uuid, "kw": pattern, "lim": limit})
            rows = result.mappings().all()
    except Exception as exc:
        logger.exception("search_memories_failed", character_id=character_id, keyword=keyword)
        return {"success": False, "error": str(exc)}

    memories = [
        {
            "id": str(row["id"]),
            "content": row["content"],
            "importance": row["importance"],
            # 响应字段名为 created_at，对应 DB 列 timestamp
            "created_at": row["timestamp"].isoformat(),
            "source_type": row["source_type"],
        }
        for row in rows
    ]

    logger.info(
        "search_memories_ok",
        character_id=character_id,
        keyword=keyword,
        total=len(memories),
    )

    return {
        "success": True,
        "character_id": character_id,
        "keyword": keyword,
        "memories": memories,
        "total": len(memories),
    }
