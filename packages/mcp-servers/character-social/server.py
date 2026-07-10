"""MCP Character Social Server - 角色社交系统

为 AI Town 角色提供"送礼 / 约会 / 冲突解决"的工具能力。
角色通过 LLM 决策调用此 MCP Server 完成社交交互。

设计：
- 无状态：每次调用由 caller 传入角色当前 relation_strength / inventory / mood
- 社交规则内置（关系等级、礼物价值、约会场景白名单）
- 校验事务可行性，返回 deltas 由 caller 应用到 character_states

返回结构（以 give_gift 为例）：
    {
        "success": bool,
        "action": "give_gift",
        "character_id": str,
        "target_id": str,
        "item_id": str,
        "relation_strength_delta": int,   # 好感度变化
        "inventory_delta": dict,          # {item_id: -1}
        "new_relation_strength": int,
        "error": str | None,
    }

caller（Action executor）拿到结果后：
    new_relation = current_relation + relation_strength_delta
    new_inventory = merge(current_inventory, inventory_delta)
"""
from __future__ import annotations

import random
from typing import Any

import structlog
from fastmcp import FastMCP  # FastMCP 2.0+ 导入方式
from pydantic import BaseModel, Field

logger = structlog.get_logger()

mcp = FastMCP("character-social")


# ============================================================
# 礼物目录数据模型
# ============================================================

class GiftItem(BaseModel):
    """可赠送礼物定义"""
    item_id: str = Field(description="物品唯一标识")
    name: str = Field(description="物品显示名")
    value: int = Field(ge=0, description="物品价值（用于关系校验与好感度计算）")
    description: str = Field(default="", description="礼物描述")


# 默认礼物目录（覆盖各价值档位，便于不同关系等级使用）
# 生产环境可通过配置文件覆盖
DEFAULT_GIFT_CATALOG: list[GiftItem] = [
    # 低价值礼物（适合 stranger）
    GiftItem(item_id="greeting_card", name="贺卡", value=10,
             description="手写贺卡，表达心意"),
    GiftItem(item_id="flower", name="花束", value=25,
             description="一束鲜花，简单温馨"),
    GiftItem(item_id="snack", name="零食", value=15,
             description="一袋零食，轻松随意"),
    # 中等价值礼物（适合 acquaintance 以上）
    GiftItem(item_id="chocolate", name="巧克力", value=35,
             description="盒装巧克力，甜蜜之选"),
    GiftItem(item_id="book", name="书籍", value=45,
             description="一本好书，知识分享"),
    GiftItem(item_id="plush_toy", name="毛绒玩具", value=60,
             description="毛绒玩具，可爱暖心"),
    GiftItem(item_id="cake", name="蛋糕", value=50,
             description="精致蛋糕，分享甜蜜"),
    # 高价值礼物（适合 friend 以上）
    GiftItem(item_id="gift_box", name="礼物盒", value=100,
             description="精美礼物盒，郑重其事"),
    GiftItem(item_id="jewelry", name="首饰", value=150,
             description="精致首饰，珍贵心意"),
    GiftItem(item_id="watch", name="手表", value=120,
             description="一块手表，长久陪伴"),
]


# ============================================================
# 社交规则常量
# ============================================================

# 关系强度等级定义：(等级名, 好感度乘数, 礼物价值上限)
# 价值上限为 None 表示无限制；数值表示礼物价值必须 < 该值
RELATION_TIERS: list[tuple[str, int, int, float, int | None]] = [
    # (等级名, 下界, 上界, 好感度乘数, 礼物价值上限)
    ("stranger", 0, 20, 0.5, 30),
    ("acquaintance", 21, 40, 1.0, 80),
    ("friend", 41, 60, 1.2, None),
    ("close_friend", 61, 80, 1.5, None),
    ("best_friend", 81, 100, 2.0, None),
]

# 约会场景白名单
DATE_SCENES: set[str] = {"cafe", "park", "cinema", "restaurant", "beach"}

