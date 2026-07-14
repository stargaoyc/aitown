"""清理 Redis 中的世界引擎 leader 锁"""
import asyncio

import redis.asyncio as aioredis


async def main():
    r = aioredis.from_url("redis://localhost:6379/0")
    v = await r.get("world:leader_lock")
    print(f"Lock value: {v}")
    await r.delete("world:leader_lock")
    print("Lock cleared")
    await r.aclose()


if __name__ == "__main__":
    asyncio.run(main())
