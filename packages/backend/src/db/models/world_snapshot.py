"""世界快照模型 - 用于世界回放与恢复

定期持久化世界状态，支持回滚到任意时间点。
"""
from datetime import datetime
from uuid import UUID
from uuid6 import uuid7

from sqlalchemy import BigInteger, Index, String
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class WorldSnapshot(Base):
    """世界快照表

    快照内容：
    - tick_id: 第几个 World Tick
    - world_time: 虚拟时间
    - weather: 天气
    - locations: 各场景状态与在场角色
    - resources: 资源状态
    - active_events: 活跃事件

    用途：调试回放、灾难恢复
    """
    __tablename__ = "world_snapshots"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    tick_id: Mapped[int] = mapped_column(BigInteger, comment="Tick 序号")
    world_time: Mapped[datetime] = mapped_column(comment="虚拟时间")
    weather: Mapped[str | None] = mapped_column(String(20), comment="天气")
    locations: Mapped[dict] = mapped_column(JSONB, comment="场景状态")
    resources: Mapped[dict] = mapped_column(JSONB, comment="资源状态")
    active_events: Mapped[list] = mapped_column(JSONB, default=list, comment="活跃事件")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default="now()", comment="创建时间"
    )

    __table_args__ = (Index("idx_world_tick", "tick_id"),)