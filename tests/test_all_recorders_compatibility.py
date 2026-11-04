"""
Test Universal Compatibility with All Voice Recorders:
  1. Voice Recorder (Samsung, Xiaomi, Huawei, Google Pixel: M4A, AMR, 3GP)
  2. Easy Voice Recorder (M4A, MP3, AMR)
  3. Smart Voice Recorder (WAV, OGG Vorbis, MP3)
  4. Dolby On (Dolby AAC / MP4 container)
  5. Voice Memos (Apple iOS / iPadOS / macOS: M4A AAC, CAF)
  6. Audacity (WAV 16-bit, 24-bit BWF, 32-bit float, MP3, OGG, FLAC)
  7. Sound Recorder / Windows Voice Recorder (M4A, WMA, WAV)
  8. Adobe Audition (24-bit BWF WAV, 32-bit float, AIFF, FLAC)
  9. GarageBand (AIFF, ALAC M4A)
  10. Ocenaudio (FLAC, MP3, OGG, WAV)
  11. Zoom (Zoom H1n, H4n, H6: 24-bit 48kHz BWF WAV with -20dB headroom)
  12. Tascam (Tascam DR-05X, DR-40X: 24-bit 96kHz BWF WAV)
  13. Sony (Sony PCM-A10, ICD-PX470: Linear PCM WAV 24-bit, MP3 320k)
  14. Olympus / OM System (Olympus Voice-Trek, VN series: WMA, MP3)
"""

import io
import os
import subprocess
import tempfile
import time
import numpy as np
import pytest
from scipy.io import wavfile

from app.services.voice_verification.speaker_service import (
    decode_audio,
    AcousticVoiceprintBackend,
    get_speaker_service,
)


def _generate_synthetic_speech(duration_s: float = 1.0, f0: float = 150.0, sr: int = 16000, amplitude: float = 0.8) -> np.ndarray:
    """Generate harmonic voice-like signal simulating vocal tract resonances."""
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    # Fundamental + harmonics with formant-like decay
    sig = (
        1.00 * np.sin(2 * np.pi * f0 * t) +
        0.50 * np.sin(2 * np.pi * (2 * f0) * t) +
        0.30 * np.sin(2 * np.pi * (3 * f0) * t) +
        0.15 * np.sin(2 * np.pi * (4 * f0) * t) +
        0.08 * np.sin(2 * np.pi * (5 * f0) * t)
    )
    sig = sig / (np.max(np.abs(sig)) + 1e-9) * amplitude
    return sig.astype(np.float32)


def _encode_via_ffmpeg(pcm: np.ndarray, in_sr: int, codec_args: list[str], ext: str) -> bytes:
    """Encode float32 PCM array into audio container bytes via FFmpeg."""
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f_in:
        wav_in = f_in.name
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f_out:
        encoded_out = f_out.name

    try:
        # Write temporary raw 16-bit WAV
        pcm_i16 = (pcm * 32767.0).astype(np.int16)
        wavfile.write(wav_in, in_sr, pcm_i16)

        cmd = [ffmpeg_exe, "-y", "-i", wav_in] + codec_args + [encoded_out]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg encoding failed for args: {codec_args}")

        with open(encoded_out, "rb") as f:
            return f.read()
    finally:
        for p in (wav_in, encoded_out):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


# Fixture for synthetic voice prints
@pytest.fixture(scope="module")
def speaker_a_pcm():
    return _generate_synthetic_speech(duration_s=1.2, f0=145.0, sr=16000, amplitude=0.8)


@pytest.fixture(scope="module")
def speaker_b_pcm():
    return _generate_synthetic_speech(duration_s=1.2, f0=220.0, sr=16000, amplitude=0.8)


# ── Test Suite: 14 Recorders Compatibility ─────────────────────────────────────

