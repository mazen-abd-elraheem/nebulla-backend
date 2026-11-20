"""Avatar package — 3D Gaussian Head Avatar (GAGAvatar) & face-emoji animation protocol."""

from app.services.avatar.emoji_actions import (
    FACE_EMOJI_ACTIONS,
    extract_emoji_and_emotion,
    list_emoji_action_catalog,
    resolve_expression_spec,
    strip_emojis_for_speech,
)
from app.services.avatar.lipsync import AcousticLipsyncService, get_lipsync_service

__all__ = [
    "FACE_EMOJI_ACTIONS",
    "extract_emoji_and_emotion",
    "list_emoji_action_catalog",
    "resolve_expression_spec",
    "strip_emojis_for_speech",
    "AcousticLipsyncService",
    "get_lipsync_service",
]


