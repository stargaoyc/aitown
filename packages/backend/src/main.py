"""AI Town Backend - FastAPI 入口

启动流程：
1. 初始化 Redis / LLM / Action Registry / Memory Services
2. 启动 World Engine（后台任务）
3. 启动 Character Tick Engine（后台任务）
4. 注册 API 路由
5. 监听 shutdown 信号，优雅停止

API 路由：
- /health - 健康检查
- /api/v1/characters - 角色管理
- /api/v1/world - 世界状态
- /api/v1/actions - Action 查询
- /api/v1/memories - 记忆查询
- /api/v1/admin - 管理接口（强制 Tick、快照回放等）
"""

import asyncio
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from structlog import get_logger

from src.actions import ActionRegistry, register_all
from src.config import settings
from src.core import WorldEngine
from src.db.repositories import (
    ActionRepository,
    CharacterRepository,
    MemoryRepository,
    SnapshotRepository,
)
from src.db.session import db
from src.llm import LLMClient, PromptTemplates
from src.memory import EpisodeService, ReflectionService, RetrievalService

# 尝试导入 CharacterTickEngine（可能尚未创建）
try:
    from src.core.character_tick import CharacterTickEngine

    CHARACTER_ENGINE_AVAILABLE = True
except ImportError:
    CharacterTickEngine = None  # type: ignore
    CHARACTER_ENGINE_AVAILABLE = False

logger = get_logger(__name__)

