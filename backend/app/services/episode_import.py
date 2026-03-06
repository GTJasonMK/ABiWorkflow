from __future__ import annotations

import re
from typing import Any

from app.llm.base import Message
from app.llm.factory import create_llm_adapter
from app.services.llm_json import extract_json_object

_MARKER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "cn_episode",
        re.compile(
            r"^\s*(第\s*[0-9零一二三四五六七八九十百千两〇]+(?:\s*[集章节幕篇]))[\s：:\-—]*.*$",
            flags=re.IGNORECASE,
        ),
    ),
    (
        "en_episode",
        re.compile(
            r"^\s*((?:episode|ep)\.?\s*\d+)[\s：:\-—]*.*$",
            flags=re.IGNORECASE,
        ),
    ),
    (
        "numeric_heading",
        re.compile(
            r"^\s*([（(【\[]?\s*\d{1,3}\s*[）)】\]]?)[\s：:\-—]+.*$",
            flags=re.IGNORECASE,
        ),
    ),
)


def _clean_line(value: str) -> str:
    return value.replace("\u3000", " ").strip()


def _normalize_episode_title(raw_title: str | None, index: int) -> str:
    cleaned = _clean_line(raw_title or "")
    if not cleaned:
        return f"第{index + 1}集"
    return cleaned[:200]


def _build_summary(text: str, max_chars: int = 120) -> str | None:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return None
    return cleaned[:max_chars]


def _normalize_episode_item(item: dict[str, Any], index: int) -> dict[str, Any]:
    script_text = str(item.get("script_text") or "").strip()
    if not script_text:
        return {}
    title = _normalize_episode_title(item.get("title"), index)
    summary = _build_summary(str(item.get("summary") or "") or script_text)
    return {
        "title": title,
        "summary": summary,
        "script_text": script_text,
        "order": index,
    }


def detect_episode_markers(content: str) -> dict[str, Any]:
    lines = content.splitlines()
    if len(lines) < 2:
        return {"has_markers": False, "marker_type": None, "confidence": 0.0, "matches": []}

    best_type = None
    best_matches: list[dict[str, Any]] = []
    for marker_type, pattern in _MARKER_PATTERNS:
        matches: list[dict[str, Any]] = []
        for idx, raw_line in enumerate(lines):
            line = _clean_line(raw_line)
            if not line:
                continue
            if pattern.match(line):
                matches.append({
                    "line_index": idx,
                    "line_text": line[:200],
                })
        if len(matches) > len(best_matches):
            best_type = marker_type
            best_matches = matches

    has_markers = len(best_matches) >= 2
    confidence = 0.0
    if has_markers:
        confidence = min(1.0, 0.35 + len(best_matches) * 0.1)

    return {
        "has_markers": has_markers,
        "marker_type": best_type if has_markers else None,
        "confidence": round(confidence, 3),
        "matches": best_matches if has_markers else [],
    }


def split_by_markers(content: str) -> dict[str, Any]:
    marker_result = detect_episode_markers(content)
    if not marker_result["has_markers"]:
        fallback = split_by_paragraph_blocks(content)
        return {
            "method": "heuristic",
            "has_markers": False,
            "marker_type": None,
            "confidence": fallback.get("confidence", 0.3),
            "episodes": fallback["episodes"],
        }

    lines = content.splitlines()
    match_indexes = [int(item["line_index"]) for item in marker_result["matches"]]
    episodes: list[dict[str, Any]] = []

    for idx, start in enumerate(match_indexes):
        end = match_indexes[idx + 1] if idx + 1 < len(match_indexes) else len(lines)
        raw_segment = lines[start:end]
        if not raw_segment:
            continue
        marker_line = _clean_line(raw_segment[0])
        body_lines = [line for line in raw_segment[1:] if _clean_line(line)]
        script_text = "\n".join(body_lines).strip() or marker_line
        title = marker_line
        if "：" in marker_line:
            prefix, suffix = marker_line.split("：", 1)
            title = suffix.strip() or prefix.strip()
        elif ":" in marker_line:
            prefix, suffix = marker_line.split(":", 1)
            title = suffix.strip() or prefix.strip()

        normalized = _normalize_episode_item(
            {"title": title, "summary": _build_summary(script_text), "script_text": script_text},
            index=len(episodes),
        )
        if normalized:
            episodes.append(normalized)

    if not episodes:
        fallback = split_by_paragraph_blocks(content)
        return {
            "method": "heuristic",
            "has_markers": False,
            "marker_type": None,
            "confidence": fallback.get("confidence", 0.3),
            "episodes": fallback["episodes"],
        }

    return {
        "method": "markers",
        "has_markers": True,
        "marker_type": marker_result["marker_type"],
        "confidence": marker_result["confidence"],
        "episodes": episodes,
    }


