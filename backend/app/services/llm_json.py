from __future__ import annotations

import json
import re


def extract_json_object(text: str) -> dict:
    """从 LLM 输出中提取 JSON 对象，兼容 markdown 代码块与前后说明文字。"""
    value = (text or "").strip()
    if not value:
        raise ValueError("LLM 返回为空，无法提取 JSON")

    # 优先尝试直接解析，兼容已经是纯 JSON 的场景。
    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # 兼容 markdown 代码块（即使前后附带说明文字）。
    fenced_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", value, flags=re.IGNORECASE)
    for block in fenced_blocks:
        candidate = block.strip()
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    # 兜底：提取首尾花括号中的对象片段，兼容“说明文字 + JSON + 说明文字”。
    start = value.find("{")
    end = value.rfind("}")
    if start != -1 and end > start:
        candidate = value[start:end + 1]
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("LLM 输出中未找到可解析的 JSON 对象")