# 情绪修正值（约会成功率）
MOOD_MODIFIERS: dict[str, float] = {
    "happy": 0.1,
    "excited": 0.1,
    "sad": -0.2,
    "angry": -0.2,
    "calm": 0.0,
}

# 约会关系强度门槛
DATE_RELATION_THRESHOLD = 40

# 约会成功/失败的好感度变化
DATE_SUCCESS_DELTA = 5
DATE_FAILURE_DELTA = -2

# 约会成功后情绪变化
DATE_SUCCESS_MOOD = "happy"

# 冲突修复基准值（恢复率乘以此值得到 delta）
BASE_CONFLICT_RECOVERY = 50

# 冲突类型定义：(恢复率, 是否需要高关系强度)
CONFLICT_TYPES: dict[str, tuple[float, int | None]] = {
    # (基础恢复率, 尝试所需最低关系强度；None 表示无门槛)
    "argument": (0.8, None),          # 争吵：基础恢复 80%
    "misunderstanding": (0.9, None),  # 误会：基础恢复 90%
    "betrayal": (0.2, 60),            # 背叛：基础恢复 20%，需要关系强度 >= 60
}

# 关系强度 bonus：每点关系强度提供的额外恢复率
CONFLICT_RELATION_BONUS_RATE = 0.001

# 关系强度范围
RELATION_MIN = 0
RELATION_MAX = 100


# ============================================================
# 辅助函数
# ============================================================

def _get_gift_catalog_dict() -> dict[str, GiftItem]:
    """获取礼物 ID → GiftItem 映射"""
    return {item.item_id: item for item in DEFAULT_GIFT_CATALOG}


def _get_relation_tier(relation_strength: int) -> tuple[str, float, int | None]:
    """根据关系强度返回 (等级名, 好感度乘数, 礼物价值上限)

    - stranger (0-20): ×0.5, 价值 < 30
    - acquaintance (21-40): ×1.0, 价值 < 80
    - friend (41-60): ×1.2, 无限制
    - close_friend (61-80): ×1.5, 无限制
    - best_friend (81-100): ×2.0, 无限制
    """
    for tier_name, low, high, multiplier, max_value in RELATION_TIERS:
        if low <= relation_strength <= high:
            return (tier_name, multiplier, max_value)
    # 超出范围按最近等级处理
    if relation_strength < RELATION_MIN:
        return ("stranger", 0.5, 30)
    return ("best_friend", 2.0, None)


def _clamp_relation(value: int) -> int:
    """将关系强度限制在 [0, 100]"""
    return max(RELATION_MIN, min(RELATION_MAX, value))


def _clamp(value: float, low: float, high: float) -> float:
    """将浮点数限制在 [low, high]"""
    return max(low, min(high, value))


# ============================================================
# MCP Tools
# ============================================================

