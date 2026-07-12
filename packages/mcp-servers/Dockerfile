# packages/mcp-servers/Dockerfile
# 通用 MCP Server 镜像 - 适用于所有自研 MCP Server
# 构建参数 SERVER 指定要构建的 MCP Server 名称
# 用法: docker build --build-arg SERVER=weather -t aitown/mcp-weather packages/mcp-servers/

FROM python:3.13-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# SERVER 构建参数指定要构建的 MCP Server（如 weather, web-search, shop-simulator 等）
ARG SERVER
ENV MCP_SERVER_NAME=$SERVER

# 复制对应 Server 的依赖文件
COPY ${SERVER}/pyproject.toml ${SERVER}/uv.lock ./

RUN uv sync --frozen --no-dev

# ===== 运行阶段 =====
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 mcp

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --chown=mcp:mcp ${MCP_SERVER_NAME}/ ./

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER mcp

CMD ["python", "server.py"]
