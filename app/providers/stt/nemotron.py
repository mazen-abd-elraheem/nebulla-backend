"""
Nemotron Egyptian Arabic STT provider — alternative to QwenCleo (doc §6.1 backup plan).
Stub implementation — fill in when the model is available.
"""

from app.providers.tts.base import BaseSTTProvider


class NemotronProvider(BaseSTTProvider):
    async def transcribe(self, audio_bytes: bytes) -> str:
        raise NotImplementedError(
            "Nemotron STT provider is not yet implemented. "
            "Set STT_PROVIDER=qwencleo in your .env file."
        )
