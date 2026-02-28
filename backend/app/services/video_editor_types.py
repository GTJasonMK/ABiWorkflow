from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class TransitionType(str, Enum):
    NONE = "none"
    CROSSFADE = "crossfade"
    FADE_BLACK = "fade_black"


class CompositionOptions(BaseModel):
    """合成选项"""

    transition_type: TransitionType = TransitionType.CROSSFADE
    transition_duration: float = Field(default=0.5, ge=0.0, le=5.0)
    include_subtitles: bool = True
    include_tts: bool = True
