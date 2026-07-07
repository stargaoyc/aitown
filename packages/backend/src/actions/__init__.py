"""Action 系统模块

导出 ActionRegistry 及所有内置 Action，并提供 register_all() 一次性注册全部内置 Action。

使用示例：
    from src.actions import ActionRegistry, register_all

    registry = ActionRegistry()
    register_all(registry)
    candidates = registry.get_candidates(state)
"""

from src.actions.base import (
    Action,
    ActionCategory,
    ActionResult,
    DecisionResult,
)
from src.actions.life import build_life_actions
from src.actions.move import build_move_action
from src.actions.registry import ActionRegistry
from src.actions.social import build_social_actions
from src.actions.work import build_work_actions

__all__ = [
    "Action",
    "ActionCategory",
    "ActionResult",
    "DecisionResult",
    "ActionRegistry",
    "register_all",
]


def register_all(registry: ActionRegistry) -> None:
    """向注册表注册所有内置 Action（移动 / 生活 / 工作 / 社交）"""
    registry.register(build_move_action())
    for action in build_life_actions():
        registry.register(action)
    for action in build_work_actions():
        registry.register(action)
    for action in build_social_actions():
        registry.register(action)
