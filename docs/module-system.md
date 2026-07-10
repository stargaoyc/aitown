# 模块与 MCP 系统设计

> 模块管理器是系统的可插拔能力中枢，负责所有功能模块的注册、开关控制和生命周期管理。MCP 工具调用层提供标准化的外部工具接口。

---

## 一、模块管理器

### 1.1 设计目标

| 目标 | 说明 |
|------|------|
| 可插拔 | 模块可动态启用/禁用/卸载，无需重启 |
| 依赖治理 | 模块间依赖关系明确，禁用前检查反向依赖 |
| 健康检查 | 模块状态可观测，异常自动降级 |
| 三态开关 | 配置文件、运行时 API、Agent 自适应 |

### 1.2 模块类型

| 模块类型 | 说明 | 示例 |
|----------|------|------|
| `MCP` | 通过 MCP 协议调用的外部服务 | 代码执行、网页搜索、天气查询 |
| `local` | 内联函数，毫秒级响应 | 情感分析、记忆检索、本地工具 |
| `skill` | 多步骤复杂工作流 | 数据分析报告生成、多轮调研 |

### 1.3 模块生命周期

```text
REGISTERED(已注册) → ENABLED(已启用) → 运行中
       ↓                  ↓
    DISABLED(已禁用)    ERROR(错误)
```

| 阶段 | 动作 |
|------|------|
| 注册 | 系统启动时扫描并注册所有可用模块 |
| 启用 | 检查依赖 → 健康检查 → 加载配置 → 标记可用 |
| 调用 | Agent 决策后通过统一接口调用 |
| 禁用 | 检查反向依赖 → 清理资源 → 标记不可用 |
| 卸载 | 完全移除模块（热插拔） |

### 1.4 开关控制方式

| 方式 | 说明 | 适用场景 |
|------|------|----------|
| 配置文件 | `config.yaml` 中 `enabled: true/false` | 运维管理，重启生效 |
| 运行时 API | `POST /api/v1/modules/{name}/enable` | 灰度测试、紧急禁用 |
| Agent 自适应 | LLM 根据上下文决策是否使用 | 智能降级、自主选择 |

### 1.5 模块与 Action 联动

```text
模块启用 → 模块管理器注册工具 → ActionRegistry 注册对应 TOOL Action
        ↓                          ↓
    模块禁用 → 模块管理器注销工具 → ActionRegistry 注销对应 Action
```

模块禁用时，依赖该模块的 Action 自动从候选列表移除，LLM 决策不再可见。

### 1.6 模块配置（PG `module_configs` 表）

| 字段 | 说明 |
|------|------|
| `name` | 模块唯一名 |
| `type` | `mcp` / `local` / `skill` |
| `enabled` | 是否启用 |
| `config` | JSONB，模块特定配置 |
| `dependencies` | 依赖的模块名列表 |
| `mcp_server_url` | MCP 类型模块的 Server 地址 |
| `health_check_status` | `healthy` / `unhealthy` / `unknown` |
| `last_check_at` | 最近健康检查时间 |

