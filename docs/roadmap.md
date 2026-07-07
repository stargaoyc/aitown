# 开发路线图

> 本文档定义 AI Town 的开发阶段、里程碑、任务分解与优先级排序。采用**渐进交付**策略，每个阶段交付可运行、可验证的核心功能。

---

## 一、开发阶段概览

```text
Phase 0: 项目初始化           ← 当前
   ├─ 创建项目结构（monorepo）
   ├─ 初始化 packages（backend / frontend / mcp-servers）
   ├─ 配置依赖管理与构建脚本
   └─ 数据库 DDL 迁移脚本
        ↓
Phase 1: 世界引擎核心
   ├─ World Tick 演化列表（Time/Weather/Scene）
   ├─ Character Tick 五阶段闭环
   ├─ Action 系统注册与执行（事务化）
   └─ 记忆系统（MemoryEpisode + pgvector）
        ↓
Phase 2: 角色与小镇
   ├─ 角色卡导入与状态初始化
   ├─ 小镇场景系统与移动矩阵
   ├─ 作息系统与动态耗时
   └─ 节日与事件触发
        ↓
Phase 3: 外部交互
   ├─ 消息服务（QQ/飞书/Web WebSocket）
   ├─ 主动分享链路
   ├─ MCP Server 自研（code-executor / shop-simulator）
   └─ MCP Server 社区集成（web-search / weather）
        ↓
Phase 4: 可观测性与运维
   ├─ OTel Trace 全链路埋点
   ├─ Grafana Alloy 日志采集
   ├─ Grafana 统一面板
   └─ Langfuse LLM 追踪
        ↓
Phase 5: 前端 Dashboard
   ├─ 角色状态可视化
   ├─ 世界地图与场景热力图
   ├─ Trace/Memory 调试面板
   └─ 管理命令入口
```

---

## 二、Phase 0：项目初始化（预计 1 周）

### 2.1 任务清单

| 任务 | 优先级 | 依赖 | 验收标准 |
|------|--------|------|----------|
| 创建 monorepo 结构（pnpm workspace） | P0 | — | `pnpm ls` 能列出所有包 |
| 初始化 `packages/backend`（Python 3.13 + uv） | P0 | monorepo | `uv sync` 成功，`uvicorn` 可启动 |
| 初始化 `packages/frontend`（React 19 + Vite 8） | P0 | monorepo | `pnpm dev` 启动 Vite |
| 初始化 `packages/mcp-servers/code-executor` | P1 | monorepo | `uv run server.py` 可监听 |
| 数据库 DDL（pgvector + pg_uuidv7 + HNSW） | P0 | backend | `alembic upgrade head` 成功 |
| Docker Compose（postgres/redis/minio） | P0 | — | `docker compose up` 启动基础设施 |
| 环境变量示例 `.env.example` | P0 | — | 包含所有必填变量 |

### 2.2 目录结构

```text
e:\projects\aitown/
├── packages/
│   ├── backend/                   # Python 后端
│   │   ├── src/
│   │   │   ├── core/              # 世界引擎核心
│   │   │   ├── db/                # 数据库模型与迁移
│   │   │   ├── api/               # FastAPI 路由
│   │   │   ├── memory/            # 记忆服务
│   │   │   ├── modules/           # MCP 模块管理
│   │   │   ├── messaging/         # 消息服务
│   │   │   ├── tools/             # MCP 工具层
│   │   │   ├── observability/     # OTel 配置
│   │   │   └── config.py
│   │   ├── tests/
│   │   ├── pyproject.toml
│   │   ├── alembic.ini
│   │   └── Dockerfile
│   ├── frontend/                  # React 前端
│   │   ├── src/
│   │   ├── public/
│   │   ├── package.json
│   │   ├── vite.config.ts
│   │   ├── tailwind.config.ts
│   │   ├── oxlint.json
│   │   └── Dockerfile
│   └── mcp-servers/
│       ├── code-executor/         # 自研 MCP
│       ├── shop-simulator/
│       └── character-social/
├── configs/
│   ├── characters/                # 角色卡 YAML
│   ├── prompts/                   # Prompt 模板
│   ├── scenes.yaml                # 小镇场景
│   ├── events.yaml                # 节日配置
│   └── world-map.yaml             # 世界地图
├── docker/
│   ├── postgres/                  # 自定义镜像（pgvector + pg_uuidv7）
│   └── grafana/
├── docs/                          # 设计文档（已完成）
├── .env.example
├── docker-compose.yml
├── docker-compose.infra.yml       # 仅基础设施
├── pnpm-workspace.yaml
├── README.md
└── ROADMAP.md                     # 本文档
```

