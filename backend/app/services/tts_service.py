from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import edge_tts

from app.config import settings

logger = logging.getLogger(__name__)

_TTS_CONCURRENCY = 4


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
        output_path.parent.mkdir(parents=True, exist_ok=True)
        communicate = edge_tts.Communicate(text, self.voice)
        await communicate.save(str(output_path))
        logger.info("TTS 生成完成: %s", output_path)
        return AudioResult(path=output_path, text=text)

    async def generate_for_scenes(
        self,
        scenes: list[dict],
        output_dir: Path,
    ) -> dict[str, AudioResult]:
        """为有台词的场景并行生成配音

        Args:
            scenes: [{"id": str, "dialogue": str}, ...]
            output_dir: 音频输出目录

        Returns:
            {scene_id: AudioResult} 映射
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        pending: list[tuple[str, str, Path]] = []
        for scene in scenes:
            dialogue = scene.get("dialogue")
            if not dialogue or not dialogue.strip():
                continue
            scene_id = scene["id"]
            audio_path = output_dir / f"{scene_id}.mp3"
            pending.append((scene_id, dialogue, audio_path))

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
            scene_id, audio_result = item
            results[scene_id] = audio_result

        logger.info("批量 TTS 生成完成: %d/%d 段配音", len(results), len(pending))
        return results
