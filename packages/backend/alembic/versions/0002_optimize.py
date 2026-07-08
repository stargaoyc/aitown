"""数据库性能与完整性优化

基于生产环境审查反馈的 11 项改进：
1. memory_episodes 按 character_id HASH 分区 + 分区级 HNSW 索引
2. memory_episodes 增加 materialized 标志（embedding 异步生成）
3. DEFAULT 分区加监控函数
4. world_snapshots 降频 + 新增 world_events 差分事件表
5. 统一 personality 到 traits JSONB
6. 新建 reflection_sources 中间表（外键约束）
7. messages 增加 conversation_id 覆盖索引
8. character_states 增加乐观锁版本号
9. pg_uuidv7 应用层兜底文档（无 DDL 变更）
10. messages.user_id 覆盖索引
11. HNSW ef_construction 64 → 128

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
    ⚠️ 注意：memory_episodes 分区改造需要重建表（数据迁移）。
    生产环境执行前需先备份数据，再在维护窗口执行。
    """

    # ============================================================
    # 改进 1+2+11: memory_episodes 重建为 HASH 分区 + materialized 标志 + ef_construction=128
    # ============================================================
    # 问题：全局 HNSW + WHERE character_id = :cid 导致召回率崩塌
    # 方案：按 character_id HASH 分区（10 分区），每分区独立 HNSW 索引
    #       查询时分区裁剪直接命中单分区，HNSW 只搜索该角色数据
    #
    # 同时：增加 materialized 标志区分原始日志与向量化记忆
    #       ef_construction 64→128 提升图精度

    op.execute("""
        -- 1. 重命名旧表
        ALTER TABLE memory_episodes RENAME TO memory_episodes_old;

        -- 2. 创建新的分区表
        CREATE TABLE memory_episodes (
            id                 UUID NOT NULL DEFAULT uuidv7(),
            character_id       UUID NOT NULL,
            content            TEXT NOT NULL,
            embedding          vector(1536),                    -- nullable: materialized=false 时为 NULL
            importance         INT  NOT NULL DEFAULT 5 CHECK (importance BETWEEN 1 AND 10),
            timestamp          TIMESTAMPTZ NOT NULL DEFAULT now(),
            action_id          TEXT,
            location           TEXT,
            related_characters UUID[] NOT NULL DEFAULT '{}',
            is_reflected       BOOLEAN NOT NULL DEFAULT FALSE,
            materialized       BOOLEAN NOT NULL DEFAULT FALSE,  -- embedding 是否已生成
            source_type        TEXT NOT NULL DEFAULT 'action'
                               CHECK (source_type IN ('action','conversation','reflection','event')),
            PRIMARY KEY (id, character_id)                     -- 分区表主键必须含分区键
        ) PARTITION BY HASH (character_id);

        -- 3. 创建 10 个 HASH 分区
        CREATE TABLE memory_episodes_p0 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 10, REMAINDER 0);
        CREATE TABLE memory_episodes_p1 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 10, REMAINDER 1);
        CREATE TABLE memory_episodes_p2 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 10, REMAINDER 2);
        CREATE TABLE memory_episodes_p3 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 10, REMAINDER 3);
        CREATE TABLE memory_episodes_p4 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 10, REMAINDER 4);
        CREATE TABLE memory_episodes_p5 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 10, REMAINDER 5);
        CREATE TABLE memory_episodes_p6 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 10, REMAINDER 6);
        CREATE TABLE memory_episodes_p7 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 10, REMAINDER 7);
        CREATE TABLE memory_episodes_p8 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 10, REMAINDER 8);
        CREATE TABLE memory_episodes_p9 PARTITION OF memory_episodes FOR VALUES WITH (MODULUS 10, REMAINDER 9);

        -- 4. 外键约束（分区表不支持 REFERENCES 直接引用，需用触发器或应用层保证）
        -- 此处保留外键通过应用层 ORM 保证

        -- 5. 每个分区独立的 HNSW 索引（分区裁剪后只搜索单分区）
        -- ef_construction=128 提升图构建精度（原 64 偏低）
        CREATE INDEX idx_mem_p0_hnsw ON memory_episodes_p0 USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 128);
        CREATE INDEX idx_mem_p1_hnsw ON memory_episodes_p1 USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 128);
        CREATE INDEX idx_mem_p2_hnsw ON memory_episodes_p2 USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 128);
        CREATE INDEX idx_mem_p3_hnsw ON memory_episodes_p3 USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 128);
        CREATE INDEX idx_mem_p4_hnsw ON memory_episodes_p4 USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 128);
        CREATE INDEX idx_mem_p5_hnsw ON memory_episodes_p5 USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 128);
        CREATE INDEX idx_mem_p6_hnsw ON memory_episodes_p6 USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 128);
        CREATE INDEX idx_mem_p7_hnsw ON memory_episodes_p7 USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 128);
        CREATE INDEX idx_mem_p8_hnsw ON memory_episodes_p8 USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 128);
        CREATE INDEX idx_mem_p9_hnsw ON memory_episodes_p9 USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 128);

        -- 6. 辅助索引（分区表级）
        CREATE INDEX idx_mem_char_time ON memory_episodes (character_id, timestamp DESC);
        CREATE INDEX idx_mem_char_imp  ON memory_episodes (character_id, importance DESC);
        CREATE INDEX idx_mem_related   ON memory_episodes USING gin (related_characters);
        CREATE INDEX idx_mem_unreflected ON memory_episodes (character_id) WHERE is_reflected = FALSE;
        -- materialized=false 的部分索引：用于异步 embedding worker 批量拉取
        CREATE INDEX idx_mem_unmaterialized ON memory_episodes (timestamp) WHERE materialized = FALSE;

        -- 7. 迁移旧数据（embedding 视为已 materialized）
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

        -- 8. 删除旧表
        DROP TABLE memory_episodes_old;
    """)

    # ============================================================
    # 改进 4: world_snapshots 降频 + world_events 差分事件表
    # ============================================================
    # 问题：30s 落盘全量 JSONB → 1.2TB/年
    # 方案：world_events 记录增量变更，world_snapshots 降频到 10 分钟

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
    # 改进 5: 统一 personality 到 traits JSONB
    # ============================================================
    # 问题：personality TEXT[] 与 traits JSONB 冗余，易不一致
    # 方案：将 personality 迁移到 traits.personality，废弃 personality 列
    op.execute("""
        -- 将 personality 数组迁移到 traits.personality
        UPDATE characters
        SET traits = traits || jsonb_build_object('personality', to_jsonb(personality))
        WHERE personality IS NOT NULL AND personality <> '{}';

        -- 添加注释说明 personality 列已废弃
        COMMENT ON COLUMN characters.personality IS 'DEPRECATED: 使用 traits.personality 代替';
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
    # 反思表的 source_memory_ids 保留但标记废弃
    op.execute("COMMENT ON COLUMN reflections.source_memory_ids IS 'DEPRECATED: 使用 reflection_sources 中间表'")

    # ============================================================
    # 改进 8: character_states 乐观锁版本号
    # ============================================================
    op.add_column(
        "character_states",
        sa.Column("version", sa.Integer, nullable=False, server_default="1",
                  comment="乐观锁版本号")
    )

    # ============================================================
    # 改进 10: messages.user_id 覆盖索引
    # ============================================================
    op.execute("""
        CREATE INDEX idx_msg_user_time_cover
        ON messages (user_id, created_at DESC)
        INCLUDE (content, role, platform);
    """)

    # ============================================================
    # 改进 7: messages conversation_id 覆盖索引
    # ============================================================
    op.execute("""
        CREATE INDEX idx_msg_conv_time_cover
        ON messages (conversation_id, created_at)
        INCLUDE (content, role, character_id, platform);
    """)

    # ============================================================
    # 改进 3: DEFAULT 分区监控函数
    # ============================================================
    # 保留 DEFAULT 分区但加监控：若写入则记录告警
    op.execute("""
        CREATE OR REPLACE FUNCTION check_default_partition()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE WARNING 'Data written to DEFAULT partition: table=%, data=%',
                TG_TABLE_NAME, NEW;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_action_default_warn
            BEFORE INSERT ON action_records_default
            FOR EACH ROW EXECUTE FUNCTION check_default_partition();

        CREATE TRIGGER trg_messages_default_warn
            BEFORE INSERT ON messages_default
            FOR EACH ROW EXECUTE FUNCTION check_default_partition();
    """)


def downgrade() -> None:
    # 回滚触发器
    op.execute("DROP TRIGGER IF EXISTS trg_action_default_warn ON action_records_default;")
    op.execute("DROP TRIGGER IF EXISTS trg_messages_default_warn ON messages_default;")
    op.execute("DROP FUNCTION IF EXISTS check_default_partition();")

    # 回滚 messages 索引
    op.execute("DROP INDEX IF EXISTS idx_msg_conv_time_cover;")
    op.execute("DROP INDEX IF EXISTS idx_msg_user_time_cover;")

    # 回滚 character_states version
    op.drop_column("character_states", "version")

    # 回滚 reflection_sources
    op.drop_table("reflection_sources")

    # 回滚 personality 迁移（无法完全回滚，traits.personality 保留）
    op.execute("COMMENT ON COLUMN characters.personality IS NULL;")

    # 回滚 world_events
    op.drop_table("world_events")

    # 回滚 memory_episodes 分区改造（风险高，建议不回滚）
    # 生产环境 downgrade 此步骤需极度谨慎
    op.execute("""
        -- 重建非分区表
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
