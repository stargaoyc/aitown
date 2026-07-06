# 数据模型设计

> 本文档定义 AI Town 的全部数据库表结构、ER 关系、索引策略。所有持久化数据统一存储于 PostgreSQL 17 + pgvector，主键使用 UUID v7（时间有序），时间字段统一 TIMESTAMPTZ。

---

## 一、扩展与命名约定

### 1.1 启用扩展

```sql
CREATE EXTENSION IF NOT EXISTS pg_uuidv7;   -- 时间有序 UUID v7 生成
CREATE EXTENSION IF NOT EXISTS "vector";     -- pgvector 向量检索
CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- 文本模糊检索
-- 注意: 不再使用 uuid-ossp, 改用 pg_uuidv7 提供 uuidv7()
```

### 1.2 命名约定

| 项 | 约定 |
|----|------|
| 主键 | `id UUID DEFAULT uuidv7()`（UUID v7，时间有序） |
| 时间戳 | `created_at` / `updated_at TIMESTAMPTZ DEFAULT now()` |
| 业务时间 | `timestamp` / `due_at` / `captured_at` 等统一为 `TIMESTAMPTZ` |
| 软删除 | `deleted_at TIMESTAMPTZ`（按需） |
| 灵活字段 | 用 `JSONB`，不用 `JSON` |
| 数组字段 | 用 `TEXT[]` / `UUID[]` |
| 表名 | 复数蛇形（`characters`、`action_records`） |

### 1.3 主键选型说明

使用 **UUID v7**（RFC 9562）而非 UUID v4：
- UUID v4 完全随机 → B-tree 页分裂严重、缓存局部性差、写入性能衰减；
- UUID v7 前 48 位为毫秒时间戳 → 时间单调递增 → 顺序追加 → 索引友好；
- 后 80 位随机 → 防枚举、分布式可独立生成。

