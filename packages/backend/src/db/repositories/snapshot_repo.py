"""世界事件 Repository - 差分事件持久化与回放

⚠️ 0002_optimize 迁移后，world_snapshots 表已删除。
世界状态通过 world_events 差分事件表持久化，回放时从事件流重建。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from src.db.models import WorldEvent
from src.db.repositories.base import BaseRepository

logger = get_logger()


class WorldEventRepository(BaseRepository[WorldEvent]):
    """世界事件 Repository

    用法：
        async with db.session() as session:
            repo = WorldEventRepository(session)
            await repo.add(event)
    """

    def __init__(self, session: AsyncSession):
        super().__init__(session, WorldEvent)

    async def add(self, event: WorldEvent) -> WorldEvent:
        """写入一条世界事件"""
        self.session.add(event)
        await self.session.flush()
        logger.info(
            "world_event_created",
            tick_id=event.tick_id,
            event_type=event.event_type,
        )
        return event

    async def add_batch(self, events: list[WorldEvent]) -> None:
        """批量写入世界事件"""
        if not events:
            return
        self.session.add_all(events)
        await self.session.flush()
        logger.info(
            "world_events_batch_created",
            count=len(events),
            tick_id=events[0].tick_id if events else None,
        )

    async def get_by_tick(self, tick_id: int) -> list[WorldEvent]:
        """按 Tick 序号获取该 Tick 的所有事件"""
        stmt = (
            select(WorldEvent)
            .where(WorldEvent.tick_id == tick_id)
            .order_by(WorldEvent.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def get_by_type(
        self, event_type: str, limit: int = 100
    ) -> list[WorldEvent]:
        """按事件类型查询最近的事件"""
        stmt = (
            select(WorldEvent)
            .where(WorldEvent.event_type == event_type)
            .order_by(WorldEvent.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def get_range(
        self, start_tick: int, end_tick: int
    ) -> list[WorldEvent]:
        """查询 Tick 区间内的所有事件（用于回放）"""
        stmt = (
            select(WorldEvent)
            .where(
                WorldEvent.tick_id >= start_tick,
                WorldEvent.tick_id <= end_tick,
            )
            .order_by(WorldEvent.tick_id, WorldEvent.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars())