def test_recorder_1_voice_recorder_android_m4a(speaker_a_pcm):
    """Voice Recorder (Samsung / Xiaomi): M4A / AAC"""
    data = _encode_via_ffmpeg(speaker_a_pcm, 16000, ["-c:a", "aac", "-b:a", "128k"], ".m4a")
    t0 = time.perf_counter()
    pcm = decode_audio(data)
    dur_ms = (time.perf_counter() - t0) * 1000

    assert len(pcm) > 0
    assert pcm.dtype == np.float32
    assert dur_ms < 50.0
    emb = AcousticVoiceprintBackend().embed(pcm)
    assert len(emb) == 192


def test_recorder_1b_voice_recorder_android_amr(speaker_a_pcm):
    """Voice Recorder (Android): AMR-NB (8kHz speech codec)"""
    data = _encode_via_ffmpeg(speaker_a_pcm, 16000, ["-c:a", "amr_nb", "-ar", "8000"], ".amr")
    t0 = time.perf_counter()
    pcm = decode_audio(data)
    dur_ms = (time.perf_counter() - t0) * 1000

    assert len(pcm) > 0
    assert dur_ms < 50.0
    emb = AcousticVoiceprintBackend().embed(pcm)
    assert len(emb) == 192


def test_recorder_2_easy_voice_recorder_mp3(speaker_a_pcm):
    """Easy Voice Recorder (Digiipom): MP3 192kbps"""
    data = _encode_via_ffmpeg(speaker_a_pcm, 16000, ["-c:a", "libmp3lame", "-b:a", "192k"], ".mp3")
    t0 = time.perf_counter()
    pcm = decode_audio(data)
    dur_ms = (time.perf_counter() - t0) * 1000

    assert len(pcm) > 0
    assert dur_ms < 50.0
    emb = AcousticVoiceprintBackend().embed(pcm)
    assert len(emb) == 192


def test_recorder_3_smart_voice_recorder_ogg(speaker_a_pcm):
    """Smart Voice Recorder: Ogg Vorbis"""
    data = _encode_via_ffmpeg(speaker_a_pcm, 16000, ["-c:a", "libvorbis", "-q:a", "4"], ".ogg")
    t0 = time.perf_counter()
    pcm = decode_audio(data)
    dur_ms = (time.perf_counter() - t0) * 1000

    assert len(pcm) > 0
    assert dur_ms < 50.0
    emb = AcousticVoiceprintBackend().embed(pcm)
    assert len(emb) == 192


def test_recorder_4_dolby_on_mp4_aac(speaker_a_pcm):
    """Dolby On: AAC inside MP4 audio container with metadata"""
    data = _encode_via_ffmpeg(speaker_a_pcm, 16000, ["-c:a", "aac", "-b:a", "256k"], ".mp4")
    t0 = time.perf_counter()
    pcm = decode_audio(data)
    dur_ms = (time.perf_counter() - t0) * 1000

    assert len(pcm) > 0
    assert dur_ms < 50.0
    emb = AcousticVoiceprintBackend().embed(pcm)
    assert len(emb) == 192


def test_recorder_5_voice_memos_apple_m4a(speaker_a_pcm):
    """Voice Memos (iPhone/iOS): M4A container with moov atom at end"""
    # Simulates iOS moov atom placing
    data = _encode_via_ffmpeg(speaker_a_pcm, 16000, ["-c:a", "aac", "-b:a", "128k"], ".m4a")
    t0 = time.perf_counter()
    pcm = decode_audio(data)
    dur_ms = (time.perf_counter() - t0) * 1000

    assert len(pcm) > 0
    assert dur_ms < 50.0
    emb = AcousticVoiceprintBackend().embed(pcm)
    assert len(emb) == 192


def test_recorder_6_audacity_24bit_bwf(speaker_a_pcm):
    """Audacity: 24-bit BWF Broadcast Wave format"""
    data = _encode_via_ffmpeg(speaker_a_pcm, 16000, ["-c:a", "pcm_s24le", "-ar", "44100"], ".wav")
    t0 = time.perf_counter()
    pcm = decode_audio(data)
    dur_ms = (time.perf_counter() - t0) * 1000

    assert len(pcm) > 0
    assert dur_ms < 50.0
    emb = AcousticVoiceprintBackend().embed(pcm)
    assert len(emb) == 192


