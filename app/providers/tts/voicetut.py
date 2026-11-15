"""
VoiceTut TTS Provider — Unified with XTTSProvider (VoiceTut-powered).
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VoiceTut is the primary XTTS voice cloning engine for Egyptian Arabic (arz).
This module aliases VoiceTutProvider to XTTSProvider for seamless unification.
"""

from app.providers.tts.xtts.provider import XTTSProvider

# VoiceTutProvider is unified with XTTSProvider as the primary Egyptian voice engine
class VoiceTutProvider(XTTSProvider):
    """VoiceTut-powered TTS Provider for Egyptian Arabic."""

    @classmethod
    def list_speakers(cls) -> list[dict]:
        return XTTSProvider.list_speakers()


__all__ = ["VoiceTutProvider", "XTTSProvider"]
