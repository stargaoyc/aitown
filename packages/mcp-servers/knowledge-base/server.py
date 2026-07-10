"""MCP Knowledge Base Server - 小镇设定库查询

为 AI Town 角色（LLM）提供小镇设定检索能力，覆盖世界规则、角色系统、场景系统、
行动系统、记忆系统等核心设定。

设计：
- 内置硬编码知识库（模块级常量），生产环境可通过配置文件覆盖
- 基于关键词的加权检索（keywords > title > content）
- 支持按类别（category）过滤
- 无状态：所有调用不依赖外部存储，单进程即可运行

返回结构：
    {
        "success": bool,
        "query": str,
        "category": str | None,
        "results": [
            {
                "id": str,
                "category": str,
                "title": str,
                "content": str,
                "keywords": list[str],
                "score": float,
            }
        ],
        "total": int,
        "error": str | None,
    }
"""
from __future__ import annotations

from typing import Any

import structlog
from fastmcp import FastMCP  # FastMCP 2.0+ 导入方式
from pydantic import BaseModel, Field

logger = structlog.get_logger()

mcp = FastMCP("knowledge-base")


# ============================================================
# 知识库数据模型
# ============================================================

class KBEntry(BaseModel):
    """知识库条目定义"""
    id: str = Field(description="条目唯一标识")
    category: str = Field(description="类别：world_rules/character_system/scene_system/action_system/memory_system")
    title: str = Field(description="条目标题")
    content: str = Field(description="条目内容（设定详细说明）")
    keywords: list[str] = Field(default_factory=list, description="关键词列表，用于检索匹配")


# ============================================================
# 内置知识库数据（模块级常量）
# 生产环境可通过配置文件覆盖
# ============================================================