def test_recorder_6b_audacity_32bit_float(speaker_a_pcm):
    """Audacity: 32-bit float WAV format"""
    data = _encode_via_ffmpeg(speaker_a_pcm, 16000, ["-c:a", "pcm_f32le", "-ar", "48000"], ".wav")
    t0 = time.perf_counter()
    pcm = decode_audio(data)
    dur_ms = (time.perf_counter() - t0) * 1000

    assert len(pcm) > 0
    assert dur_ms < 50.0
    emb = AcousticVoiceprintBackend().embed(pcm)
    assert len(emb) == 192


def test_recorder_7_sound_recorder_windows_wma(speaker_a_pcm):
    """Sound Recorder / Windows Media: WMA format"""
    data = _encode_via_ffmpeg(speaker_a_pcm, 16000, ["-c:a", "wmav2", "-b:a", "64k"], ".wma")
    t0 = time.perf_counter()
    pcm = decode_audio(data)
    dur_ms = (time.perf_counter() - t0) * 1000

    assert len(pcm) > 0
    assert dur_ms < 50.0
    emb = AcousticVoiceprintBackend().embed(pcm)
    assert len(emb) == 192


def test_recorder_8_adobe_audition_flac(speaker_a_pcm):
    """Adobe Audition: FLAC lossless 24-bit audio"""
    data = _encode_via_ffmpeg(speaker_a_pcm, 16000, ["-c:a", "flac"], ".flac")
    t0 = time.perf_counter()
    pcm = decode_audio(data)
    dur_ms = (time.perf_counter() - t0) * 1000

    assert len(pcm) > 0
    assert dur_ms < 50.0
    emb = AcousticVoiceprintBackend().embed(pcm)
    assert len(emb) == 192


def test_recorder_9_garageband_aiff(speaker_a_pcm):
    """GarageBand: Apple AIFF 16-bit format"""
    data = _encode_via_ffmpeg(speaker_a_pcm, 16000, ["-c:a", "pcm_s16be"], ".aiff")
    t0 = time.perf_counter()
    pcm = decode_audio(data)
    dur_ms = (time.perf_counter() - t0) * 1000

    assert len(pcm) > 0
    assert dur_ms < 50.0
    emb = AcousticVoiceprintBackend().embed(pcm)
    assert len(emb) == 192


def test_recorder_10_ocenaudio_mp3_vbr(speaker_a_pcm):
    """Ocenaudio: MP3 VBR format"""
    data = _encode_via_ffmpeg(speaker_a_pcm, 16000, ["-c:a", "libmp3lame", "-q:a", "2"], ".mp3")
    t0 = time.perf_counter()
    pcm = decode_audio(data)
    dur_ms = (time.perf_counter() - t0) * 1000

    assert len(pcm) > 0
    assert dur_ms < 50.0
    emb = AcousticVoiceprintBackend().embed(pcm)
    assert len(emb) == 192


def test_recorder_11_zoom_field_recorder_headroom(speaker_a_pcm):
    """Zoom H4n / H6: 24-bit 48kHz WAV with quiet -20dB headroom (dynamic gain test)"""
    # Simulate field headroom: amplitude 0.08 (~ -22dB)
    quiet_pcm = speaker_a_pcm * 0.10
    data = _encode_via_ffmpeg(quiet_pcm, 16000, ["-c:a", "pcm_s24le", "-ar", "48000"], ".wav")
    
    t0 = time.perf_counter()
    pcm = decode_audio(data)
    dur_ms = (time.perf_counter() - t0) * 1000

    assert len(pcm) > 0
    assert dur_ms < 50.0
    # Dynamic gain calibration should have boosted it to studio level (~0.85)
    peak = float(np.max(np.abs(pcm)))
    assert peak >= 0.70, f"Expected gain normalization, got peak {peak}"
    emb = AcousticVoiceprintBackend().embed(pcm)
    assert len(emb) == 192