@mcp.tool()
async def give_gift(
    character_id: str,
    target_id: str,
    item_id: str,
    current_relation_strength: int,
    current_inventory: dict[str, int] | None = None,
) -> dict:
    """模拟角色给另一个角色送礼

    校验：物品在库存中、关系强度允许该价值礼物（stranger 不能送贵重礼物）
    根据物品价值和关系强度计算好感度增量，返回 deltas 由 caller 应用。

    关系强度规则：
    - stranger (0-20): 只能送小礼物（价值<30），好感度增量 ×0.5
    - acquaintance (21-40): 可送中等礼物（价值<80），好感度增量 ×1.0
    - friend (41-60): 可送任意礼物，好感度增量 ×1.2
    - close_friend (61-80): 好感度增量 ×1.5
    - best_friend (81-100): 好感度增量 ×2.0

    好感度计算：base_increase = item_value * 0.3 * relation_multiplier

    Args:
        character_id: 送礼角色 ID
        target_id: 收礼角色 ID
        item_id: 礼物物品 ID
        current_relation_strength: 当前关系强度（caller 从 character_states 传入）
        current_inventory: 角色当前库存（caller 从 character_states.inventory 传入）

    Returns:
        {
            "success": bool,
            "action": "give_gift",
            "character_id": str,
            "target_id": str,
            "item_id": str,
            "relation_strength_delta": int,
            "inventory_delta": dict,
            "new_relation_strength": int,
            "error": str | None,
        }
    """
    current_inventory = current_inventory or {}

    # 校验角色 ID
    if not character_id or not target_id:
        return _gift_error_result(
            character_id, target_id, item_id,
            current_relation_strength,
            "character_id and target_id are required",
        )
    if character_id == target_id:
        return _gift_error_result(
            character_id, target_id, item_id,
            current_relation_strength,
            "Cannot give gift to self",
        )

    # 校验礼物存在
    catalog = _get_gift_catalog_dict()
    gift = catalog.get(item_id)
    if gift is None:
        return _gift_error_result(
            character_id, target_id, item_id,
            current_relation_strength,
            f"Gift item not found in catalog: {item_id}",
        )

    # 校验库存
    have_quantity = current_inventory.get(item_id, 0)
    if have_quantity < 1:
        return _gift_error_result(
            character_id, target_id, item_id,
            current_relation_strength,
            f"Item not in inventory: {item_id} (have {have_quantity})",
        )

    # 校验关系强度范围
    if current_relation_strength < RELATION_MIN or current_relation_strength > RELATION_MAX:
        return _gift_error_result(
            character_id, target_id, item_id,
            current_relation_strength,
            f"relation_strength must be in [{RELATION_MIN}, {RELATION_MAX}]",
        )

    # 获取关系等级
    tier_name, multiplier, max_value = _get_relation_tier(current_relation_strength)

    # 校验礼物价值是否在该关系等级允许范围内
    if max_value is not None and gift.value >= max_value:
        return _gift_error_result(
            character_id, target_id, item_id,
            current_relation_strength,
            f"Gift too valuable for tier '{tier_name}': "
            f"item value {gift.value} >= limit {max_value}",
        )

    # 计算好感度增量
    base_increase = gift.value * 0.3 * multiplier
    relation_strength_delta = int(base_increase)
    new_relation_strength = _clamp_relation(current_relation_strength + relation_strength_delta)

    # 库存变化（送出一个）
    inventory_delta = {item_id: -1}

    logger.info(
        "give_gift_validated",
        character_id=character_id,
        target_id=target_id,
        item_id=item_id,
        item_value=gift.value,
        tier=tier_name,
        multiplier=multiplier,
        relation_strength_delta=relation_strength_delta,
        new_relation_strength=new_relation_strength,
    )

    return {
        "success": True,
        "action": "give_gift",
        "character_id": character_id,
        "target_id": target_id,
        "item_id": item_id,
        "relation_strength_delta": relation_strength_delta,
        "inventory_delta": inventory_delta,
        "new_relation_strength": new_relation_strength,
        "error": None,
    }