详细 DDL 见 [数据模型设计](data-model.md#module_configs)。

---

## 二、MCP 工具调用层

### 2.1 MCP 架构

```text
┌─────────────────────────────────────────────────────────────────┐
│                   世界引擎 (MCP Client)                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ 工具发现     │  │ 工具调用    │  │ 结果处理与重试          │ │
│  │ (ListTools) │  │ (CallTool) │  │ (超时/降级/熔断)        │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
└─────────────────────────────┬───────────────────────────────────┘
                              │ JSON-RPC 2.0 / SSE
┌─────────────────────────────▼───────────────────────────────────┐
│                    MCP Server Cluster                            │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐           │
│  │ 代码执行     │ │ 网页搜索     │ │ 天气查询     │           │
│  │ Server       │ │ Server       │ │ Server       │           │
│  └──────────────┘ └──────────────┘ └──────────────┘           │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐           │
│  │ 商店模拟     │ │ 知识库查询   │ │ 第三方API    │           │
│  │ Server       │ │ Server       │ │ Server       │           │
│  └──────────────┘ └──────────────┘ └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 通信协议

| 项 | 选型 |
|----|------|
| 协议 | JSON-RPC 2.0 |
| 传输 | SSE（Server-Sent Events）/ stdio / WebSocket |
| SDK | 官方 `mcp` Python SDK |

### 2.3 MCP Server 注册工具示例

```python
# mcp-servers/code-executor/server.py
from mcp.server import Server, tool

server = Server("code-executor")

@server.tool()
async def run_python(code: str) -> dict:
    """在沙箱中执行 Python 代码"""
    # 实际执行逻辑（容器化隔离）
    result = await sandbox.run(code)
    return {"output": result.stdout, "error": result.stderr}

@server.tool()
async def list_files(path: str) -> dict:
    """列出指定路径下的文件"""
    ...
```

### 2.4 MCP Client 调用示例

```python
# tools/mcp_client.py
from mcp import ClientSession

async def call_mcp_tool(server_url: str, tool_name: str, params: dict):
    async with mcp.ClientSession(server_url) as session:
        # 动态发现工具
        tools = await session.list_tools()
        # 调用工具
        result = await session.call_tool(tool_name, params)
        return result
```

### 2.5 容错策略

| 策略 | 说明 |
|------|------|
| 超时 | 单次调用默认 30s，可按工具配置 |
| 重试 | 可重试错误重试 2 次，指数退避 |
| 熔断 | 5 分钟内错误率 > 30% 触发熔断，10 分钟后探活 |
| 降级 | 工具不可用时，LLM 决策可见"工具暂不可用"，引导选择其他 Action |
| 健康检查 | 模块管理器每 60s 调用 `health` 端点，更新 `health_check_status` |

---

## 三、统一工具调用接口

### 3.1 工具抽象

```python
# tools/base.py
from abc import ABC, abstractmethod

class Tool(ABC):
    name: str
    description: str
    parameters: dict          # JSON Schema

    @abstractmethod
    async def call(self, **params) -> dict: ...


class LocalTool(Tool):
    """内联函数工具"""
    pass


class MCPTool(Tool):
    """MCP 远程工具"""
    server_url: str

    async def call(self, **params) -> dict:
        return await call_mcp_tool(self.server_url, self.name, params)


class SkillTool(Tool):
    """多步骤工作流工具"""
    steps: list[callable]

    async def call(self, **params) -> dict:
        result = params
        for step in self.steps:
            result = await step(result)
        return result
```

### 3.2 工具注册表

```python
# tools/registry.py
class ToolRegistry:
    def register(self, tool: Tool) -> None: ...
    def unregister(self, name: str) -> None: ...
    def get(self, name: str) -> Tool: ...
    def list_all(self) -> list[Tool]: ...
    def to_openai_functions(self) -> list[dict]:
        """转换为 OpenAI function-calling 格式"""
        ...
```

### 3.3 与 LangGraph 集成

```python
# agents/character_agent.py
from langgraph.prebuilt import ToolNode

# 将所有已启用工具绑定到 LLM
tools = tool_registry.list_all()
llm_with_tools = llm.bind_tools(tools)
tool_node = ToolNode(tools)
```

---

## 四、内置 MCP Server 清单与开发分工

### 4.1 自研 vs 社区现成划分

并非所有 MCP Server 都需自研。社区已有大量现成 MCP Server，可直接复用；只有业务专属或需深度定制的才自研。

| Server | 来源 | 理由 |
|--------|------|------|
| `code-executor` | **自研** | 需沙箱隔离、自定义资源限制、与小镇角色上下文绑定 |
| `web-search` | **社区** | 可直接用 Tavily MCP / Brave Search MCP，仅需配置 API Key |
| `weather` | **社区** | 可用 OpenWeatherMap MCP / 开源天气 MCP |
| `shop-simulator` | **自研** | 小镇专属业务逻辑（商品/库存/价格/角色消费），无现成方案 |
| `knowledge-base` | **自研/社区** | 取决于知识库类型：通用文档可用社区 RAG MCP；小镇设定库需自研 |
| `image-generator` | **社区** | 可直接用 Stable Diffusion / DALL-E MCP |
| `time-tool` | **社区** | 时间/时区/日历查询有现成 MCP |
| `character-social` | **自研** | 小镇社交系统专属（送礼/约会/冲突），强业务绑定 |

### 4.2 自研 MCP Server 清单

已自研的 Server 集中在 `packages/mcp-servers/`：

| Server | 端口 | 工具 | 说明 | 状态 |
|--------|------|------|------|------|
| `code-executor` | 8001 | `execute_python`, `list_allowed_modules` | 沙箱代码执行（subprocess 隔离 + 模块白名单） | ✅ |
| `shop-simulator` | 8004 | `list_items`, `get_item_details`, `buy_item`, `sell_item`, `get_shop_categories` | 商店模拟（24 件商品 + 购买/出售事务） | ✅ |
| `character-social` | 8006 | `give_gift`, `invite_date`, `resolve_conflict` | 角色社交（送礼/约会/冲突解决） | ✅ |
| `knowledge-base` | 8005 | `query_kb`, `list_categories` | 小镇设定库（世界规则/角色/场景/行动/记忆系统） | ✅ |

### 4.3 社区 MCP Server 接入

社区 MCP Server 无需自研，仅需在 `config.yaml` 注册并配置 API Key：

```yaml
# config.yaml
mcp:
  community_servers:
    - name: web-search
      package: @mcp/tavily-search          # 社区包名
      config:
        api_key: ${TAVILY_API_KEY}
    - name: weather
      package: @mcp/openweathermap
      config:
        api_key: ${OPENWEATHER_API_KEY}
    - name: image-generator
      package: @mcp/stable-diffusion
      config:
        endpoint: ${SD_ENDPOINT}
```

启动时由模块管理器拉起社区 MCP Server 进程，注册到 `module_configs` 表。

### 4.4 各 Server 独立部署

无论自研还是社区，各 MCP Server 独立部署（多进程/Docker），通过 `MCP_*_SERVER` 环境变量配置地址。

---

## 五、管理 API

已实现的管理 API 端点：

| 端点 | 方法 | 说明 | 状态 |
|------|------|------|------|
| `/api/v1/modules` | GET | 模块列表（含运行状态） | ✅ |
| `/api/v1/mcp/servers` | GET | MCP Server 列表（含工具清单） | ✅ |
| `/api/v1/mcp/servers/{name}` | GET | 单个 MCP Server 详情 | ✅ |
| `/api/v1/mcp/tools` | GET | 所有可用工具列表 | ✅ |

详细请求/响应见 [API设计文档](api-spec.md)。

---

## 六、可观测埋点

| Span | 关键属性 |
|------|----------|
| `mcp.tool.call` | `tool_name`, `server_url`, `latency_ms`, `success` |
| `module.enable` | `module_name`, `dependencies_checked` |
| `module.disable` | `module_name`, `reverse_deps_checked` |
| `module.health_check` | `module_name`, `status` |

---

## 七、相关文档

| 主题 | 文档 |
|------|------|
| Action 系统与 TOOL 类 Action | [action-system.md](action-system.md) |
| 数据模型（module_configs） | [data-model.md](data-model.md) |
| API 设计 | [api-spec.md](api-spec.md) |
| 配置参考 | [config-reference.md](config-reference.md) |