DEFAULT_KB: list[KBEntry] = [
    # ----------------------------------------------------------
    # 世界规则（world_rules）
    # ----------------------------------------------------------
    KBEntry(
        id="world_time_system",
        category="world_rules",
        title="时间系统",
        content=(
            "虚拟时钟每 Tick 推进 10 分钟，一天共 144 Ticks。"
            "世界引擎按 Tick 节拍推进所有角色状态、行动结算与事件触发。"
            "1 Tick = 10 分钟现实等价时间，便于换算行动耗时。"
        ),
        keywords=["时间", "tick", "时钟", "10分钟", "144", "虚拟时钟"],
    ),
    KBEntry(
        id="world_weather_system",
        category="world_rules",
        title="天气系统",
        content=(
            "每 60 Tick 更新一次天气（即每虚拟 10 小时刷新一次）。"
            "天气类型包括：晴、阴、雨、暴雨、雪、雾等，影响场景拥挤度与部分行动可行性。"
        ),
        keywords=["天气", "weather", "60 tick", "晴", "雨", "雪", "雾"],
    ),
    KBEntry(
        id="world_season_system",
        category="world_rules",
        title="季节系统",
        content=(
            "四季轮转：春樱、夏阳、秋叶、冬雪各 36 天，全年 144 天。"
            "季节影响场景外观、可触发事件与可用物品（如冬季可堆雪人、春季可赏樱）。"
        ),
        keywords=["季节", "season", "春樱", "夏阳", "秋叶", "冬雪", "36天", "四季"],
    ),
    KBEntry(
        id="world_tick_lock",
        category="world_rules",
        title="世界 Tick 分布式锁",
        content=(
            "世界 Tick 使用 Redis 分布式锁确保单实例运行，避免多实例同时推进导致状态错乱。"
            "锁键名 world:tick:lock，持有期间执行 Tick 推进逻辑，完成后释放。"
        ),
        keywords=["tick", "redis", "分布式锁", "单实例", "world:tick:lock", "锁"],
    ),

    # ----------------------------------------------------------
    # 角色系统（character_system）
    # ----------------------------------------------------------
    KBEntry(
        id="character_attributes",
        category="character_system",
        title="角色属性",
        content=(
            "角色核心属性：stamina(体力)、satiety(饱腹)、mood(情绪)、money(金钱)、social_energy(社交能量)。"
            "属性随行动消耗/恢复，过低会触发负面状态（如体力为 0 强制休息）。"
        ),
        keywords=["属性", "stamina", "体力", "satiety", "饱腹", "mood", "情绪", "money", "金钱", "social_energy", "社交能量"],
    ),
    KBEntry(
        id="character_sleep_schedule",
        category="character_system",
        title="作息类型",
        content=(
            "角色作息类型分三种：early_bird(早起鸟)、normal(普通)、night_owl(夜猫子)。"
            "作息类型决定角色最佳睡眠时段、精力恢复效率与可执行行动的偏好时段。"
        ),
        keywords=["作息", "early_bird", "早起鸟", "normal", "普通", "night_owl", "夜猫子", "睡眠"],
    ),
    KBEntry(
        id="character_relationship_levels",
        category="character_system",
        title="关系等级",
        content=(
            "角色间关系等级递进：stranger(陌生人) → acquaintance(熟人) → friend(朋友) "
            "→ close_friend(密友) → best_friend(挚友)。"
            "关系等级影响社交行动成功率与可触发的特殊事件。"
        ),
        keywords=["关系", "relationship", "stranger", "陌生人", "acquaintance", "熟人", "friend", "朋友", "close_friend", "密友", "best_friend", "挚友"],
    ),
    KBEntry(
        id="character_state_storage",
        category="character_system",
        title="角色状态存储",
        content=(
            "角色状态采用双存储：Redis 存储实时状态（高频读写，如当前属性值、位置），"
            "PostgreSQL 存储持久化数据（低频读写，如角色档案、关系历史）。"
            "Tick 结算时将 Redis 状态快照回写 PostgreSQL。"
        ),
        keywords=["存储", "redis", "postgresql", "pg", "实时", "持久化", "快照", "状态"],
    ),

    # ----------------------------------------------------------
    # 场景系统（scene_system）
    # ----------------------------------------------------------
    KBEntry(
        id="scene_types",
        category="scene_system",
        title="场景类型",
        content=(
            "小镇场景类型：home(家)、cafe(咖啡馆)、park(公园)、school(学校)、shop(商店)、"
            "restaurant(餐厅)、cinema(电影院)、beach(海滩)、shrine(神社)、library(图书馆)。"
            "每个场景支持特定类别的行动。"
        ),
        keywords=["场景", "scene", "home", "家", "cafe", "咖啡馆", "park", "公园", "school", "学校", "shop", "商店", "restaurant", "餐厅", "cinema", "电影院", "beach", "海滩", "shrine", "神社", "library", "图书馆"],
    ),
    KBEntry(
        id="scene_crowdness",
        category="scene_system",
        title="场景拥挤度",
        content=(
            "场景拥挤度取值 0.0-1.0，影响行动耗时（拥挤度越高，行动耗时越长）。"
            "拥挤度随时间、天气、事件动态变化，由世界引擎每 Tick 更新。"
        ),
        keywords=["拥挤度", "crowdness", "0.0", "1.0", "耗时", "动态"],
    ),
    KBEntry(
        id="scene_open_hours",
        category="scene_system",
        title="场景开放时间",
        content=(
            "部分场景有开放时间限制（如 cafe 07:00-22:00、library 09:00-21:00），"
            "非开放时段角色无法进入或执行该场景专属行动。home 场景全天开放。"
        ),
        keywords=["开放时间", "open hours", "cafe", "library", "时段", "限制"],
    ),
    KBEntry(
        id="scene_move_matrix",
        category="scene_system",
        title="场景移动矩阵",
        content=(
            "场景间移动耗时由 Dijkstra 算法计算最短路径。"
            "移动矩阵预计算邻接场景间的基础耗时，结合拥挤度修正得到实际耗时。"
        ),
        keywords=["移动", "move", "matrix", "dijkstra", "最短路径", "邻接", "耗时", "矩阵"],
    ),

    # ----------------------------------------------------------
    # 行动系统（action_system）
    # ----------------------------------------------------------
    KBEntry(
        id="action_categories",
        category="action_system",
        title="Action 分类",
        content=(
            "Action 分四大类：life(生活，如吃饭/睡觉/阅读)、work(工作，如打工/创作)、"
            "social(社交，如聊天/送礼/约会)、move(移动，如前往其他场景)。"
        ),
        keywords=["action", "行动", "分类", "life", "生活", "work", "工作", "social", "社交", "move", "移动"],
    ),
    KBEntry(
        id="action_limits",
        category="action_system",
        title="行动限制",
        content=(
            "每日行动受体力/饱腹/社交能量限制：属性不足时对应行动不可执行或效率降低。"
            "如社交行动消耗 social_energy，工作行动消耗 stamina，吃饭恢复 satiety。"
        ),
        keywords=["限制", "体力", "饱腹", "社交能量", "每日", "消耗", "恢复"],
    ),
    KBEntry(
        id="action_transaction",
        category="action_system",
        title="Action 事务化执行",
        content=(
            "Action 执行为事务化：PostgreSQL 事务记录行动日志 + Redis 状态原子更新。"
            "任一步失败则整体回滚，保证角色状态一致性。"
        ),
        keywords=["事务", "transaction", "postgresql", "pg", "redis", "回滚", "原子", "一致", "日志"],
    ),

    # ----------------------------------------------------------
    # 记忆系统（memory_system）
    # ----------------------------------------------------------
    KBEntry(
        id="memory_types",
        category="memory_system",
        title="记忆类型",
        content=(
            "记忆分两类：episode(情节记忆，记录具体事件) 与 reflection(反思，由 LLM 对情节归纳生成)。"
            "反思记忆权重更高，影响角色长期性格与决策倾向。"
        ),
        keywords=["记忆", "memory", "episode", "情节", "reflection", "反思", "归纳"],
    ),
    KBEntry(
        id="memory_retrieval",
        category="memory_system",
        title="记忆检索方式",
        content=(
            "记忆检索使用 pgvector HNSW 向量相似度检索：将记忆文本 embedding 后存入向量列，"
            "查询时对 query embedding 做最近邻搜索，返回 Top-K 相关记忆。"
        ),
        keywords=["检索", "retrieval", "pgvector", "hnsw", "向量", "相似度", "embedding", "最近邻"],
    ),
    KBEntry(
        id="memory_partition",
        category="memory_system",
        title="记忆分区",
        content=(
            "memory_episodes 表按 character_id HASH 分区（16 分区），"
            "避免单表过大并提升按角色查询的吞吐。每个分区独立维护索引与 HNSW 图。"
        ),
        keywords=["分区", "partition", "hash", "memory_episodes", "character_id", "16", "索引", "hnsw"],
    ),
]


