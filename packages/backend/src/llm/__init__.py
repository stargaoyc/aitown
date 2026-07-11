"""LLM 模块 - OpenAI + LangChain 统一接口（支持三模态）

提供三种模型能力：
- chat: 对话+图像理解（agnes-2.0-flash），使用 /v1/chat/completions
- image: 图像生成（agnes-image-2.1-flash），使用 /v1/images/generations
- video: 视频生成（agnes-video-v2.0），使用 /v1/videos（异步任务）

方法：
- chat(prompt): 纯文本对话
- multimodal_chat(content): 多模态对话（含图像理解）
- generate_image(prompt, ...): 图像生成
- generate_video(prompt, ...): 视频生成
- structured_output(prompt, schema): 纯文本结构化输出
- multimodal_structured_output(content, schema): 多模态结构化输出
- embed(text): 文本嵌入
- embed_multimodal(text, image_url): 多模态嵌入
"""
from src.llm.client import LLMClient
from src.llm.prompts import PromptTemplates

__all__ = ["LLMClient", "PromptTemplates"]
