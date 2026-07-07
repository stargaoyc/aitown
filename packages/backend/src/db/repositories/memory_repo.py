"""记忆 Repository - ORM + 原生 SQL 混合策略

设计要点：
- 常规增删改查使用 SQLAlchemy 2.0 ORM（保持类型安全与可组合性）
- 向量混合检索使用原生 SQL（text()），充分利用 pgvector HNSW 索引与
  重要性/时间衰减的混合排序能力，这是 ORM 难以表达的关键路径

混合排序公式：
    final_score = sim_score * 0.6 + importance * 0.05 - time_decay
详见 architecture.md §5.7
"""
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from src.db.models import MemoryEpisode
from src.db.repositories.base import BaseRepository

logger = get_logger()


class MemoryRepository(BaseRepository[MemoryEpisode]):
    """记忆 Repository - ORM + 原生 SQL 混合策略"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, MemoryEpisode)

    async def add(self, episode: MemoryEpisode) -> MemoryEpisode:
        """添加记忆（ORM）"""
        self.session.add(episode)
        await self.session.flush()
        return episode

    async def recent(
        self, character_id: UUID, limit: int = 50
    ) -> list[MemoryEpisode]:
        """获取角色最近记忆（ORM，按时间倒序）"""
        stmt = (
            select(MemoryEpisode)
            .where(MemoryEpisode.character_id == character_id)
            .order_by(MemoryEpisode.timestamp.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def count_unreflected(self, character_id: UUID) -> int:
        """统计角色未反思记忆数（ORM，利用 idx_mem_unreflected 部分索引）"""
        stmt = (
            select(func.count())
            .select_from(MemoryEpisode)
            .where(
                MemoryEpisode.character_id == character_id,
                MemoryEpisode.is_reflected.is_(False),
            )
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def mark_reflected(self, episode_ids: list[UUID]) -> None:
        """将指定记忆批量标记为已反思（ORM 批量 UPDATE）"""
        if not episode_ids:
            return
        stmt = (
            update(MemoryEpisode)
            .where(MemoryEpisode.id.in_(episode_ids))
            .values(is_reflected=True)
        )
        await self.session.execute(stmt)
        await self.session.flush()
        logger.info(
            "memory_marked_reflected", count=len(episode_ids)
        )

    async def search_hybrid(
        self, character_id: UUID, query_vec: list[float], top_k: int = 10
    ) -> list[dict]:
        """混合检索（原生 SQL - HNSW + 重要性 + 时间衰减）

        执行流程：
        1. SET LOCAL hnsw.ef_search = 40 —— 提升 HNSW 召回质量（事务内生效）
        2. CTE candidates：先按向量距离召回 Top-K*2 候选，限定角色范围
        3. 计算 final_score = sim_score*0.6 + importance*0.05 + time_decay
           （time_decay = -距今天数*0.05，越久远扣分越多）
        4. 按 final_score 排序取 Top-K

        注意：SET LOCAL 必须与查询在同一事务内执行，故拆分为两次 execute。
        """
        # 1. 设置 HNSW 检索参数（事务内生效）
        await self.session.execute(text("SET LOCAL hnsw.ef_search = 40"))

        # 2. 向量召回 + 混合排序
        stmt = text(
            """
            WITH candidates AS (
                SELECT id, content, importance, timestamp,
                       1 - (embedding <=> :q_vec) AS sim_score
                FROM memory_episodes
                WHERE character_id = :cid
                ORDER BY embedding <=> :q_vec
                LIMIT :limit
            )
            SELECT id, content,
                   sim_score * 0.6 + importance * 0.05
                   - EXTRACT(EPOCH FROM (now() - timestamp)) / 86400.0 * 0.05 AS final_score
            FROM candidates
            ORDER BY final_score DESC
            LIMIT :top_k;
            """
        )
        result = await self.session.execute(
            stmt,
            {
                "cid": character_id,
                "q_vec": str(query_vec),
                "limit": top_k * 2,
                "top_k": top_k,
            },
        )
        rows = [dict(row._mapping) for row in result]
        logger.info(
            "memory_search_hybrid",
            character_id=str(character_id),
            top_k=top_k,
            returned=len(rows),
        )
        return rows