详见 [架构设计 - 主键选型](architecture.md#51-主键选型uuid-v7时间有序-uuid)。

---

## 二、ER 关系图

```text
┌──────────────────────┐         ┌──────────────────────┐
│  characters          │◀────────│  relations           │
│  (角色定义)          │  from/to│  (角色关系)          │
└──────────┬───────────┘         └──────────────────────┘
           │ 1:N
           ▼
┌──────────────────────┐         ┌──────────────────────┐
│  character_states    │         │  action_records      │
│  (实时态, Redis 镜像)│         │  (行为历史, 分区)    │
└──────────────────────┘         └──────────┬───────────┘
                                            │ 1:N
           ┌──────────────────────┐         ▼
           │  memory_episodes     │◀────────┘
           │  (向量记忆)          │
           │  embedding vector    │
           └──────────┬───────────┘
                      │ 1:N (source)
                      ▼
           ┌──────────────────────┐         ┌──────────────────────┐
           │  reflections         │         │  plans               │
           │  (反思总结)          │         │  (长期规划)          │
           └──────────────────────┘         └──────────────────────┘

┌──────────────────────┐         ┌──────────────────────┐
│  messages            │         │  module_configs      │
│  (对话历史, 分区)    │         │  (模块配置)          │
└──────────────────────┘         └──────────────────────┘

┌──────────────────────┐
│  world_snapshots     │  (周期性世界状态快照, 用于回放)
└──────────────────────┘
```

---

## 三、表结构 DDL

### 3.1 characters（角色定义）

```sql
CREATE TABLE characters (
    id           UUID PRIMARY KEY DEFAULT uuidv7(),
    name         TEXT NOT NULL,
    age          INT  NOT NULL CHECK (age >= 0 AND age <= 200),
    occupation   TEXT NOT NULL,
    personality  TEXT[] NOT NULL DEFAULT '{}',           -- ["开朗","细心"]
    traits       JSONB NOT NULL DEFAULT '{}'::jsonb,      -- 自定义属性
    backstory    TEXT NOT NULL DEFAULT '',
    avatar_url   TEXT,
    status       TEXT NOT NULL DEFAULT 'active'
                 CHECK (status IN ('active','archived','deleted')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_characters_name_trgm ON characters USING gin (name gin_trgm_ops);
CREATE INDEX idx_characters_traits    ON characters USING gin (traits jsonb_path_ops);
CREATE INDEX idx_characters_status    ON characters (status);
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID (v7) | 主键，时间有序 |
| `name` | TEXT | 角色名 |
| `age` | INT | 年龄 |
| `occupation` | TEXT | 职业 |
| `personality` | TEXT[] | 性格标签数组 |
| `traits` | JSONB | 自定义属性（灵活） |
| `backstory` | TEXT | 背景故事 |
| `avatar_url` | TEXT | 头像 URL |
| `status` | TEXT | `active`/`archived`/`deleted` |

### 3.2 character_states（实时态持久镜像）

> 实时高频读写仍走 Redis，PG 仅作持久镜像与冷启动恢复。

```sql
CREATE TABLE character_states (
    character_id      UUID PRIMARY KEY REFERENCES characters(id) ON DELETE CASCADE,
    location          TEXT NOT NULL,
    current_action    TEXT,
    action_started_at TIMESTAMPTZ,                       -- 统一 TIMESTAMPTZ
    energy            INT  NOT NULL DEFAULT 100 CHECK (energy BETWEEN 0 AND 100),
    hunger            INT  NOT NULL DEFAULT 0   CHECK (hunger BETWEEN 0 AND 100),
    mood              TEXT,
    last_updated      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 启动时: SELECT * FROM character_states; → 灌入 Redis
```

### 3.3 action_records（行为历史，按月分区）

```sql
CREATE TABLE action_records (
    id                 UUID NOT NULL DEFAULT uuidv7(),
    character_id       UUID NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    action_id          TEXT NOT NULL,
    action_name        TEXT NOT NULL,
    params             JSONB NOT NULL DEFAULT '{}'::jsonb,
    reason             TEXT NOT NULL DEFAULT '',
    result             TEXT NOT NULL DEFAULT '',
    duration_minutes   INT  NOT NULL DEFAULT 0,
    location           TEXT,
    related_characters UUID[] NOT NULL DEFAULT '{}',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- 分区表主键必须包含分区键
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

-- 每月一个分区 (示例: 2026-07)
CREATE TABLE action_records_2026_07 PARTITION OF action_records
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');

-- 默认分区兜底, 防止插入失败
CREATE TABLE action_records_default PARTITION OF action_records DEFAULT;

CREATE INDEX idx_ar_char_time   ON action_records (character_id, created_at DESC);
CREATE INDEX idx_ar_action      ON action_records (action_id);
CREATE INDEX idx_ar_related     ON action_records USING gin (related_characters);
CREATE INDEX idx_ar_params      ON action_records USING gin (params jsonb_path_ops);
```

### 3.4 memory_episodes（向量记忆，pgvector）

```sql
CREATE TABLE memory_episodes (
    id                 UUID PRIMARY KEY DEFAULT uuidv7(),
    character_id       UUID NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    content            TEXT NOT NULL,
    embedding          vector(1536) NOT NULL,            -- 维度由 config 决定
    importance         INT  NOT NULL DEFAULT 5 CHECK (importance BETWEEN 1 AND 10),
    timestamp          TIMESTAMPTZ NOT NULL DEFAULT now(),
    action_id          TEXT,
    location           TEXT,
    related_characters UUID[] NOT NULL DEFAULT '{}',
    is_reflected       BOOLEAN NOT NULL DEFAULT FALSE,
    source_type        TEXT NOT NULL DEFAULT 'action'
                       CHECK (source_type IN ('action','conversation','reflection','event'))
);

-- HNSW 向量索引 (生产首选, 优于 IVFFlat)
CREATE INDEX idx_mem_embedding_hnsw
    ON memory_episodes
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- 查询时调优搜索宽度
-- SET hnsw.ef_search = 40;  -- 会话级, 越大召回越高

-- 过滤+检索联合索引 (角色内检索最常见)
CREATE INDEX idx_mem_char_time ON memory_episodes (character_id, timestamp DESC);
CREATE INDEX idx_mem_char_imp   ON memory_episodes (character_id, importance DESC);
CREATE INDEX idx_mem_related    ON memory_episodes USING gin (related_characters);
CREATE INDEX idx_mem_unreflected ON memory_episodes (character_id)
    WHERE is_reflected = FALSE;                          -- 部分索引, 反思触发专用
```

### 3.5 reflections（反思总结）

```sql
CREATE TABLE reflections (
    id                 UUID PRIMARY KEY DEFAULT uuidv7(),
    character_id       UUID NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    summary            TEXT NOT NULL,                    -- "我习惯早睡早起"
    detail             TEXT NOT NULL DEFAULT '',
    source_memory_ids  UUID[] NOT NULL DEFAULT '{}',     -- 由哪些记忆归纳而来
    importance         INT  NOT NULL DEFAULT 5 CHECK (importance BETWEEN 1 AND 10),
    embedding          vector(1536),                     -- 反思向量(可选, 高层语义检索)
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_refl_char_time ON reflections (character_id, created_at DESC);
CREATE INDEX idx_refl_embedding_hnsw
    ON reflections USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

### 3.6 plans（长期规划）

```sql
CREATE TABLE plans (
    id            UUID PRIMARY KEY DEFAULT uuidv7(),
    character_id  UUID NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    title         TEXT NOT NULL,                         -- "三个月内学会咖啡拉花"
    horizon       TEXT NOT NULL CHECK (horizon IN ('daily','weekly','monthly','quarterly','yearly')),
    steps         JSONB NOT NULL DEFAULT '[]'::jsonb,    -- [{...},{...}]
    status        TEXT NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active','completed','abandoned','paused')),
    priority      INT  NOT NULL DEFAULT 5,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    due_at        TIMESTAMPTZ
);

CREATE INDEX idx_plans_char_status ON plans (character_id, status);
CREATE INDEX idx_plans_due         ON plans (due_at) WHERE status = 'active';
```

### 3.7 relations（角色关系）

```sql
CREATE TABLE relations (
    from_id    UUID NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    to_id      UUID NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    strength   INT  NOT NULL DEFAULT 0 CHECK (strength BETWEEN -100 AND 100),
    tags       TEXT[] NOT NULL DEFAULT '{}',             -- ["朋友","同学"]
    metadata   JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (from_id, to_id),
    CHECK (from_id <> to_id)
);

CREATE INDEX idx_rel_to       ON relations (to_id, strength DESC);
CREATE INDEX idx_rel_tags     ON relations USING gin (tags);
CREATE INDEX idx_rel_metadata ON relations USING gin (metadata jsonb_path_ops);
```

### 3.8 messages（对话历史，按月分区）

```sql
CREATE TABLE messages (
    id              UUID NOT NULL DEFAULT uuidv7(),
    conversation_id UUID NOT NULL,                       -- 会话 ID (无外键, 会话为逻辑概念)
    character_id    UUID REFERENCES characters(id) ON DELETE SET NULL,
    user_id         TEXT,                                -- 平台用户标识
    platform        TEXT NOT NULL CHECK (platform IN ('web','qq','lark','api')),
    role            TEXT NOT NULL CHECK (role IN ('user','assistant','system','tool')),
    content         TEXT NOT NULL,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,  -- 平台特定字段
    tokens          INT,
    cost            NUMERIC(10,6),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE messages_2026_07 PARTITION OF messages
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');

CREATE TABLE messages_default PARTITION OF messages DEFAULT;

CREATE INDEX idx_msg_conv_time ON messages (conversation_id, created_at);
CREATE INDEX idx_msg_char_time ON messages (character_id, created_at DESC);
CREATE INDEX idx_msg_user_time ON messages (user_id, created_at DESC);
CREATE INDEX idx_msg_created_brin ON messages USING brin (created_at);
```

### 3.9 module_configs（模块配置）

```sql
CREATE TABLE module_configs (
    id                   UUID PRIMARY KEY DEFAULT uuidv7(),
    name                 TEXT NOT NULL UNIQUE,
    type                 TEXT NOT NULL CHECK (type IN ('mcp','local','skill')),
    enabled              BOOLEAN NOT NULL DEFAULT FALSE,
    config               JSONB NOT NULL DEFAULT '{}'::jsonb,
    dependencies         TEXT[] NOT NULL DEFAULT '{}',
    mcp_server_url       TEXT,
    health_check_status  TEXT NOT NULL DEFAULT 'unknown'
                         CHECK (health_check_status IN ('healthy','unhealthy','unknown')),
    last_check_at        TIMESTAMPTZ,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_module_enabled ON module_configs (enabled) WHERE enabled = TRUE;
```

### 3.10 world_snapshots（世界状态周期快照）

> Redis 仅保留当前世界态，PG 周期落盘用于回放/调试。

```sql
CREATE TABLE world_snapshots (
    id          UUID PRIMARY KEY DEFAULT uuidv7(),
    tick_id     BIGINT NOT NULL,
    state       JSONB NOT NULL,                          -- 完整 WorldState
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_world_tick ON world_snapshots (tick_id);
CREATE INDEX idx_world_time ON world_snapshots (captured_at DESC);
```

---

## 四、索引策略汇总

### 4.1 索引清单

| 检索场景 | 索引 | 说明 |
|----------|------|------|
| 角色名模糊搜索 | `gin (name gin_trgm_ops)` | pg_trgm 支持相似度 |
| 角色按 traits 筛选 | `gin (traits jsonb_path_ops)` | JSONB 路径查询 |
| 角色记忆向量召回 | `hnsw (embedding vector_cosine_ops)` | HNSW，生产首选 |
| 角色内记忆按时间 | `(character_id, timestamp DESC)` | 范围扫描 |
| 未反思记忆查找 | `(character_id) WHERE is_reflected=FALSE` | 部分索引，反思专用 |
| 角色行为历史 | `(character_id, created_at DESC)` | 分区裁剪 + 索引 |
| 关联角色反查 | `gin (related_characters)` | 数组成员查询 |
| 关系图遍历 | `(from_id)` PK + `(to_id)` 索引 | 双向查询 |
| 消息会话拉取 | `(conversation_id, created_at)` | 多轮对话上下文 |
| 消息时间扫描 | `brin (created_at)` | 分区表海量时间数据 |

### 4.2 索引设计原则

1. **主键索引**：UUID v7 时间有序，B-tree 顺序追加，无碎片化；
2. **复合索引字段顺序**：等值查询字段在前，范围查询字段在后；
3. **部分索引**：高频过滤条件用 `WHERE` 缩小索引体积（如 `WHERE enabled=TRUE`、`WHERE is_reflected=FALSE`）；
4. **GIN 索引**：JSONB、数组、全文检索场景；
5. **BRIN 索引**：分区表时间列，海量数据下极小体积；
6. **HNSW 索引**：向量检索，优于 IVFFlat（无需训练、增量友好）。

---

## 五、向量检索 SQL 范式

### 5.1 基础 Top-K 检索

```sql
SELECT id, content, importance, timestamp,
       1 - (embedding <=> :q_vec) AS sim_score
FROM memory_episodes
WHERE character_id = :cid
ORDER BY embedding <=> :q_vec
LIMIT :top_k;
```

### 5.2 混合检索（向量 + 时间衰减 + 重要度）

```sql
WITH candidates AS (
    SELECT id, content, importance, timestamp,
           1 - (embedding <=> :q_vec) AS sim_score
    FROM memory_episodes
    WHERE character_id = :cid
    ORDER BY embedding <=> :q_vec
    LIMIT :top_k * 3
)
SELECT id, content,
       sim_score * 0.6
       + importance * 0.05
       + EXTRACT(EPOCH FROM (now() - timestamp)) / 86400.0 * (-0.05) AS final_score
FROM candidates
ORDER BY final_score DESC
LIMIT :top_k;
```

### 5.3 反思层检索

```sql
SELECT id, summary
FROM reflections
WHERE character_id = :cid
ORDER BY embedding <=> :q_vec
LIMIT 5;
```

### 5.4 联合检索（应用层合并）

```sql
-- 原始记忆 + 反思 UNION ALL, 应用层按 final_score 排序
SELECT 'memory' AS kind, id, content AS text, embedding <=> :q_vec AS dist
FROM memory_episodes WHERE character_id = :cid
UNION ALL
SELECT 'reflection', id, summary, embedding <=> :q_vec
FROM reflections WHERE character_id = :cid
ORDER BY dist LIMIT :top_k;
```

### 5.5 HNSW 查询时调优

```sql
-- 会话级调整搜索宽度 (越大召回越高, 延迟越大)
SET LOCAL hnsw.ef_search = 80;
SELECT ... FROM memory_episodes ORDER BY embedding <=> :q_vec LIMIT 10;
```

---

## 六、分区表维护

### 6.1 滚动新建分区

`action_records` 与 `messages` 按月分区，需预创建未来 12 个月分区：

```sql
-- 示例: 预创建 2026-08 分区
CREATE TABLE action_records_2026_08 PARTITION OF action_records
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');

CREATE TABLE messages_2026_08 PARTITION OF messages
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
```

### 6.2 自动化方案

| 方案 | 说明 |
|------|------|
| `pg_cron` 扩展 | 每月 1 日定时执行 `CREATE TABLE ... PARTITION OF` |
| 应用层定时任务 | Python `apscheduler` 每月 25 日预创建下月分区 |
| 默认分区兜底 | `CREATE TABLE ..._default PARTITION OF ... DEFAULT;` 防止插入失败 |

### 6.3 历史分区归档

- 超过 1 年的分区可 detach 后导出到对象存储（Parquet 格式）；
- PG 内仅保留近 1 年数据用于在线查询。

```sql
-- 归档旧分区
ALTER TABLE action_records DETACH PARTITION action_records_2025_07;
-- 导出后 DROP
DROP TABLE action_records_2025_07;
```

---

## 七、容量估算

| 表 | 单角色/月增量 | 50 角色年增量 | 说明 |
|----|---------------|---------------|------|
| `action_records` | ~3 万 | ~1800 万 | 按 30s/Tick, 每角色每 Tick 1 条 |
| `memory_episodes` | ~3 万 | ~1800 万 | 与 action_records 1:1 |
| `messages` | 视用户量 | — | 分区表承载 |
| `reflections` | ~50 | ~3 万 | 反思稀疏 |
| `relations` | 稳定 | ~2500 行 | 50 角色两两组合 |

PG 在 HNSW + 分区表下，单表千万级行检索 p95 < 50ms（HNSW 检索 + 过滤）。

---

## 八、ORM 模型示例

### 8.1 SQLAlchemy 2.0 风格

```python
# db/models/memory_episode.py
from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Integer, Boolean, ForeignKey, Index, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from uuid6 import uuid7                                  # 应用层兜底
from .base import Base
import uuid

class MemoryEpisode(Base):
    __tablename__ = "memory_episodes"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid7                  # 应用层生成 UUID v7
    )
    character_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE")
    )
    content: Mapped[str] = mapped_column(String)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))
    importance: Mapped[int] = mapped_column(Integer, default=5)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    action_id: Mapped[str | None]
    location: Mapped[str | None]
    related_characters: Mapped[list[uuid.UUID]] = mapped_column(default=list)
    is_reflected: Mapped[bool] = mapped_column(Boolean, default=False)
    source_type: Mapped[str] = mapped_column(String, default="action")

    __table_args__ = (
        Index("idx_mem_char_time", "character_id", timestamp.desc()),
        Index("idx_mem_unreflected", "character_id")
            .where(is_reflected == False),               # 部分索引
        # HNSW 索引通过 alembic 迁移用 raw SQL 创建
    )
```

### 8.2 alembic 创建 HNSW 索引与扩展

HNSW 索引与 pg_uuidv7 扩展不能通过 ORM `Index` 自动生成，需在 alembic 升级脚本中用 `op.execute()` 写原生 SQL：

```python
# migrations/versions/xxxx_init.py
def upgrade():
    # 1. 扩展
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_uuidv7;")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    # 2. 建表 (使用 uuidv7() 默认值)
    op.create_table(
        "memory_episodes",
        sa.Column("id", sa.UUID, primary_key=True,
                  server_default=sa.text("uuidv7()")),
        # ... 其他字段 ...
    )

    # 3. HNSW 向量索引
    op.execute(
        "CREATE INDEX idx_mem_embedding_hnsw ON memory_episodes "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64);"
    )

    # 4. 部分索引
    op.execute(
        "CREATE INDEX idx_mem_unreflected ON memory_episodes (character_id) "
        "WHERE is_reflected = FALSE;"
    )

def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_mem_embedding_hnsw;")
    op.execute("DROP INDEX IF EXISTS idx_mem_unreflected;")
    op.drop_table("memory_episodes")
```

---

## 九、相关文档

| 主题 | 文档 |
|------|------|
| 架构决策（UUID v7 / HNSW / 连接池） | [architecture.md](architecture.md) |
| 记忆系统 | [memory-system.md](memory-system.md) |
| 开发指南（Repository 模式） | [development-guide.md](development-guide.md) |
