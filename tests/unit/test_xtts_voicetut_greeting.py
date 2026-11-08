"""
Unit tests for XTTS VoiceTut TTS Provider unification and Cloned Greeting Caching.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.providers.tts.base import BaseTTSProvider
from app.providers.tts.factory import get_tts_provider
from app.providers.tts.xtts.provider import XTTSProvider
from app.providers.tts.voicetut import VoiceTutProvider
from app.services.voice_clone.voice_clone_service import VoiceCloneService


def test_xtts_provider_is_main_engine():
    """Verify XTTSProvider is powered by VoiceTut and acts as the main TTS engine."""
    provider = XTTSProvider()
    assert isinstance(provider, BaseTTSProvider)
    assert provider._language == "arz"


def test_base_tts_provider_get_default():
    """BaseTTSProvider.get_default() returns XTTSProvider."""
    default_p = BaseTTSProvider.get_default()
    assert isinstance(default_p, XTTSProvider)


def test_factory_returns_xtts_as_default_and_fallback():
    """get_tts_provider returns XTTSProvider for any alias or unknown provider."""
    assert isinstance(get_tts_provider(), XTTSProvider)
    assert isinstance(get_tts_provider("xtts"), XTTSProvider)
    assert isinstance(get_tts_provider("voicetut"), XTTSProvider)
    assert isinstance(get_tts_provider("voicetut_service"), XTTSProvider)
    assert isinstance(get_tts_provider("unknown_tts_provider"), XTTSProvider)


def test_voicetut_provider_is_alias_of_xtts():
    """VoiceTutProvider is unified with XTTSProvider."""
    assert VoiceTutProvider is XTTSProvider


@pytest.mark.asyncio
async def test_cloned_greeting_caching_lifecycle(tmp_path):
    """Verify pre-caching and retrieval of cloned voice greeting."""
    provider = XTTSProvider()

    test_wav = tmp_path / "greeting_test.wav"
    mock_audio_bytes = b"RIFF....WAVEfmt ....data...."

    with patch.object(XTTSProvider, "get_greeting_cache_path", return_value=test_wav):
        with patch.object(XTTSProvider, "synthesize", new_callable=AsyncMock) as mock_synth:
            mock_synth.return_value = mock_audio_bytes

            # 1. Precache greeting
            res = await provider.precache_greeting(
                personality_id=999,
                text="أهلاً بيك يا باشا",
                sample_path=str(tmp_path / "sample.wav"),
            )
            assert res == mock_audio_bytes
            assert test_wav.exists()

            # 2. Get cached greeting (0ms retrieval)
            cached = provider.get_cached_greeting(999)
            assert cached == mock_audio_bytes

            # 3. VoiceCloneService integration
            svc = VoiceCloneService.get_instance()
            with patch.object(svc._xtts, "get_cached_greeting", return_value=mock_audio_bytes):
                assert svc.get_cached_greeting(999) == mock_audio_bytes

