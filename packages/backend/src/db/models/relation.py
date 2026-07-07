"""角色关系模型 - 有向图

记录角色对其他角色的认知，是社交 Action 的依据。
双向关系需两条记录（A→B 和 B→A）。
"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class Relation(Base):
    """关系表 - 有向图

    relationship_type:
    - stranger: 陌生人（strength < 20）
    - acquaintance: 熟人（20-40）
    - friend: 朋友（40-70）
    - close_friend: 密友（70-90）
    - best_friend: 挚友（90+）

    strength: 0-100，关系强度
    last_interaction_at: 最后互动时间（用于衰减计算）
    notes: LLM 总结的对该角色的认知
    """
    __tablename__ = "relations"

    character_id: Mapped[UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True
    )
    target_id: Mapped[UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True
    )
    strength: Mapped[int] = mapped_column(Integer, default=20, comment="关系强度 0-100")
    relationship_type: Mapped[str] = mapped_column(
        String(30), default="stranger", comment="关系类型"
    )
    last_interaction_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMPTZ, comment="最后互动时间"
    )
    notes: Mapped[str | None] = mapped_column(Text, comment="对该角色的认知笔记")