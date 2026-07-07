"""记忆片段模型 - 含 pgvector 向量字段

存储角色的所有经历片段，是记忆系统的核心数据。
向量字段用于语义检索，importance + timestamp 用于混合排序。
"""
from datetime import datetime
from uuid import UUID
from uuid6 import uuid7

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from src.config import settings
from src.db.base import Base


class MemoryEpisode(Base):
    """记忆片段表 - 含 HNSW 向量索引

    设计要点：
    - embedding: pgvector Vector(1536)，HNSW 索引加速
    - importance: 重要性评分（1-10），影响检索排序权重
    - is_reflected: 是否已被反思消化，部分索引优化未反思查询
    - source_type: 来源类型（action/conversation/reflection）

    检索策略（混合排序）：
        final_score = sim_score * 0.6 + importance * 0.05 + time_decay
    详见 architecture.md §5.7
    """
    __tablename__ = "memory_episodes"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid7, comment="记忆 ID"
    )
    character_id: Mapped[UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), comment="所属角色"
    )
    content: Mapped[str] = mapped_column(Text, comment="记忆内容（自然语言）")
    embedding: Mapped[list[float]] = mapped_column(
        Vector(settings.embedding_dim), comment="向量嵌入"
    )
    importance: Mapped[int] = mapped_column(
        Integer, default=5, comment="重要性 1-10"
    )
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, server_default="now()", comment="发生时间"
    )
    action_id: Mapped[str | None] = mapped_column(String(100), comment="关联 Action")
    location: Mapped[str | None] = mapped_column(String(50), comment="发生场景")
    related_characters: Mapped[list] = mapped_column(
        JSONB, default=list, comment="相关角色 ID 列表"
    )
    is_reflected: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否已被反思消化"
    )
    source_type: Mapped[str] = mapped_column(
        String(20), default="action", comment="来源类型"
    )

    __table_args__ = (
        # 角色记忆时间线查询
        Index("idx_mem_char_time", "character_id", "timestamp"),
        # 部分索引：仅索引未反思的记忆，加速反思触发检查
        Index(
            "idx_mem_unreflected",
            "character_id",
            postgresql_where="is_reflected = FALSE",
        ),
    )