def split_by_paragraph_blocks(content: str, *, target_episode_count: int = 6) -> dict[str, Any]:
    raw_blocks = [part.strip() for part in re.split(r"\n\s*\n+", content) if part.strip()]
    if not raw_blocks:
        raw_blocks = [content.strip()]
    raw_blocks = [block for block in raw_blocks if block]
    if not raw_blocks:
        return {"method": "heuristic", "confidence": 0.2, "episodes": []}

    total_chars = sum(len(block) for block in raw_blocks)
    target_chars = max(300, total_chars // max(1, min(target_episode_count, len(raw_blocks))))

    merged: list[str] = []
    current = ""
    for block in raw_blocks:
        if not current:
            current = block
            continue
        if len(current) + len(block) <= target_chars:
            current = f"{current}\n\n{block}"
            continue
        merged.append(current)
        current = block
    if current:
        merged.append(current)

    episodes: list[dict[str, Any]] = []
    for idx, text in enumerate(merged):
        normalized = _normalize_episode_item(
            {
                "title": f"第{idx + 1}集",
                "summary": _build_summary(text),
                "script_text": text,
            },
            index=idx,
        )
        if normalized:
            episodes.append(normalized)

    return {"method": "heuristic", "confidence": 0.45, "episodes": episodes}


def _extract_llm_episodes_payload(raw: dict[str, Any]) -> list[dict[str, Any]]:
    source = raw.get("episodes")
    if not isinstance(source, list):
        return []

    items: list[dict[str, Any]] = []
    for idx, item in enumerate(source):
        if not isinstance(item, dict):
            continue
        normalized = _normalize_episode_item(item, idx)
        if normalized:
            items.append(normalized)
    return items


async def split_with_llm(content: str) -> dict[str, Any]:
    """尝试使用 LLM 分集，失败时回退到规则切分。"""
    if not content.strip():
        return {"method": "heuristic", "confidence": 0.0, "episodes": []}

    llm = None
    try:
        llm = create_llm_adapter()
        messages = [
            Message(
                role="system",
                content=(
                    "你是短剧分集助手。请将输入文案拆分为若干集，并仅输出 JSON："
                    '{"episodes":[{"title":"第1集 标题","summary":"摘要","script_text":"该集完整正文"}]}。'
                    "不要输出额外说明。script_text 必须保留原文语义。"
                ),
            ),
            Message(
                role="user",
                content=content,
            ),
        ]
        response = await llm.complete(messages, temperature=0.2)
        parsed = extract_json_object(response.content)
        episodes = _extract_llm_episodes_payload(parsed)
        if episodes:
            return {"method": "llm", "confidence": 0.82, "episodes": episodes}
    except Exception:
        # 回退到规则切分，避免因模型失败阻断主流程。
        pass
    finally:
        if llm is not None:
            await llm.close()

    marker_split = split_by_markers(content)
    if marker_split.get("episodes"):
        marker_split["method"] = "llm_fallback"
        marker_split["confidence"] = min(0.72, float(marker_split.get("confidence") or 0.5))
        return marker_split

    fallback = split_by_paragraph_blocks(content)
    fallback["method"] = "llm_fallback"
    fallback["confidence"] = min(0.65, float(fallback.get("confidence") or 0.45))
    return fallback