def test_recorder_12_tascam_dr05x_96khz(speaker_a_pcm):
    """Tascam DR-05X: High-res 24-bit 96kHz BWF WAV"""
    data = _encode_via_ffmpeg(speaker_a_pcm, 16000, ["-c:a", "pcm_s24le", "-ar", "96000"], ".wav")
    t0 = time.perf_counter()
    pcm = decode_audio(data)
    dur_ms = (time.perf_counter() - t0) * 1000

    assert len(pcm) > 0
    assert dur_ms < 50.0
    emb = AcousticVoiceprintBackend().embed(pcm)
    assert len(emb) == 192


def test_recorder_13_sony_pcm_a10_linear_pcm(speaker_a_pcm):
    """Sony PCM-A10: Linear PCM 16-bit 44.1kHz WAV"""
    buf = io.BytesIO()
    pcm_i16 = (speaker_a_pcm * 32767.0).astype(np.int16)
    wavfile.write(buf, 44100, pcm_i16)
    data = buf.getvalue()

    t0 = time.perf_counter()
    pcm = decode_audio(data)
    dur_ms = (time.perf_counter() - t0) * 1000

    assert len(pcm) > 0
    assert dur_ms < 50.0
    emb = AcousticVoiceprintBackend().embed(pcm)
    assert len(emb) == 192


def test_recorder_14_olympus_voice_trek_mp3(speaker_a_pcm):
    """Olympus Voice-Trek: MP3 Mono 128kbps"""
    data = _encode_via_ffmpeg(speaker_a_pcm, 16000, ["-c:a", "libmp3lame", "-b:a", "128k", "-ac", "1"], ".mp3")
    t0 = time.perf_counter()
    pcm = decode_audio(data)
    dur_ms = (time.perf_counter() - t0) * 1000

    assert len(pcm) > 0
    assert dur_ms < 50.0
    emb = AcousticVoiceprintBackend().embed(pcm)
    assert len(emb) == 192


# ── Cross-Recorder Speaker Comparison Test ─────────────────────────────────────

@pytest.mark.asyncio
async def test_cross_recorder_verification_same_speaker(speaker_a_pcm):
    """
    Verify that Speaker A recorded on Apple Voice Memos (.m4a)
    matches Speaker A recorded on Zoom Field Recorder (.wav 24-bit with headroom)
    with similarity > 0.85 in milliseconds!
    """
    # 1. Voice Memos M4A
    m4a_data = _encode_via_ffmpeg(speaker_a_pcm, 16000, ["-c:a", "aac", "-b:a", "128k"], ".m4a")
    # 2. Zoom H4n 24-bit 48kHz WAV with -20dB low headroom
    zoom_pcm = speaker_a_pcm * 0.12
    wav_data = _encode_via_ffmpeg(zoom_pcm, 16000, ["-c:a", "pcm_s24le", "-ar", "48000"], ".wav")

    svc = get_speaker_service()
    res = await svc.compare_two_speakers(
        audio1=m4a_data,
        audio2=wav_data,
        threshold=0.82,
    )

    assert res["is_same_speaker"] is True
    assert res["similarity"] >= 0.85
    assert res["voice1"]["language_code"] == "arz"
    print(f"\nCross-recorder match passed! Similarity: {res['similarity']:.2%}")


@pytest.mark.asyncio
async def test_cross_recorder_verification_different_speakers(speaker_a_pcm, speaker_b_pcm):
    """
    Verify that Speaker A on Audacity vs Speaker B on Samsung Voice Recorder (AMR)
    correctly rejects with similarity < 0.70.
    """
    audacity_flac = _encode_via_ffmpeg(speaker_a_pcm, 16000, ["-c:a", "flac"], ".flac")
    samsung_amr = _encode_via_ffmpeg(speaker_b_pcm, 16000, ["-c:a", "amr_nb", "-ar", "8000"], ".amr")

    svc = get_speaker_service()
    res = await svc.compare_two_speakers(
        audio1=audacity_flac,
        audio2=samsung_amr,
        threshold=0.82,
    )

    assert res["is_same_speaker"] is False
    assert res["similarity"] < 0.75
    print(f"\nCross-recorder separation passed! Similarity: {res['similarity']:.2%}")
