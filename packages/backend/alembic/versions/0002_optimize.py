"""数据库性能与完整性优化（v2）

基于生产环境审查反馈的系统性改进：

致命问题修复：
1. personality 迁移使用 COALESCE 防御 NULL（原代码 NULL || jsonb = NULL）
2. HNSW 索引在父表创建（自动传播所有子分区，避免运维噩梦）
3. 数据迁移锁警告（大表需用 pg_repack 或蓝绿迁移）

架构级修复：
4. 删除 DEFAULT 分区，改为 RAISE EXCEPTION 触发器（强制运维介入）
5. 删除 world_snapshots 表，仅保留 world_events 差分表
6. HASH 分区改为 16 个（2 的幂，扩展性更好）
7. 彻底删除 personality 列（不保留废弃列）

索引优化：
8. 覆盖索引移除 content 字段（避免索引膨胀）
9. character_states 增加 updated_at 自动更新触发器

Revision ID: 0002_optimize
Revises: 0001_init
Create Date: 2026-07-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002_optimize"
down_revision: Union[str, None] = "0001_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    ⚠️ 生产环境执行警告：

    1. memory_episodes 表重建涉及全表数据迁移，会持有 ACCESS EXCLUSIVE 锁。
       - 数据量 < 100 万行：可直接执行（预计 < 1 分钟）
       - 数据量 > 100 万行：必须使用 pg_repack 或蓝绿迁移
       - 执行前必须备份：pg_dump --table=memory_episodes

    2. 执行前确认无活跃的 Tick 循环（暂停 World Engine）。

    3. 建议在低峰期维护窗口执行，并设置锁超时：
       SET lock_wait_timeout = '30s';
    """

    # ============================================================
    # 改进 1+2+5+6: memory_episodes 重建为 HASH 分区（16 分区）
    # ============================================================
    # 问题：全局 HNSW + WHERE character_id = :cid 导致召回率崩塌
    # 方案：按 character_id HASH 分区（16 分区，2 的幂便于扩展）
    #       查询时分区裁剪直接命中单分区，HNSW 只搜索该角色数据
    #
    # 同时：
    # - 增加 materialized 标志区分原始日志与向量化记忆
    # - ef_construction 64→128 提升图精度
    # - HNSW 索引在父表创建，自动传播到所有子分区（含未来新增）

    op.execute("""
        -- 1. 重命名旧表
        ALTER TABLE memory_episodes RENAME TO memory_episodes_old;

        -- 2. 创建新的 HASH 分区表（16 分区，2 的幂）
        CREATE TABLE memory_episodes (
            id                 UUID NOT NULL DEFAULT uuidv7(),
            character_id       UUID NOT NULL,                       -- 分区键（无 FK，应用层保证）
            content            TEXT NOT NULL,
            embedding          vector(1536),                        -- nullable: materialized=false 时为 NULL
            importance         INT  NOT NULL DEFAULT 5 CHECK (importance BETWEEN 1 AND 10),
            timestamp          TIMESTAMPTZ NOT NULL DEFAULT now(),
            action_id          TEXT,
            location           TEXT,
            related_characters UUID[] NOT NULL DEFAULT '{}',
            is_reflected       BOOLEAN NOT NULL DEFAULT FALSE,
            materialized       BOOLEAN NOT NULL DEFAULT FALSE,      -- embedding 是否已生成
            source_type        TEXT NOT NULL DEFAULT 'action'
                               CHECK (source_type IN ('action','conversation','reflection','event')),
            PRIMARY KEY (id, character_id)                          -- 分区表主键必须含分区键
        ) PARTITION BY HASH (character_id);

        -- 3. 创建 16 个 HASH 分区（MODULUS 16）
        CREATE TABLE memory_episodes_p00 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 16, REMAINDER 0);
        CREATE TABLE memory_episodes_p01 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 16, REMAINDER 1);
        CREATE TABLE memory_episodes_p02 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 16, REMAINDER 2);
        CREATE TABLE memory_episodes_p03 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 16, REMAINDER 3);
        CREATE TABLE memory_episodes_p04 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 16, REMAINDER 4);
        CREATE TABLE memory_episodes_p05 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 16, REMAINDER 5);
        CREATE TABLE memory_episodes_p06 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 16, REMAINDER 6);
        CREATE TABLE memory_episodes_p07 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 16, REMAINDER 7);
        CREATE TABLE memory_episodes_p08 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 16, REMAINDER 8);
        CREATE TABLE memory_episodes_p09 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 16, REMAINDER 9);
        CREATE TABLE memory_episodes_p10 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 16, REMAINDER 10);
        CREATE TABLE memory_episodes_p11 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 16, REMAINDER 11);
        CREATE TABLE memory_episodes_p12 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 16, REMAINDER 12);
        CREATE TABLE memory_episodes_p13 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 16, REMAINDER 13);
        CREATE TABLE memory_episodes_p14 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 16, REMAINDER 14);
        CREATE TABLE memory_episodes_p15 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 16, REMAINDER 15);

        -- 4. ⚠️ HNSW 索引在父表创建，PostgreSQL 自动传播到所有子分区
        --    （包括未来新增的分区，无需手动补建）
        --    ef_construction=128 提升图构建精度（原 64 偏低）
        CREATE INDEX idx_mem_embedding_hnsw ON memory_episodes
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 128);

        -- 5. 辅助索引（同样在父表创建，自动传播）
        CREATE INDEX idx_mem_char_time ON memory_episodes (character_id, timestamp DESC);
        CREATE INDEX idx_mem_char_imp  ON memory_episodes (character_id, importance DESC);
        CREATE INDEX idx_mem_related   ON memory_episodes USING gin (related_characters);
        CREATE INDEX idx_mem_unreflected ON memory_episodes (character_id) WHERE is_reflected = FALSE;
        -- materialized=false 的部分索引：用于异步 embedding worker 批量拉取
        CREATE INDEX idx_mem_unmaterialized ON memory_episodes (timestamp) WHERE materialized = FALSE;

        -- 6. 迁移旧数据（⚠️ 大表锁警告，见函数 docstring）
        INSERT INTO memory_episodes (
            id, character_id, content, embedding, importance, timestamp,
            action_id, location, related_characters, is_reflected,
            materialized, source_type
        )
        SELECT
            id, character_id, content,
            CASE WHEN embedding IS NOT NULL THEN embedding::vector ELSE NULL END,
            importance, timestamp, action_id, location, related_characters,
            is_reflected,
            CASE WHEN embedding IS NOT NULL THEN TRUE ELSE FALSE END,
            source_type
        FROM memory_episodes_old;

        -- 7. 删除旧表
        DROP TABLE memory_episodes_old;
    """)

    # ============================================================
    # 改进 4: 删除 DEFAULT 分区 + RAISE EXCEPTION 触发器
    # ============================================================
    # 问题：DEFAULT 分区兜底 → 慢查询定时炸弹
    # 方案：删除 DEFAULT 分区，改为 BEFORE INSERT 触发器抛异常
    #       强制运维预创建分区，不要"兜底"

    op.execute("""
        -- 删除 action_records 的 DEFAULT 分区
        DROP TABLE IF EXISTS action_records_default;

        -- 删除 messages 的 DEFAULT 分区
        DROP TABLE IF EXISTS messages_default;

        -- 创建分区检查函数：若分区不存在则抛异常
        CREATE OR REPLACE FUNCTION check_partition_exists()
        RETURNS TRIGGER AS $$
        DECLARE
            partition_name TEXT;
        BEGIN
            -- 对于按月分区的表，检查目标分区是否存在
            IF TG_TABLE_NAME = 'action_records' THEN
                partition_name := 'action_records_' ||
                    to_char(NEW.created_at, 'YYYY_MM');
            ELSIF TG_TABLE_NAME = 'messages' THEN
                partition_name := 'messages_' ||
                    to_char(NEW.created_at, 'YYYY_MM');
            ELSE
                RETURN NEW;
            END IF;

            -- 检查分区是否存在
            IF NOT EXISTS (
                SELECT 1 FROM pg_class WHERE relname = partition_name
            ) THEN
                RAISE EXCEPTION
                    'Partition % does not exist for table %. '
                    'Run partition pre-creation task or create manually: '
                    'CREATE TABLE % PARTITION OF % FOR VALUES FROM (...)',
                    partition_name, TG_TABLE_NAME, partition_name, TG_TABLE_NAME;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        -- 在分区表上创建触发器（BEFORE INSERT）
        CREATE TRIGGER trg_action_partition_check
            BEFORE INSERT ON action_records
            FOR EACH ROW EXECUTE FUNCTION check_partition_exists();

        CREATE TRIGGER trg_messages_partition_check
            BEFORE INSERT ON messages
            FOR EACH ROW EXECUTE FUNCTION check_partition_exists();
    """)

    # ============================================================
    # 改进 5: 删除 world_snapshots，仅保留 world_events
    # ============================================================
    # 问题：world_snapshots 与 world_events 双写冗余
    # 方案：删除 world_snapshots，回放从 world_events 重建
    op.execute("DROP TABLE IF EXISTS world_snapshots;")

    op.create_table(
        "world_events",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("uuidv7()")),
        sa.Column("tick_id", sa.BigInteger, nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False,
                  comment="time/weather/scene/resource/event"),
        sa.Column("payload", sa.JSONB, nullable=False,
                  comment="变更内容（仅差分）"),
        sa.Column("created_at", sa.TIMESTAMPTZ, server_default=sa.text("now()")),
    )
    op.create_index("idx_world_events_tick", "world_events", ["tick_id"])
    op.create_index("idx_world_events_type_time", "world_events", ["event_type", "created_at DESC"])

    # ============================================================
    # 改进 7: 彻底删除 personality 列，统一到 traits
    # ============================================================
    # 问题：personality TEXT[] 与 traits JSONB 冗余，易不一致
    # 方案：先迁移数据到 traits.personality，再删除 personality 列
    # ⚠️ 修复：使用 COALESCE 防御 traits 为 NULL 的情况
    op.execute("""
        -- 将 personality 迁移到 traits.personality（⚠️ COALESCE 防御 NULL）
        UPDATE characters
        SET traits = COALESCE(traits, '{}'::jsonb) || jsonb_build_object('personality', to_jsonb(personality))
        WHERE personality IS NOT NULL AND personality <> '{}';

        -- 彻底删除 personality 列
        ALTER TABLE characters DROP COLUMN personality;
    """)

    # ============================================================
    # 改进 6: reflection_sources 中间表（替代 UUID[] 无外键）
    # ============================================================
    op.create_table(
        "reflection_sources",
        sa.Column("reflection_id", sa.UUID,
                  sa.ForeignKey("reflections.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("memory_id", sa.UUID,
                  primary_key=True,
                  comment="memory_episodes.id（应用层保证存在）"),
        sa.Column("created_at", sa.TIMESTAMPTZ, server_default=sa.text("now()")),
    )
    op.create_index("idx_refl_sources_memory", "reflection_sources", ["memory_id"])

    # ============================================================
    # 改进 8+9: character_states 乐观锁 + updated_at 触发器
    # ============================================================
    op.add_column(
        "character_states",
        sa.Column("version", sa.Integer, nullable=False, server_default="1",
                  comment="乐观锁版本号")
    )

    # updated_at 自动更新触发器
    op.execute("""
        CREATE OR REPLACE FUNCTION update_character_states_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_character_states_updated_at
            BEFORE UPDATE ON character_states
            FOR EACH ROW EXECUTE FUNCTION update_character_states_updated_at();
    """)

    # ============================================================
    # 改进 3: 覆盖索引（移除 content，避免索引膨胀）
    # ============================================================
    # 问题：INCLUDE (content) 会导致索引体积膨胀（content 可能 2000 字）
    # 方案：仅包含轻量字段，content 走主键回表
    op.execute("""
        -- messages.user_id 覆盖索引（仅轻量字段）
        CREATE INDEX idx_msg_user_time_cover
        ON messages (user_id, created_at DESC)
        INCLUDE (role, platform);

        -- messages.conversation_id 覆盖索引（仅轻量字段）
        CREATE INDEX idx_msg_conv_time_cover
        ON messages (conversation_id, created_at)
        INCLUDE (role, character_id, platform);
    """)


def downgrade() -> None:
    """
    ⚠️ downgrade 风险极高，建议通过备份恢复而非回滚迁移。
    """
    # 回滚覆盖索引
    op.execute("DROP INDEX IF EXISTS idx_msg_conv_time_cover;")
    op.execute("DROP INDEX IF EXISTS idx_msg_user_time_cover;")

    # 回滚 character_states 触发器 + version
    op.execute("DROP TRIGGER IF EXISTS trg_character_states_updated_at ON character_states;")
    op.execute("DROP FUNCTION IF EXISTS update_character_states_updated_at();")
    op.drop_column("character_states", "version")

    # 回滚 reflection_sources
    op.drop_table("reflection_sources")

    # 回滚 personality 列（无法恢复数据，仅重建列）
    op.execute("ALTER TABLE characters ADD COLUMN personality JSONB DEFAULT '[]';")

    # 回滚 world_events + 重建 world_snapshots
    op.drop_table("world_events")
    op.create_table(
        "world_snapshots",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("uuidv7()")),
        sa.Column("tick_id", sa.BigInteger),
        sa.Column("state", sa.JSONB),
        sa.Column("captured_at", sa.TIMESTAMPTZ, server_default=sa.text("now()")),
    )

    # 回滚 DEFAULT 分区 + 删除触发器
    op.execute("DROP TRIGGER IF EXISTS trg_action_partition_check ON action_records;")
    op.execute("DROP TRIGGER IF EXISTS trg_messages_partition_check ON messages;")
    op.execute("DROP FUNCTION IF EXISTS check_partition_exists();")
    op.execute("""
        CREATE TABLE action_records_default PARTITION OF action_records DEFAULT;
        CREATE TABLE messages_default PARTITION OF messages DEFAULT;
    """)

    # 回滚 memory_episodes 分区改造（风险极高）
    op.execute("""
        CREATE TABLE memory_episodes_rollback AS
        SELECT id, character_id, content, embedding, importance, timestamp,
               action_id, location, related_characters, is_reflected, source_type
        FROM memory_episodes;

        DROP TABLE memory_episodes;
        ALTER TABLE memory_episodes_rollback RENAME TO memory_episodes;

        CREATE INDEX idx_mem_embedding_hnsw ON memory_episodes
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);
        CREATE INDEX idx_mem_char_time ON memory_episodes (character_id, timestamp DESC);
    """)