# 类别描述映射（供 list_categories 返回）
CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "world_rules": "世界规则（时间/天气/季节/Tick 调度）",
    "character_system": "角色系统（属性/作息/关系/状态存储）",
    "scene_system": "场景系统（场景类型/拥挤度/开放时间/移动矩阵）",
    "action_system": "行动系统（Action 分类/限制/事务化执行）",
    "memory_system": "记忆系统（记忆类型/检索/分区）",
}


# ============================================================
# 检索逻辑
# ============================================================

# 检索匹配权重
SCORE_KEYWORD_MATCH = 3.0   # keywords 完全匹配
SCORE_TITLE_CONTAIN = 2.0   # title 包含关键词
SCORE_CONTENT_CONTAIN = 1.0  # content 包含关键词


def _score_entry(entry: KBEntry, tokens: list[str]) -> float:
    """计算单条知识条目相对查询词的匹配分数

    匹配规则：
        - keywords 列表中存在完全匹配的 token：+3 分
        - title 包含某 token：+2 分
        - content 包含某 token：+1 分
    每个 token 对每种匹配类型独立计分。

    Args:
        entry: 知识库条目
        tokens: 查询分词后的 token 列表

    Returns:
        匹配总分
    """
    if not tokens:
        return 0.0

    keywords_lower = [k.lower() for k in entry.keywords]
    title_lower = entry.title.lower()
    content_lower = entry.content.lower()

    score = 0.0
    for token in tokens:
        token_lower = token.lower()
        if not token_lower:
            continue
        # keywords 完全匹配
        if token_lower in keywords_lower:
            score += SCORE_KEYWORD_MATCH
        # title 包含关键词
        if token_lower in title_lower:
            score += SCORE_TITLE_CONTAIN
        # content 包含关键词
        if token_lower in content_lower:
            score += SCORE_CONTENT_CONTAIN

    return score


