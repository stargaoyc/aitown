# weather MCP Server

MCP Server，集成 [OpenWeatherMap API](https://openweathermap.org/api)，为 AI Town 角色提供实时天气查询与多日预报能力。

> ⚠️ 本包为社区插件骨架，需配置有效的 OpenWeatherMap API Key 才能完整运行。

## 提供的工具

| 工具 | 说明 |
| --- | --- |
| `get_current_weather(city, units="metric")` | 查询城市当前天气 |
| `get_forecast(city, days=5, units="metric")` | 查询城市天气预报（5 天 / 3 小时间隔） |
| `get_weather_by_coords(lat, lon, units="metric")` | 按经纬度查询当前天气 |

`get_current_weather` / `get_weather_by_coords` 返回 `{"success", "city", "temperature", "feels_like", "humidity", "wind_speed", "description", "icon", "units", "error"}`。

`get_forecast` 返回 `{"success", "city", "forecasts": [{"datetime", "temperature", "description"}], "count", "error"}`。

`units` 取值：`metric`（摄氏）、`imperial`（华氏）、`standard`（开尔文）。

## 前置条件

- Python ≥ 3.13
- 一个有效的 OpenWeatherMap API Key（在 https://home.openweathermap.org/api_keys 申请）

## 配置

通过环境变量配置 API Key：

```bash
# Linux / macOS
export OPENWEATHER_API_KEY=your_api_key

# Windows PowerShell
$env:OPENWEATHER_API_KEY = "your_api_key"
```

> 若未配置 API Key，工具调用不会崩溃，而是返回 `{"success": false, "error": "API key not configured", ...}`。

## 运行

```bash
cd packages/mcp-servers/weather
uv run python server.py
```

或以 stdio 模式接入 MCP Client（如 Claude Desktop）。

## 依赖

见 `pyproject.toml`：`mcp`、`structlog`、`httpx`、`pydantic`。
