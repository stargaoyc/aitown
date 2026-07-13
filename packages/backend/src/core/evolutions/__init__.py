"""世界演化系统模块

导出所有演化器及基类。World Engine 通过遍历 `default_evolutions()` 返回的
演化器列表（按依赖顺序：时间 → 天气 → 场景 → 资源 → 事件）驱动世界推进。

Redis Key 约定：
    world:state            - Hash，主世界状态（合并各演化器返回字段）
    world:state:time       - Hash，时间相关
    world:state:weather    - Hash，天气
    world:state:scenes     - Hash，场景状态（scene_id → JSON）
    world:state:resources  - Hash，资源（good_id → JSON）
    world:state:events     - Hash，活跃事件（event_id → JSON）
"""

from src.core.evolutions.base import WorldEvolution
from src.core.evolutions.event_evolution import EventEvolution
from src.core.evolutions.resource_evolution import ResourceEvolution
from src.core.evolutions.scene_evolution import SceneEvolution
from src.core.evolutions.time_evolution import TimeEvolution
from src.core.evolutions.weather_evolution import WeatherEvolution

__all__ = [
    "WorldEvolution",
    "TimeEvolution",
    "WeatherEvolution",
    "SceneEvolution",
    "ResourceEvolution",
    "EventEvolution",
    "default_evolutions",
]


def default_evolutions() -> list[WorldEvolution]:
    """默认演化器列表（按依赖顺序排列）

    时间演化器必须最先执行，后续演化器（天气/场景/事件）依赖其写入的
    虚拟时间与季节。
    """
    return [
        TimeEvolution(),
        WeatherEvolution(),
        SceneEvolution(),
        ResourceEvolution(),
        EventEvolution(),
    ]
