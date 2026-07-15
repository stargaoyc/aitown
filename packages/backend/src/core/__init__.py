"""Core 模块 - 世界引擎与角色引擎

模块结构（gap-analysis 2.2 重组）：
    core/world/     — 世界引擎 + 演化系统
    core/character/ — 角色 Tick 引擎

导出（向后兼容）：
    WorldEngine: World Tick 主循环引擎
    CharacterTickEngine: 角色 Tick 五阶段闭环引擎
"""

from src.core.character import CharacterTickEngine
from src.core.world import WorldEngine

__all__ = ["WorldEngine", "CharacterTickEngine"]
