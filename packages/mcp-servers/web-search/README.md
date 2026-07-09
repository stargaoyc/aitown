# web-search MCP Server

MCP Server，集成 [Tavily Search API](https://tavily.com/)，为 AI Town 角色提供网络搜索与新闻搜索能力。

> ⚠️ 本包为社区插件骨架，需配置有效的 Tavily API Key 才能完整运行。

## 提供的工具

| 工具 | 说明 |
| --- | --- |
| `search(query, max_results=5)` | 通用网络搜索（topic=general） |
| `search_news(query, max_results=5)` | 新闻搜索（topic=news） |

两个工具均返回 `{"success", "results": [{"title", "url", "content", "score"}], "total", "error"}`。

## 前置条件

- Python ≥ 3.13
- 一个有效的 Tavily API Key（在 https://tavily.com/ 注册获取）

## 配置

通过环境变量配置 API Key：

```bash
# Linux / macOS
export TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Windows PowerShell
$env:TAVILY_API_KEY = "tvly-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

> 若未配置 API Key，工具调用不会崩溃，而是返回 `{"success": false, "error": "API key not configured", ...}`。

## 运行

```bash
cd packages/mcp-servers/web-search
uv run python server.py
```

或以 stdio 模式接入 MCP Client（如 Claude Desktop）。

## 依赖

见 `pyproject.toml`：`mcp`、`structlog`、`httpx`、`pydantic`。