def _query_kb_internal(
    query: str,
    category: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """执行知识库检索的内部实现

    Args:
        query: 查询字符串
        category: 可选类别过滤
        limit: 返回结果上限

    Returns:
        匹配的知识条目列表（已按分数降序排序，并附加 score 字段）
    """
    # 按空格分词（兼容中英文混排，连续空格视为单分隔符）
    tokens = [t for t in query.split() if t]

    scored: list[tuple[float, KBEntry]] = []
    for entry in DEFAULT_KB:
        # 类别过滤
        if category and entry.category != category:
            continue
        score = _score_entry(entry, tokens)
        if score > 0:
            scored.append((score, entry))

    # 按分数降序排列
    scored.sort(key=lambda x: x[0], reverse=True)

    # 取 top N
    results: list[dict[str, Any]] = []
    for score, entry in scored[:limit]:
        results.append({
            "id": entry.id,
            "category": entry.category,
            "title": entry.title,
            "content": entry.content,
            "keywords": list(entry.keywords),
            "score": score,
        })

    return results


# ============================================================
# MCP Tools
# ============================================================

@mcp.tool()
async def query_kb(
    query: str,
    category: str | None = None,
    limit: int = 5,
) -> dict:
    """关键词检索小镇设定库

    支持按类别过滤，返回加权排序后的匹配条目。
    匹配权重：keywords 完全匹配 (+3) > title 包含 (+2) > content 包含 (+1)。

    Args:
        query: 查询关键词（多个关键词以空格分隔，中英文均可）
        category: 可选类别过滤，可选值：
            world_rules / character_system / scene_system / action_system / memory_system
        limit: 返回结果上限，默认 5，范围 1-50

    Returns:
        {
            "success": bool,
            "query": str,
            "category": str | None,
            "results": [
                {
                    "id": str,
                    "category": str,
                    "title": str,
                    "content": str,
                    "keywords": list[str],
                    "score": float,
                }
            ],
            "total": int,
            "error": str | None,
        }
    """
    # 输入校验
    if not query or not query.strip():
        logger.info("query_kb_empty_query", category=category)
        return {
            "success": False,
            "query": query,
            "category": category,
            "results": [],
            "total": 0,
            "error": "Query must not be empty",
        }

    if limit < 1:
        limit = 1
    if limit > 50:
        limit = 50

    # 校验类别（若提供）
    valid_categories = set(CATEGORY_DESCRIPTIONS.keys())
    if category and category not in valid_categories:
        logger.info(
            "query_kb_invalid_category",
            category=category,
            valid=list(valid_categories),
        )
        return {
            "success": False,
            "query": query,
            "category": category,
            "results": [],
            "total": 0,
            "error": f"Invalid category: {category}. Valid: {sorted(valid_categories)}",
        }

    results = _query_kb_internal(query, category, limit)

    logger.info(
        "query_kb_called",
        query=query,
        category=category,
        limit=limit,
        returned=len(results),
    )

    return {
        "success": True,
        "query": query,
        "category": category,
        "results": results,
        "total": len(results),
        "error": None,
    }


@mcp.tool()
async def list_categories() -> dict:
    """列出知识库所有类别及其条目数量

    Returns:
        {
            "categories": [
                {"name": str, "entry_count": int, "description": str}
            ],
            "total": int,
        }
    """
    # 统计每个类别的条目数
    count_by_cat: dict[str, int] = {}
    for entry in DEFAULT_KB:
        count_by_cat[entry.category] = count_by_cat.get(entry.category, 0) + 1

    categories: list[dict[str, Any]] = []
    for name, desc in CATEGORY_DESCRIPTIONS.items():
        categories.append({
            "name": name,
            "entry_count": count_by_cat.get(name, 0),
            "description": desc,
        })

    logger.info("list_categories_called", total_categories=len(categories))

    return {
        "categories": categories,
        "total": len(categories),
    }


if __name__ == "__main__":
    mcp.run()
