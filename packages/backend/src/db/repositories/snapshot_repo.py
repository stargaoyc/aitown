"""世界快照 Repository - 世界状态持久化与回放

定期持久化世界状态，支持回滚到任意时间点（按 tick_id 索引）。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from src.db.models import WorldSnapshot
from src.db.repositories.base import BaseRepository

logger = get_logger()


class SnapshotRepository(BaseRepository[WorldSnapshot]):
    """世界快照 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, WorldSnapshot)

    async def add(self, snapshot: WorldSnapshot) -> WorldSnapshot:
        """写入一帧世界快照"""
        self.session.add(snapshot)
        await self.session.flush()
        logger.info(
            "snapshot_created", tick_id=snapshot.tick_id
        )
        return snapshot

    async def get_latest(self) -> WorldSnapshot | None:
        """获取最新一帧快照（按 tick_id 倒序取首条）"""
        stmt = (
            select(WorldSnapshot)
            .order_by(WorldSnapshot.tick_id.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_tick(self, tick_id: int) -> WorldSnapshot | None:
        """按 Tick 序号获取快照（tick_id 非主键，走 idx_world_tick 索引）"""
        stmt = select(WorldSnapshot).where(WorldSnapshot.tick_id == tick_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
