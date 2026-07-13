"""Core 模块 - 世界引擎与演化系统

导出：
    WorldEngine: World Tick 主循环引擎
    CharacterTickEngine: 角色 Tick 五阶段闭环引擎
"""

from src.core.character_tick import CharacterTickEngine
from src.core.world_engine import WorldEngine

__all__ = ["WorldEngine", "CharacterTickEngine"]