---

## 三、Phase 1：世界引擎核心（预计 2 周）

### 3.1 World Tick（演化列表）

| 任务 | 说明 | 验收 |
|------|------|------|
| `TimeEvolution` | 虚拟时钟推进，每 Tick +10 分钟 | 单元测试：10 Tick 后时间正确 |
| `WeatherEvolution` | 天气状态变化，每 60 Tick 更新 | 天气符合配置的概率分布 |
| `SceneEvolution` | 场景开放/拥挤度更新 | 拥挤度与 `visitors` 数量一致 |
| `EventEvolution` | 节日/事件触发 | 樱花祭日期触发 `active_events` |
| Redis 状态读写 | `world:state` 结构持久化 | 断电恢复后状态一致 |

### 3.2 Character Tick（五阶段闭环）

| 任务 | 说明 | 验收 |
|------|------|------|
| 感知环境 | 读取角色/世界/记忆状态 | 返回完整 context |
| 候选 Action 过滤 | `precondition` 检查 | 候选列表非空（至少有"等待"） |
| LLM 决策 | 结构化输出（action/reason/planChanges） | 输出解析成功，非法决策回退 |
| Action 执行 | 事务化（PG + Redis） | 单一事务，失败回滚 |
| 记忆沉淀 | 写入 `memory_episodes` + embedding | pgvector 可检索 |

### 3.3 Action 系统

| 任务 | 说明 | 验收 |
|------|------|------|
| ActionRegistry | 注册/注销/候选过滤 | 注册后可列出 |
| 核心 Action | 移动/生活/工作/社交 10+ 个 | precondition 过滤正确 |
| Action executor | 状态变化 + 行为记录 | 事务内多表写入成功 |
| 完成事件广播 | Redis Streams `ActionCompleted` | 消费组可订阅 |

### 3.4 记忆系统

| 任务 | 说明 | 验收 |
|------|------|------|
| MemoryEpisode 模型 | 含向量字段 + HNSW 索引 | 插入后可检索 Top-K |
| 混合检索排序 | 语义 + 重要性 + 时间衰减 | 排序得分计算正确 |
| 人物记忆沉淀 | 对话窗口触发 | 写入 `person_memory` |
| 反思触发器 | 累计阈值触发 LLM 反思 | 生成 Reflection 写入 |

---

## 四、Phase 2：角色与小镇（预计 1 周）

### 4.1 角色系统

| 任务 | 说明 | 验收 |
|------|------|------|
| 角色卡导入 CLI | YAML → PG `characters` 表 | 导入后角色可参与 Tick |
| 实时状态初始化 | Redis `char:{id}:state` | 状态字段完整 |
| 作息系统 | `traits.schedule` 影响 | 夜猫子夜间活跃 |
| 计划系统 | PG `plans` 表 + planChanges | 计划推进/完成 |

### 4.2 小镇系统

| 任务 | 说明 | 验收 |
|------|------|------|
| 场景配置加载 | `world-map.yaml` → Redis | 场景开放时间正确 |
| 移动矩阵 | 场景间耗时查表 | 移动 Action 时耗正确 |
| 动态耗时 | 天气/拥挤度调整 | 雨天移动耗时 ×1.5 |
| 资源循环 | World Tick 资源增减 | 资源过低触发物价上涨 |

---

## 五、Phase 3：外部交互（预计 2 周）

### 5.1 消息服务

| 任务 | 说明 | 验收 |
|------|------|------|
| Satori 网关 | OneBot v12 adapter | 收到 QQ 消息能标准化 |
| 飞书 adapter | Lark API 接入 | 飞书消息能标准化 |
| Web WebSocket | 浏览器接入 | 客户端能收发消息 |
| 回复生成 | LLM 生成自然语言回复 | 回复引用真实经历 |

### 5.2 主动分享

| 任务 | 说明 | 验收 |
|------|------|------|
| 分享意图评估 | `proactiveShareIntent` → 再走 LLM | 判断是否适合分享 |
| 分享文案生成 | 自然语言，不暴露工程概念 | 文案符合角色性格 |
| 发送调度 | 群聊/私聊选择 | 不刷屏 |

### 5.3 MCP Servers

| 任务 | 说明 | 验收 |
|------|------|------|
| code-executor（自研） | Python 代码沙箱执行 | 返回执行结果 |
| shop-simulator（自研） | 商店购买模拟 | 更新角色 inventory |
| web-search（社区） | Tavily API 集成 | 搜索结果返回 |
| weather（社区） | OpenWeatherMap 集成 | 天气查询返回 |

