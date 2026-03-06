from __future__ import annotations

import asyncio
import importlib
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_TTS_CONCURRENCY = 4
_EDGE_TTS_MODULE = None


def _load_edge_tts():
    """懒加载 edge_tts，避免依赖异常导致应用启动失败。"""
    global _EDGE_TTS_MODULE
    if _EDGE_TTS_MODULE is not None:
        return _EDGE_TTS_MODULE
    try:
        _EDGE_TTS_MODULE = importlib.import_module("edge_tts")
        return _EDGE_TTS_MODULE
    except Exception as exc:  # noqa: BLE001 - 捕获导入链中的所有异常并转换为可读错误
        raise RuntimeError(
            "edge-tts 依赖不可用（通常是 aiohttp/edge_tts 安装损坏或版本不兼容），"
            "请修复 Python 依赖后再使用 TTS 功能。"
        ) from exc


class AudioResult:
    """TTS 生成结果"""

    def __init__(self, path: Path, text: str):
        self.path = path
        self.text = text


class TTSService:
    """TTS 语音合成服务（基于 edge-tts）"""

    def __init__(self, voice: str | None = None):
        self.voice = voice or settings.tts_voice

    async def generate_audio(self, text: str, output_path: Path) -> AudioResult:
        """为一段文本生成语音文件"""
        edge_tts = _load_edge_tts()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        communicate = edge_tts.Communicate(text, self.voice)
        await communicate.save(str(output_path))
        logger.info("TTS 生成完成: %s", output_path)
        return AudioResult(path=output_path, text=text)

    async def generate_for_panels(
        self,
        panels: list[dict],
        output_dir: Path,
    ) -> dict[str, AudioResult]:
        """为有台词的分镜并行生成配音

        Args:
            panels: [{"id": str, "dialogue": str}, ...]
            output_dir: 音频输出目录

        Returns:
            {panel_id: AudioResult} 映射
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        pending: list[tuple[str, str, Path]] = []
        for panel in panels:
            dialogue = panel.get("dialogue")
            if not dialogue or not dialogue.strip():
                continue
            panel_id = panel["id"]
            audio_path = output_dir / f"{panel_id}.mp3"
            pending.append((panel_id, dialogue, audio_path))

        if not pending:
            return {}

        semaphore = asyncio.Semaphore(_TTS_CONCURRENCY)

        async def _gen(sid: str, text: str, path: Path) -> tuple[str, AudioResult]:
            async with semaphore:
                result = await self.generate_audio(text, path)
                return sid, result

        completed = await asyncio.gather(
            *[_gen(sid, text, path) for sid, text, path in pending],
            return_exceptions=True,
        )

        results: dict[str, AudioResult] = {}
        for item in completed:
            if isinstance(item, BaseException):
                logger.warning("TTS 生成失败: %s", item)
                continue
            panel_id, audio_result = item
            results[panel_id] = audio_result

        logger.info("批量 TTS 生成完成: %d/%d 段配音", len(results), len(pending))
        return results
