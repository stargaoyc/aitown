"""反思来源中间表 - 替代 reflections.source_memory_ids UUID[]

解决 UUID[] 数组无法建立外键约束的问题，
通过中间表保证引用完整性。
"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Index
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class ReflectionSource(Base):
    """反思来源关联表

    一条反思由多条记忆归纳而来，此表记录关联关系。
    删除记忆时，CASCADE 会自动清理关联（需应用层先查再删）。
    """
    __tablename__ = "reflection_sources"

    reflection_id: Mapped[UUID] = mapped_column(
        ForeignKey("reflections.id", ondelete="CASCADE"),
        primary_key=True, comment="反思 ID"
    )
    memory_id: Mapped[UUID] = mapped_column(
        primary_key=True,
        comment="memory_episodes.id（应用层保证存在）"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default="now()", comment="创建时间"
    )

    __table_args__ = (
        # 按 memory_id 反查：哪些反思引用了此记忆
        Index("idx_refl_sources_memory", "memory_id"),
    )
