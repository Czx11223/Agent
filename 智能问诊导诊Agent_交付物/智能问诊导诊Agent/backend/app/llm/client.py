"""OpenAI 兼容 LLM 客户端（复用 httpx 底层的连接，能力等价 OpenAI SDK）。"""
import json
import time

from ..core import config
from ..core.errors import ApiError, LLM_ERROR

# 瞬时网络故障（DNS 失败/连接超时/限流/5xx）的重试次数与指数退避基数（秒）
_MAX_RETRY = 3
_BACKOFF = 3.0


def chat_json(messages: list[dict], temperature: float | None = None, max_tokens: int | None = None) -> dict:
    """单次对话，要求模型返回 JSON 对象；网络类瞬时故障自动重试。"""
    import httpx

    if not config.LLM_API_KEY or not config.LLM_BASE_URL:
        raise ApiError(LLM_ERROR, "未配置 LLM_API_KEY / LLM_BASE_URL")

    payload = {
        "model": config.LLM_MODEL,
        "messages": messages,
        "temperature": temperature if temperature is not None else config.LLM_TEMPERATURE,
        "max_tokens": max_tokens if max_tokens is not None else config.LLM_MAX_TOKENS,
        "response_format": {"type": "json_object"},
        "stream": True,
    }
    url = f"{config.LLM_BASE_URL.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {config.LLM_API_KEY}"}
    # 连接阶段快速失败（避免 TCP 层久等），读取阶段保留长超时以适配大模型
    timeout = httpx.Timeout(config.LLM_TIMEOUT, connect=10.0)

    def _try_parse(data: str) -> dict | None:
        try:
            return json.loads(data)
        except Exception:
            return None

    last_err = None
    for attempt in range(_MAX_RETRY):
        try:
            parts: list[str] = []
            with httpx.stream("POST", url, headers=headers, json=payload, timeout=timeout) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_text():
                    for line in chunk.splitlines():
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data.startswith("[DONE]"):
                            break
                        try:
                            obj = json.loads(data)
                        except Exception:
                            continue
                        choice = obj.get("choices") or [{}]
                        delta = choice[0].get("delta") or {}
                        if delta.get("content"):
                            parts.append(delta["content"])
                        msg = choice[0].get("message") or {}
                        if msg.get("content"):
                            parts.append(msg["content"])
                        parsed = _try_parse("".join(parts))
                        if parsed is not None:
                            return parsed  # 尽早返回：JSON 已合法即停止消费，避免等满 max_tokens
                # 流结束仍未拼出合法 JSON，兜底解析
                parsed = _try_parse("".join(parts))
                if parsed is not None:
                    return parsed
                raise ValueError("流式响应未产出合法 JSON 决策")
        except ApiError:
            raise
        except Exception as e:  # noqa
            last_err = e
            status = getattr(getattr(e, "response", None), "status_code", None)
            retryable = status is None or status == 429 or status >= 500
            if retryable and attempt < _MAX_RETRY - 1:
                delay = _BACKOFF * (2 ** attempt)
                if status == 429:
                    delay *= 2
                time.sleep(delay)
                continue
            raise ApiError(LLM_ERROR, f"LLM 调用失败: {e}")