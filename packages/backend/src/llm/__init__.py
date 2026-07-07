"""LLM 模块 - OpenAI + LangChain 统一接口

提供三个模型配置：
- chat: 日常对话（gpt-4o-mini）
- strong: 复杂决策（gpt-4o）
- flash: 快速响应（gpt-3.5-turbo）
"""
from src.llm.client import LLMClient
from src.llm.prompts import PromptTemplates

__all__ = ["LLMClient", "PromptTemplates"]