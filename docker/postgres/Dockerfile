FROM pgvector/pgvector:pg17

# 安装 pg_uuidv7 扩展（时间有序 UUID v7）
RUN apt-get update && apt-get install -y --no-install-recommends \
        git build-essential postgresql-server-dev-17 && \
    git clone --depth 1 https://github.com/fboulnois/pg_uuidv7.git /tmp/pg_uuidv7 && \
    cd /tmp/pg_uuidv7 && make && make install && \
    rm -rf /tmp/pg_uuidv7 && \
    apt-get purge -y git build-essential postgresql-server-dev-17 && \
    apt-get autoremove -y && rm -rf /var/lib/apt/lists/*