---

## 六、Phase 4：可观测性与运维（预计 1 周）

### 6.1 Trace

| 任务 | 说明 | 验收 |
|------|------|------|
| OTel SDK 集成 | `start_span` 埋点 | Jaeger 可查看链路 |
| Trace 采样 | 0.5 采样率 | 采样后仍可追踪关键路径 |
| Langfuse 集成 | LLM Prompt/Token 审计 | Langfuse 可查看对话记录 |

### 6.2 Metrics

| 任务 | 说明 | 验收 |
|------|------|------|
| Prometheus 指标 | Tick 耗时 / Action 成败 / LLM 调用 | Grafana 可查询 |
| 告警规则 | 5xx / Tick 延迟 / LLM 失败率 | 告警触发飞书通知 |

### 6.3 Logs

| 任务 | 说明 | 验收 |
|------|------|------|
| 结构化 JSON 日志 | stdout → stdout | 日志含 trace_id |
| Grafana Alloy 采集 | Docker 容器日志 → Loki | Grafana Logs 面板可查询 |
| Trace ↔ Logs 联动 | trace_id 关联 | Jaeger Span 可跳转 Logs |

---

## 七、Phase 5：前端 Dashboard（预计 2 周）

### 7.1 页面清单

| 页面 | 说明 |
|------|------|
| `/` | 世界总览：时间/天气/活跃角色数 |
| `/characters` | 角色列表：状态/位置/当前行为 |
| `/character/:id` | 角色详情：状态/记忆/计划/关系 |
| `/map` | 小镇地图：场景热力图（拥挤度） |
| `/traces` | Trace 调试：按 trace_id 查链路 |
| `/admin` | 管理入口：暂停/恢复/快照回放/强制 Tick |

### 7.2 技术验收

| 任务 | 验收 |
|------|------|
| React 19 + Compiler | 无手写 useMemo/useCallback |
| ES2024 特性 | 使用 Set.intersection 等 |
| oxlint + oxfmt | lint/format 通过 |
| TanStack Query | WebSocket 实时数据流 |
| Tailwind v4 + 二次元配色 | GlassCard 组件渲染正确 |

---

## 八、里程碑与交付物

| 里程碑 | 预计周期 | 交付物 |
|--------|----------|--------|
| **M0: 项目骨架** | 1 周 | monorepo + packages + 数据库 DDL + Docker Compose 基础设施 |
| **M1: 世界可运行** | 2 周 | World Tick + Character Tick + Action 10+ + 记忆检索 |
| **M2: 角色有生活** | 1 周 | 角色卡导入 + 小镇场景 + 作息 + 动态耗时 |
| **M3: 可外部交互** | 2 周 | QQ/飞书/Web 消息 + 主动分享 + MCP 4 个 Server |
| **M4: 可观测完整** | 1 周 | Trace/Metrics/Logs 三支柱 + Grafana 统一面板 |
| **M5: 前端可用** | 2 周 | Dashboard 6 页面 + 实时数据 + 管理入口 |

**总预计周期**：9 周（约 2 个月）

---

## 九、风险与依赖

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| pg_uuidv7 扩展未安装 | UUID v4 索引碎片化 | 应用层 `uuid6` 库兜底 |
| LLM 调用超时/失败 | Tick 阻塞 | 强制超时 + 重试 + 默认"等待"回退 |
| PgBouncer prepared statements | 与事务模式冲突 | `DB_PREPARED_STATEMENT_CACHE_SIZE=0` |
| MCP Server 不稳定 | 工具调用失败 | 超时 + fallback + 告警 |
| 角色 Tick 并发过多 | 资源耗尽 | 信号量限制 + 优先级调度 |

---

## 十、下一步行动（Phase 0）

1. **创建 monorepo 结构**（pnpm-workspace.yaml + packages 目录）
2. **初始化 backend**（`pyproject.toml` + `src/` 目录 + `alembic.ini`）
3. **初始化 frontend**（`package.json` + `vite.config.ts` + `oxlint.json`）
4. **编写数据库 DDL**（`alembic/versions/` 迁移脚本）
5. **创建 `.env.example`**（所有必填变量）
6. **编写 `docker-compose.infra.yml`**（postgres/redis/minio）

---

## 十一、相关文档

| 主题 | 文档 |
|------|------|
| 架构总览 | [architecture.md](architecture.md) |
| 开发指南 | [development-guide.md](development-guide.md) |
| 数据模型 | [data-model.md](data-model.md) |
| 部署 | [deployment.md](deployment.md) |