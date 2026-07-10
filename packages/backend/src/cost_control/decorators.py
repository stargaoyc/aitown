"""成本控制装饰器 - 在 LLM 调用处接入预算检查与熔断

用法：
    @with_cost_control(budget_manager, circuit_breaker)
    async def call_llm(prompt: str) -> tuple[str, int, float]:
        ...
        return text, tokens, cost

约定：被装饰的 async 函数返回值需包含 token / cost 信息，支持两种形式：
1. dict：包含 ``"tokens"`` 与 ``"cost"`` 键
   （如 ``MessageService.handle_user_message`` 的返回值）
2. tuple / list：长度 >= 3，``tokens`` 位于索引 1，``cost`` 位于索引 2
   （如 ``(result, tokens, cost)`` 或 ``(result, tokens, cost, error)``）

流程：
1. 调用前：检查熔断器 ``can_execute()``，OPEN 时抛 ``CircuitOpen``
2. 调用前：检查预算 ``check_budget()``，超预算抛 ``BudgetExceeded``
3. 执行被装饰函数
4. 成功：``record_success()`` + 从返回值提取 tokens/cost 调用 ``record_usage()``
5. 失败（抛异常）：``record_failure()`` 并重新抛出原异常
"""
from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from structlog import get_logger

from src.cost_control.budget_manager import BudgetExceeded, BudgetManager
from src.cost_control.circuit_breaker import CircuitBreaker, CircuitOpen, CircuitState

logger = get_logger(__name__)

T = TypeVar("T")


def _extract_usage(result: Any) -> tuple[int, float]:
    """从被装饰函数的返回值中提取 tokens 与 cost

    支持：
    - dict：``result["tokens"]``、``result["cost"]``
    - tuple/list（len >= 3）：``tokens=result[1]``、``cost=result[2]``

    Returns:
        (tokens, cost)，无法提取时返回 (0, 0.0)
    """
    if isinstance(result, dict):
        return int(result.get("tokens") or 0), float(result.get("cost") or 0.0)
    if isinstance(result, (tuple, list)) and len(result) >= 3:
        try:
            return int(result[1]), float(result[2])
        except (TypeError, ValueError):
            return 0, 0.0
    return 0, 0.0


def with_cost_control(
    budget_manager: BudgetManager,
    circuit_breaker: CircuitBreaker,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """装饰器工厂：为 async LLM 调用接入预算检查 + 熔断

    Args:
        budget_manager: 日预算管理器
        circuit_breaker: 熔断器

    Returns:
        装饰器函数

    Raises:
        CircuitOpen: 熔断器开启，拒绝调用
        BudgetExceeded: 日预算已超出
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            # 1. 熔断检查
            if not await circuit_breaker.can_execute():
                state, failure_count, last_failure_time = await circuit_breaker.snapshot()
                state_str = (
                    state.value if isinstance(state, CircuitState) else str(state)
                )
                logger.warning(
                    "circuit_open_blocked",
                    function=func.__qualname__,
                    state=state_str,
                    failure_count=failure_count,
                )
                raise CircuitOpen(state_str, failure_count, last_failure_time)

            # 2. 预算检查
            budget_status = await budget_manager.check_budget()
            if budget_status["exceeded"]:
                logger.warning(
                    "budget_exceeded_blocked",
                    function=func.__qualname__,
                    used=budget_status["used"],
                    budget=budget_status["budget"],
                    remaining=budget_status["remaining"],
                )
                raise BudgetExceeded(
                    used=budget_status["used"],
                    budget=budget_status["budget"],
                    remaining=budget_status["remaining"],
                )

            if budget_status["warning"]:
                logger.warning(
                    "budget_warning",
                    function=func.__qualname__,
                    ratio=budget_status["ratio"],
                    used=budget_status["used"],
                    budget=budget_status["budget"],
                )

            # 3. 执行被装饰函数
            try:
                result = await func(*args, **kwargs)
            except Exception:
                await circuit_breaker.record_failure()
                raise

            # 4. 成功：记录熔断恢复 + 记录 usage
            await circuit_breaker.record_success()
            tokens, cost = _extract_usage(result)
            if tokens > 0 or cost > 0:
                try:
                    await budget_manager.record_usage(tokens, cost)
                except Exception:
                    # usage 记录失败不应影响主流程
                    logger.error(
                        "usage_record_failed",
                        function=func.__qualname__,
                        tokens=tokens,
                        cost=cost,
                        exc_info=True,
                    )
            return result

        return wrapper

    return decorator
