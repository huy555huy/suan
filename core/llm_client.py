"""LLM 客户端封装。

约束：
- 使用 OpenAI 兼容 SDK 调用配置端点
- 强制结构化输出（JSON 模式）
- 支持流式 / 非流式
- 内置重试；最终失败则抛错
"""
from __future__ import annotations
import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, AsyncIterator, Iterable

from openai import AsyncOpenAI

from .config import settings

logger = logging.getLogger("suan.llm")


@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str = ""


_client: AsyncOpenAI | None = None

# 全局健康状态：连续失败 N 次后标记不可用，每 5 分钟允许重试一次
LLM_HEALTH = {
    "available": True,
    "consecutive_failures": 0,
    "last_failure_ts": 0,
    "last_failure_reason": "",
}


def llm_available() -> bool:
    """对外接口：当前 LLM 是否可用。失败累积后短时间内直接报不可用。"""
    import time as _time
    if LLM_HEALTH["available"]:
        return True
    # 5 分钟后允许重试
    if _time.time() - LLM_HEALTH["last_failure_ts"] > 300:
        LLM_HEALTH["available"] = True
        LLM_HEALTH["consecutive_failures"] = 0
        return True
    return False


def _record_llm_failure(reason: str) -> None:
    import time as _time
    LLM_HEALTH["consecutive_failures"] += 1
    LLM_HEALTH["last_failure_ts"] = _time.time()
    LLM_HEALTH["last_failure_reason"] = reason
    if LLM_HEALTH["consecutive_failures"] >= 3:
        LLM_HEALTH["available"] = False
        logger.warning("LLM 连续失败 ≥3 次，临时标记为不可用：%s", reason)


def _record_llm_success() -> None:
    LLM_HEALTH["consecutive_failures"] = 0
    LLM_HEALTH["available"] = True


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if not settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY 未配置（检查 .env）")
        _client = AsyncOpenAI(
            base_url=settings.llm_base_url.rstrip("/") + "/v1",
            api_key=settings.llm_api_key,
            timeout=settings.request_timeout,
            max_retries=0,  # we manage retries ourselves
        )
    return _client


def _extract_json(text: str) -> Any:
    """尽力从 LLM 响应里提取 JSON 对象。"""
    text = text.strip()
    if not text:
        return None
    # 直接 json.loads
    try:
        return json.loads(text)
    except Exception:
        pass
    # 截取 markdown code fence
    fence = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.S)
    if fence:
        try:
            return json.loads(fence.group(1))
        except Exception:
            pass
    # 截取首尾大括号
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if 0 <= brace_start < brace_end:
        try:
            return json.loads(text[brace_start : brace_end + 1])
        except Exception:
            pass
    bracket_start = text.find("[")
    bracket_end = text.rfind("]")
    if 0 <= bracket_start < bracket_end:
        try:
            return json.loads(text[bracket_start : bracket_end + 1])
        except Exception:
            pass
    return None


async def chat(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.6,
    max_tokens: int = 2048,
    response_json: bool = False,
    tier: str = "high",
) -> tuple[str, LLMUsage]:
    """非流式调用。返回 (text, usage)。"""
    cli = get_client()
    chosen = model or (settings.model_high if tier == "high" else settings.model_low)
    last_err: Exception | None = None
    for attempt in range(settings.max_retries + 1):
        try:
            kwargs: dict[str, Any] = dict(
                model=chosen,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if response_json:
                kwargs["response_format"] = {"type": "json_object"}
            resp = await cli.chat.completions.create(**kwargs)
            choice = resp.choices[0]
            text = choice.message.content or ""
            usage = LLMUsage(
                prompt_tokens=getattr(resp.usage, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(resp.usage, "completion_tokens", 0) or 0,
                total_tokens=getattr(resp.usage, "total_tokens", 0) or 0,
                finish_reason=getattr(choice, "finish_reason", "") or "",
            )
            _record_llm_success()
            return text, usage
        except Exception as e:
            last_err = e
            err_str = str(e)
            logger.warning("LLM call failed (attempt %d/%d): %s", attempt + 1,
                           settings.max_retries + 1, err_str[:200])
            # 订阅 / 鉴权错误立刻 fail-fast，不重试
            if "SUBSCRIPTION_NOT_FOUND" in err_str or "401" in err_str or "403" in err_str:
                _record_llm_failure(err_str[:200])
                raise
            if attempt < settings.max_retries:
                await asyncio.sleep(0.6 * (attempt + 1))
                # 只在端点明确不支持 response_format 时才降级；超时/限流等重试
                # 必须保留 JSON mode，否则结构化节点会偶发输出非严格 JSON。
                if (response_json and attempt == 0 and "response_format" in err_str
                    and ("unsupported" in err_str.lower()
                         or "not support" in err_str.lower())):
                    response_json = False
            else:
                _record_llm_failure(err_str[:200])
                raise
    raise RuntimeError(f"LLM 调用最终失败: {last_err}")


async def chat_json(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.4,
    max_tokens: int = 3000,
    tier: str = "high",
) -> tuple[Any, str, LLMUsage]:
    """要求结构化 JSON 输出。返回 (parsed_json_or_None, raw_text, usage)。"""
    text, usage = await chat(
        messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        response_json=True,
        tier=tier,
    )
    if usage.finish_reason == "length":
        raise RuntimeError(
            f"LLM JSON 输出被截断：finish_reason=length, "
            f"completion_tokens={usage.completion_tokens}, max_tokens={max_tokens}"
        )
    parsed = _extract_json(text)
    return parsed, text, usage


async def chat_stream(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.65,
    max_tokens: int = 2048,
    tier: str = "high",
) -> AsyncIterator[str]:
    """流式调用，yield 文本片段。"""
    cli = get_client()
    chosen = model or (settings.model_high if tier == "high" else settings.model_low)
    stream = await cli.chat.completions.create(
        model=chosen,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    async for chunk in stream:
        try:
            delta = chunk.choices[0].delta.content
        except Exception:
            delta = None
        if delta:
            yield delta