# === 全局实例 ===
redis: Redis | None = None
world_engine: WorldEngine | None = None
character_engine: CharacterTickEngine | None = None  # type: ignore
registry: ActionRegistry | None = None
llm: LLMClient | None = None
prompts: PromptTemplates | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理

    初始化顺序：
    1. Redis 连接
    2. LLM 客户端
    3. Action Registry
    4. World Engine
    5. Character Tick Engine（如果可用）
    """
    global redis, world_engine, character_engine, registry, llm, prompts

    logger.info("ai_town_backend_starting")

    # 1. 初始化 Redis
    try:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        # 测试连接
        await redis.ping()
        logger.info("redis_connected", url=settings.redis_url)
    except Exception as e:
        logger.error("redis_connection_failed", error=str(e), exc_info=True)
        raise

    # 2. 初始化 LLM 客户端
    try:
        llm = LLMClient()
        prompts = PromptTemplates()
        logger.info("llm_initialized", model=settings.model_chat)
    except Exception as e:
        logger.error("llm_initialization_failed", error=str(e), exc_info=True)
        raise

    # 3. 初始化 Action Registry
    try:
        registry = ActionRegistry()
        register_all(registry)
        logger.info("action_registry_initialized", count=len(registry.list_all()))
    except Exception as e:
        logger.error("action_registry_initialization_failed", error=str(e), exc_info=True)
        raise

    # 4. 启动 World Engine
    try:
        world_engine = WorldEngine(redis)
        await world_engine.start()
        logger.info("world_engine_started")
    except Exception as e:
        logger.error("world_engine_start_failed", error=str(e), exc_info=True)
        raise

    # 5. 启动 Character Tick Engine（如果模块可用）
    character_tick_task: asyncio.Task | None = None
    if CHARACTER_ENGINE_AVAILABLE and CharacterTickEngine is not None:
        try:
            character_engine = CharacterTickEngine(
                redis=redis,
                registry=registry,
                llm_client=llm,
                prompts=prompts,
            )
            # 启动后台任务：定期对所有活跃角色执行 Tick
            character_tick_task = asyncio.create_task(_character_tick_loop())
            logger.info("character_engine_started")
        except Exception as e:
            logger.error(
                "character_engine_start_failed",
                error=str(e),
                exc_info=True,
            )
            character_engine = None
    else:
        logger.warning(
            "character_tick_engine_not_available",
            message="CharacterTickEngine module not found, character tick loop disabled",
        )

    yield

    # === Shutdown ===
    logger.info("ai_town_backend_shutting_down")

    # 取消 Character Tick 循环
    if character_tick_task:
        character_tick_task.cancel()
        try:
            await character_tick_task
        except asyncio.CancelledError:
            pass

    # 停止 World Engine
    if world_engine:
        await world_engine.stop()
        logger.info("world_engine_stopped")

    # 关闭 Redis 连接
    if redis:
        await redis.close()
        logger.info("redis_connection_closed")


async def _character_tick_loop() -> None:
    """Character Tick 后台循环

    定期对所有活跃角色执行 Tick，推进角色状态
    """
    logger.info("character_tick_loop_started", interval=settings.character_tick_seconds)

    while True:
        try:
            await asyncio.sleep(settings.character_tick_seconds)

            if not character_engine or not redis:
                continue

            # 获取所有活跃角色
            async with db.session() as session:
                repo = CharacterRepository(session)
                characters = await repo.get_active_characters()

            if not characters:
                logger.debug("no_active_characters")
                continue

            logger.info("character_tick_batch_start", count=len(characters))

            # 对每个角色执行 Tick
            success_count = 0
            for char in characters:
                try:
                    await character_engine.tick_character(char.id)
                    success_count += 1
                except Exception as e:
                    logger.error(
                        "character_tick_failed",
                        character_id=str(char.id),
                        character_name=char.name,
                        error=str(e),
                        exc_info=True,
                    )

            logger.info(
                "character_tick_batch_complete",
                total=len(characters),
                success=success_count,
                failed=len(characters) - success_count,
            )

        except asyncio.CancelledError:
            logger.info("character_tick_loop_cancelled")
            raise
        except Exception as e:
            logger.error("character_tick_loop_error", error=str(e), exc_info=True)
            # 继续循环，不中断


# === FastAPI 应用实例 ===
app = FastAPI(
    title="AI Town Backend",
    description="二次元 AI 小镇陪伴智能体 - World Engine + LangGraph",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === API 路由 ===


@app.get("/health")
async def health():
    """健康检查

    返回服务状态、World Tick ID、Redis 连接状态
    """
    return {
        "status": "ok",
        "world_tick": world_engine.tick_id if world_engine else 0,
        "redis": "connected" if redis else "disconnected",
        "character_engine": "available" if character_engine else "unavailable",
    }


@app.get("/api/v1/characters")
async def list_characters(limit: int = 20, active_only: bool = False):
    """获取角色列表

    Args:
        limit: 返回数量限制（默认 20）
        active_only: 是否只返回活跃角色（默认 False）

    Returns:
        角色列表
    """
    async with db.session() as session:
        repo = CharacterRepository(session)
        if active_only:
            characters = await repo.get_active_characters()
        else:
            characters = await repo.list_all(limit)

    return {
        "data": [
            {
                "id": str(c.id),
                "name": c.name,
                "age": c.age,
                "occupation": c.occupation,
                "is_active": c.is_active,
            }
            for c in characters
        ],
        "total": len(characters),
    }


@app.get("/api/v1/characters/{character_id}")
async def get_character(character_id: str):
    """获取角色详情

    Args:
        character_id: 角色 UUID

    Returns:
        角色档案 + 实时状态
    """
    try:
        cid = UUID(character_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    async with db.session() as session:
        repo = CharacterRepository(session)
        result = await repo.get_character_with_state(cid)

    if not result:
        raise HTTPException(status_code=404, detail="Character not found")

    character, state = result

    return {
        "character": {
            "id": str(character.id),
            "name": character.name,
            "age": character.age,
            "occupation": character.occupation,
            "personality": character.personality,
            "traits": character.traits,
            "backstory": character.backstory,
            "is_active": character.is_active,
        },
        "state": {
            "location": state.location,
            "stamina": state.stamina,
            "satiety": state.satiety,
            "mood": state.mood,
            "money": state.money,
        },
    }


@app.get("/api/v1/world")
async def get_world_state():
    """获取世界状态

    Returns:
        世界当前状态（从 Redis 读取）
    """
    if not redis:
        raise HTTPException(status_code=503, detail="Redis not connected")

    state = await redis.hgetall("world:state")
    return {"data": dict(state)}


@app.get("/api/v1/world/snapshot/{tick_id}")
async def get_world_snapshot(tick_id: int):
    """获取历史快照

    Args:
        tick_id: Tick ID

    Returns:
        世界历史快照
    """
    async with db.session() as session:
        repo = SnapshotRepository(session)
        snapshot = await repo.get_by_tick(tick_id)

    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    return {
        "tick_id": snapshot.tick_id,
        "world_time": snapshot.world_time.isoformat() if snapshot.world_time else None,
        "weather": snapshot.weather,
        "locations": snapshot.locations,
        "resources": snapshot.resources,
        "active_events": snapshot.active_events,
        "created_at": snapshot.created_at.isoformat(),
    }


@app.get("/api/v1/actions")
async def list_actions():
    """获取所有 Action

    Returns:
        所有已注册的 Action 列表
    """
    if not registry:
        raise HTTPException(status_code=503, detail="Action registry not initialized")

    actions = registry.list_all()
    return {
        "data": [
            {
                "id": a.id,
                "name": a.name,
                "description": a.description,
                "category": a.category.value if hasattr(a.category, "value") else str(a.category),
                "duration_minutes": a.duration_minutes,
                "energy_cost": a.energy_cost,
            }
            for a in actions
        ],
        "total": len(actions),
    }


@app.get("/api/v1/actions/{action_id}")
async def get_action(action_id: str):
    """获取单个 Action 详情

    Args:
        action_id: Action ID

    Returns:
        Action 详情
    """
    if not registry:
        raise HTTPException(status_code=503, detail="Action registry not initialized")

    action = registry.get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    return {
        "id": action.id,
        "name": action.name,
        "description": action.description,
        "category": action.category.value if hasattr(action.category, "value") else str(action.category),
        "duration_minutes": action.duration_minutes,
        "energy_cost": action.energy_cost,
        "preconditions": getattr(action, "preconditions", {}),
        "effects": getattr(action, "effects", {}),
    }


@app.get("/api/v1/memories/{character_id}")
async def get_memories(character_id: str, limit: int = 20):
    """获取角色记忆

    Args:
        character_id: 角色 UUID
        limit: 返回数量限制（默认 20）

    Returns:
        角色最近的记忆片段
    """
    try:
        cid = UUID(character_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    async with db.session() as session:
        repo = MemoryRepository(session)
        episodes = await repo.recent(cid, limit)

    return {
        "data": [
            {
                "id": str(e.id),
                "content": e.content,
                "timestamp": e.timestamp.isoformat(),
                "importance": e.importance,
                "is_reflected": e.is_reflected,
            }
            for e in episodes
        ],
        "total": len(episodes),
    }


@app.post("/api/v1/admin/tick")
async def force_tick(character_id: str | None = None):
    """强制触发 Tick（管理接口）

    Args:
        character_id: 可选，指定角色 ID。如果为空则对所有活跃角色执行 Tick

    Returns:
        执行结果
    """
    if not character_engine:
        raise HTTPException(
            status_code=503,
            detail="Character engine not initialized or unavailable",
        )

    if character_id:
        # 单个角色 Tick
        try:
            cid = UUID(character_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid UUID format")

        await character_engine.tick_character(cid)
        return {"message": f"Tick executed for character {character_id}", "count": 1}

    # 全量 Tick
    async with db.session() as session:
        repo = CharacterRepository(session)
        characters = await repo.get_active_characters()

    if not characters:
        return {"message": "No active characters found", "count": 0}

    success_count = 0
    for char in characters:
        try:
            await character_engine.tick_character(char.id)
            success_count += 1
        except Exception as e:
            logger.error(
                "force_tick_failed",
                character_id=str(char.id),
                error=str(e),
                exc_info=True,
            )

    return {
        "message": f"Tick executed for {success_count}/{len(characters)} characters",
        "total": len(characters),
        "success": success_count,
        "failed": len(characters) - success_count,
    }


@app.post("/api/v1/admin/world/tick")
async def force_world_tick():
    """强制触发 World Tick（管理接口）

    Returns:
        执行结果
    """
    if not world_engine:
        raise HTTPException(status_code=503, detail="World engine not initialized")

    try:
        await world_engine._execute_tick()
        return {
            "message": "World tick executed",
            "tick_id": world_engine.tick_id,
        }
    except Exception as e:
        logger.error("force_world_tick_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"World tick failed: {str(e)}")


@app.get("/api/v1/admin/status")
async def get_admin_status():
    """获取系统状态（管理接口）

    Returns:
        各组件运行状态
    """
    return {
        "redis": "connected" if redis else "disconnected",
        "world_engine": {
            "running": world_engine is not None,
            "tick_id": world_engine.tick_id if world_engine else 0,
            "is_leader": world_engine.is_leader if world_engine else False,
        },
        "character_engine": {
            "available": character_engine is not None,
            "tick_interval": settings.character_tick_seconds,
        },
        "action_registry": {
            "initialized": registry is not None,
            "action_count": len(registry.list_all()) if registry else 0,
        },
        "llm": {
            "initialized": llm is not None,
            "model": settings.model_chat,
        },
    }