"""初始化数据库：扩展 + 核心表

Revision ID: 0001_init
Revises:
Create Date: 2026-07-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_init"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 扩展
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_uuidv7;")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    # 2. characters 表
    op.create_table(
        "characters",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("uuidv7()")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("age", sa.Integer),
        sa.Column("occupation", sa.String(100)),
        sa.Column("personality", sa.JSONB),
        sa.Column("traits", sa.JSONB),
        sa.Column("backstory", sa.Text),
        sa.Column("avatar_url", sa.String(500)),
        sa.Column("voice_preset", sa.String(100)),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.TIMESTAMPTZ, server_default=sa.text("now()")),
    )

    # 3. character_states 表（PG 镜像）
    op.create_table(
        "character_states",
        sa.Column("character_id", sa.UUID, sa.ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("location", sa.String(50)),
        sa.Column("stamina", sa.Integer, default=80),
        sa.Column("satiety", sa.Integer, default=60),
        sa.Column("mood", sa.String(20)),
        sa.Column("money", sa.Integer, default=500),
        sa.Column("inventory", sa.JSONB),
        sa.Column("current_action", sa.JSONB),
        sa.Column("phone_battery", sa.Integer, default=75),
        sa.Column("social_energy", sa.Integer, default=60),
        sa.Column("updated_at", sa.TIMESTAMPTZ, server_default=sa.text("now()")),
    )

    # 4. action_records 表（分区表）
    op.create_table(
        "action_records",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("uuidv7()")),
        sa.Column("character_id", sa.UUID, sa.ForeignKey("characters.id", ondelete="CASCADE")),
        sa.Column("action_id", sa.String(100)),
        sa.Column("action_name", sa.String(100)),
        sa.Column("params", sa.JSONB),
        sa.Column("reason", sa.Text),
        sa.Column("result", sa.Text),
        sa.Column("duration_minutes", sa.Integer),
        sa.Column("location", sa.String(50)),
        sa.Column("related_characters", sa.JSONB),
        sa.Column("timestamp", sa.TIMESTAMPTZ, server_default=sa.text("now()")),
    )
    # 分区（按月）
    op.execute("""
        CREATE TABLE action_records_2026_07 PARTITION OF action_records
        FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
    """)
    # 默认分区
    op.execute("""
        CREATE TABLE action_records_default PARTITION OF action_records DEFAULT;
    """)
    op.create_index("idx_action_char_time", "action_records", ["character_id", sa.text("timestamp DESC")])

    # 5. memory_episodes 表（含向量）
    op.create_table(
        "memory_episodes",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("uuidv7()")),
        sa.Column("character_id", sa.UUID, sa.ForeignKey("characters.id", ondelete="CASCADE")),
        sa.Column("content", sa.Text),
        sa.Column("embedding", sa.Text),  # pgvector Vector(1536) 需原生 SQL
        sa.Column("importance", sa.Integer, default=5),
        sa.Column("timestamp", sa.TIMESTAMPTZ, server_default=sa.text("now()")),
        sa.Column("action_id", sa.String(100)),
        sa.Column("location", sa.String(50)),
        sa.Column("related_characters", sa.JSONB),
        sa.Column("is_reflected", sa.Boolean, default=False),
        sa.Column("source_type", sa.String(20), default="action"),
    )
    # HNSW 向量索引
    op.execute("""
        CREATE INDEX idx_mem_embedding_hnsw ON memory_episodes
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
    """)
    op.create_index("idx_mem_char_time", "memory_episodes", ["character_id", sa.text("timestamp DESC")])
    op.create_index("idx_mem_unreflected", "memory_episodes", ["character_id"], postgresql_where=sa.text("is_reflected = FALSE"))

    # 6. plans 表
    op.create_table(
        "plans",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("uuidv7()")),
        sa.Column("character_id", sa.UUID, sa.ForeignKey("characters.id", ondelete="CASCADE")),
        sa.Column("type", sa.String(20)),
        sa.Column("title", sa.String(200)),
        sa.Column("description", sa.Text),
        sa.Column("status", sa.String(20), default="active"),
        sa.Column("priority", sa.Integer, default=3),
        sa.Column("deadline", sa.TIMESTAMPTZ),
        sa.Column("progress", sa.Integer, default=0),
        sa.Column("created_at", sa.TIMESTAMPTZ, server_default=sa.text("now()")),
    )

    # 7. relations 表
    op.create_table(
        "relations",
        sa.Column("character_id", sa.UUID, sa.ForeignKey("characters.id", ondelete="CASCADE")),
        sa.Column("target_id", sa.UUID, sa.ForeignKey("characters.id", ondelete="CASCADE")),
        sa.Column("strength", sa.Integer, default=20),
        sa.Column("relationship_type", sa.String(30)),
        sa.Column("last_interaction_at", sa.TIMESTAMPTZ),
        sa.Column("notes", sa.Text),
        sa.PrimaryKeyConstraint("character_id", "target_id"),
    )

    # 8. reflections 表
    op.create_table(
        "reflections",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("uuidv7()")),
        sa.Column("character_id", sa.UUID, sa.ForeignKey("characters.id", ondelete="CASCADE")),
        sa.Column("content", sa.Text),
        sa.Column("related_episodes", sa.JSONB),
        sa.Column("created_at", sa.TIMESTAMPTZ, server_default=sa.text("now()")),
    )

    # 9. world_snapshots 表
    op.create_table(
        "world_snapshots",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("uuidv7()")),
        sa.Column("tick_id", sa.BigInteger),
        sa.Column("world_time", sa.TIMESTAMPTZ),
        sa.Column("weather", sa.String(20)),
        sa.Column("locations", sa.JSONB),
        sa.Column("resources", sa.JSONB),
        sa.Column("active_events", sa.JSONB),
        sa.Column("created_at", sa.TIMESTAMPTZ, server_default=sa.text("now()")),
    )
    op.create_index("idx_world_tick", "world_snapshots", ["tick_id"])


def downgrade() -> None:
    op.drop_table("world_snapshots")
    op.drop_table("reflections")
    op.drop_table("relations")
    op.drop_table("plans")
    op.execute("DROP INDEX IF EXISTS idx_mem_unreflected;")
    op.execute("DROP INDEX IF EXISTS idx_mem_char_time;")
    op.execute("DROP INDEX IF EXISTS idx_mem_embedding_hnsw;")
    op.drop_table("memory_episodes")
    op.execute("DROP TABLE IF EXISTS action_records_default;")
    op.execute("DROP TABLE IF EXISTS action_records_2026_07;")
    op.drop_index("idx_action_char_time")
    op.drop_table("action_records")
    op.drop_table("character_states")
    op.drop_table("characters")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm;")
    op.execute("DROP EXTENSION IF EXISTS vector;")
    op.execute("DROP EXTENSION IF EXISTS pg_uuidv7;")