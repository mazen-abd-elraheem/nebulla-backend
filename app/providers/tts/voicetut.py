"""
VoiceTut TTS Provider — Unified with XTTSProvider (VoiceTut-powered).
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VoiceTut is the primary XTTS voice cloning engine for Egyptian Arabic (arz).
This module aliases VoiceTutProvider to XTTSProvider for seamless unification.
"""

from app.providers.tts.xtts.provider import XTTSProvider

# VoiceTutProvider is unified with XTTSProvider as the primary Egyptian voice engine
VoiceTutProvider = XTTSProvider

__all__ = ["VoiceTutProvider", "XTTSProvider"]