@mcp.tool()
async def invite_date(
    character_id: str,
    target_id: str,
    scene_id: str,
    current_relation_strength: int,
    current_mood: str,
) -> dict:
    """模拟角色邀请另一个角色约会

    校验：关系强度 >= 40（friend 以上）、目标场景适合约会
    根据当前情绪和关系强度计算成功率，返回是否成功及好感度增量。

    约会场景白名单：cafe, park, cinema, restaurant, beach

    成功率计算：
    - base_success_rate = 0.3 + (relation_strength - 40) * 0.01
    - mood 修正：happy/excited +0.1, sad/angry -0.2, calm 0
    - 最终成功率 clamp 到 [0.1, 0.95]

    成功：relation_strength_delta = +5，mood 变为 happy
    失败：relation_strength_delta = -2

    Args:
        character_id: 邀请方角色 ID
        target_id: 被邀请方角色 ID
        scene_id: 约会场景 ID
        current_relation_strength: 当前关系强度
        current_mood: 当前情绪（happy/excited/sad/angry/calm）

    Returns:
        {
            "success": bool,
            "action": "invite_date",
            "character_id": str,
            "target_id": str,
            "scene_id": str,
            "accepted": bool,
            "relation_strength_delta": int,
            "mood_delta": str | None,
            "error": str | None,
        }
    """
    # 校验角色 ID
    if not character_id or not target_id:
        return _date_error_result(
            character_id, target_id, scene_id,
            "character_id and target_id are required",
        )
    if character_id == target_id:
        return _date_error_result(
            character_id, target_id, scene_id,
            "Cannot invite self to a date",
        )

    # 校验关系强度
    if current_relation_strength < DATE_RELATION_THRESHOLD:
        return _date_error_result(
            character_id, target_id, scene_id,
            f"Relation strength too low: have {current_relation_strength}, "
            f"need >= {DATE_RELATION_THRESHOLD}",
        )

    # 校验关系强度范围
    if current_relation_strength > RELATION_MAX:
        return _date_error_result(
            character_id, target_id, scene_id,
            f"relation_strength exceeds max ({RELATION_MAX})",
        )

    # 校验场景
    if scene_id not in DATE_SCENES:
        return _date_error_result(
            character_id, target_id, scene_id,
            f"Scene not suitable for date: {scene_id}. "
            f"Allowed: {sorted(DATE_SCENES)}",
        )

    # 计算基础成功率
    base_success_rate = 0.3 + (current_relation_strength - DATE_RELATION_THRESHOLD) * 0.01

    # 情绪修正（未知情绪默认 0）
    mood_modifier = MOOD_MODIFIERS.get(current_mood, 0.0)

    # 最终成功率 clamp 到 [0.1, 0.95]
    final_success_rate = _clamp(base_success_rate + mood_modifier, 0.1, 0.95)

    # 随机判定是否接受
    accepted = random.random() < final_success_rate

    if accepted:
        relation_strength_delta = DATE_SUCCESS_DELTA
        mood_delta = DATE_SUCCESS_MOOD
    else:
        relation_strength_delta = DATE_FAILURE_DELTA
        mood_delta = None

    logger.info(
        "invite_date_resolved",
        character_id=character_id,
        target_id=target_id,
        scene_id=scene_id,
        current_mood=current_mood,
        base_success_rate=base_success_rate,
        mood_modifier=mood_modifier,
        final_success_rate=final_success_rate,
        accepted=accepted,
        relation_strength_delta=relation_strength_delta,
    )

    return {
        "success": True,
        "action": "invite_date",
        "character_id": character_id,
        "target_id": target_id,
        "scene_id": scene_id,
        "accepted": accepted,
        "relation_strength_delta": relation_strength_delta,
        "mood_delta": mood_delta,
        "error": None,
    }


@mcp.tool()
async def resolve_conflict(
    character_id: str,
    target_id: str,
    conflict_type: str,
    current_relation_strength: int,
) -> dict:
    """模拟角色解决与另一个角色的冲突

    冲突类型：argument（争吵）, misunderstanding（误会）, betrayal（背叛）
    根据冲突类型和关系强度计算解决效果。

    - argument: 基础恢复 80%，关系强度 bonus
    - misunderstanding: 基础恢复 90%
    - betrayal: 基础恢复 20%，需要关系强度 >= 60 才能尝试

    恢复量 = BASE_CONFLICT_RECOVERY × (恢复率 + 关系强度 bonus)
    关系强度 bonus = current_relation_strength × 0.001（每点 +0.1%）

    Args:
        character_id: 冲突方角色 ID
        target_id: 对方角色 ID
        conflict_type: 冲突类型（argument/misunderstanding/betrayal）
        current_relation_strength: 当前关系强度

    Returns:
        {
            "success": bool,
            "action": "resolve_conflict",
            "character_id": str,
            "target_id": str,
            "conflict_type": str,
            "resolved": bool,
            "relation_strength_delta": int,
            "new_relation_strength": int,
            "error": str | None,
        }
    """
    # 校验角色 ID
    if not character_id or not target_id:
        return _conflict_error_result(
            character_id, target_id, conflict_type,
            current_relation_strength,
            "character_id and target_id are required",
        )
    if character_id == target_id:
        return _conflict_error_result(
            character_id, target_id, conflict_type,
            current_relation_strength,
            "Cannot resolve conflict with self",
        )

    # 校验冲突类型
    conflict_info = CONFLICT_TYPES.get(conflict_type)
    if conflict_info is None:
        return _conflict_error_result(
            character_id, target_id, conflict_type,
            current_relation_strength,
            f"Unknown conflict_type: {conflict_type}. "
            f"Allowed: {sorted(CONFLICT_TYPES.keys())}",
        )

    recovery_rate, min_relation = conflict_info

    # 校验关系强度范围
    if current_relation_strength < RELATION_MIN or current_relation_strength > RELATION_MAX:
        return _conflict_error_result(
            character_id, target_id, conflict_type,
            current_relation_strength,
            f"relation_strength must be in [{RELATION_MIN}, {RELATION_MAX}]",
        )

    # 校验冲突类型的关系强度门槛
    if min_relation is not None and current_relation_strength < min_relation:
        return _conflict_error_result(
            character_id, target_id, conflict_type,
            current_relation_strength,
            f"Conflict type '{conflict_type}' requires relation_strength >= "
            f"{min_relation}, have {current_relation_strength}",
        )

    # 计算关系强度 bonus（每点关系强度 +0.1% 恢复率）
    relation_bonus = current_relation_strength * CONFLICT_RELATION_BONUS_RATE

    # 计算恢复量
    final_recovery_rate = recovery_rate + relation_bonus
    relation_strength_delta = int(BASE_CONFLICT_RECOVERY * final_recovery_rate)
    new_relation_strength = _clamp_relation(current_relation_strength + relation_strength_delta)

    logger.info(
        "resolve_conflict_validated",
        character_id=character_id,
        target_id=target_id,
        conflict_type=conflict_type,
        base_recovery_rate=recovery_rate,
        relation_bonus=relation_bonus,
        final_recovery_rate=final_recovery_rate,
        relation_strength_delta=relation_strength_delta,
        new_relation_strength=new_relation_strength,
    )

    return {
        "success": True,
        "action": "resolve_conflict",
        "character_id": character_id,
        "target_id": target_id,
        "conflict_type": conflict_type,
        "resolved": True,
        "relation_strength_delta": relation_strength_delta,
        "new_relation_strength": new_relation_strength,
        "error": None,
    }


# ============================================================
# 错误返回辅助函数
# ============================================================

def _gift_error_result(
    character_id: str,
    target_id: str,
    item_id: str,
    current_relation_strength: int,
    error: str,
) -> dict[str, Any]:
    """构造 give_gift 错误返回"""
    return {
        "success": False,
        "action": "give_gift",
        "character_id": character_id,
        "target_id": target_id,
        "item_id": item_id,
        "relation_strength_delta": 0,
        "inventory_delta": {},
        "new_relation_strength": current_relation_strength,
        "error": error,
    }


def _date_error_result(
    character_id: str,
    target_id: str,
    scene_id: str,
    error: str,
) -> dict[str, Any]:
    """构造 invite_date 错误返回"""
    return {
        "success": False,
        "action": "invite_date",
        "character_id": character_id,
        "target_id": target_id,
        "scene_id": scene_id,
        "accepted": False,
        "relation_strength_delta": 0,
        "mood_delta": None,
        "error": error,
    }


def _conflict_error_result(
    character_id: str,
    target_id: str,
    conflict_type: str,
    current_relation_strength: int,
    error: str,
) -> dict[str, Any]:
    """构造 resolve_conflict 错误返回"""
    return {
        "success": False,
        "action": "resolve_conflict",
        "character_id": character_id,
        "target_id": target_id,
        "conflict_type": conflict_type,
        "resolved": False,
        "relation_strength_delta": 0,
        "new_relation_strength": current_relation_strength,
        "error": error,
    }


if __name__ == "__main__":
    mcp.run()
