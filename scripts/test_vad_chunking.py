import io
import time
import numpy as np
import soundfile as sf

def trim_silence(
    audio: np.ndarray,
    sample_rate: int,
    threshold_db: float = -42.0,
    padding_ms: int = 150,
) -> tuple[np.ndarray, bool]:
    """
    Trims leading and trailing silence using short-term RMS energy.
    Prevents waiting on empty audio / long silent lead-ins.
    """
    if len(audio) == 0:
        return audio, False

    # 25ms frame size, 10ms hop
    frame_length = int(sample_rate * 0.025)
    hop_length = int(sample_rate * 0.010)
    
    if len(audio) < frame_length:
        return audio, True

    # Frame energy (RMS)
    num_frames = 1 + (len(audio) - frame_length) // hop_length
    frames = np.lib.stride_tricks.as_strided(
        audio,
        shape=(num_frames, frame_length),
        strides=(audio.strides[0] * hop_length, audio.strides[0]),
    )
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(np.maximum(rms, 1e-6))

    # Mask of active speech
    active = db > threshold_db
    if not np.any(active):
        return np.array([], dtype=audio.dtype), False

    first_frame = np.argmax(active)
    last_frame = len(active) - 1 - np.argmax(active[::-1])

    pad_samples = int(sample_rate * (padding_ms / 1000.0))
    start_sample = max(0, first_frame * hop_length - pad_samples)
    end_sample = min(len(audio), last_frame * hop_length + frame_length + pad_samples)

    return audio[start_sample:end_sample], True

def split_into_speech_chunks(
    audio: np.ndarray,
    sample_rate: int,
    max_chunk_duration_s: float = 7.0,
    min_chunk_duration_s: float = 2.0,
    silence_threshold_db: float = -40.0,
) -> list[np.ndarray]:
    """
    Splits long audio into speech chunks based on natural pauses.
    """
    total_duration = len(audio) / sample_rate
    if total_duration <= max_chunk_duration_s:
        return [audio]

    frame_length = int(sample_rate * 0.025)
    hop_length = int(sample_rate * 0.010)
    num_frames = 1 + (len(audio) - frame_length) // hop_length

    frames = np.lib.stride_tricks.as_strided(
        audio,
        shape=(num_frames, frame_length),
        strides=(audio.strides[0] * hop_length, audio.strides[0]),
    )
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(np.maximum(rms, 1e-6))
    is_silent = db <= silence_threshold_db

    max_samples = int(max_chunk_duration_s * sample_rate)
    min_samples = int(min_chunk_duration_s * sample_rate)

    chunks = []
    curr_start = 0
    total_len = len(audio)

    while curr_start < total_len:
        if total_len - curr_start <= max_samples:
            chunks.append(audio[curr_start:])
            break

        # Search for silence dip between min_samples and max_samples
        search_start_sample = curr_start + min_samples
        search_end_sample = min(total_len, curr_start + max_samples)
        
        search_start_frame = search_start_sample // hop_length
        search_end_frame = min(len(is_silent), search_end_sample // hop_length)

        split_sample = None
        if search_start_frame < search_end_frame:
            window = is_silent[search_start_frame:search_end_frame]
            silent_indices = np.where(window)[0]
            if len(silent_indices) > 0:
                # Pick silence closest to the middle of the window
                target = len(window) // 2
                best_idx = silent_indices[np.argmin(np.abs(silent_indices - target))]
                split_sample = (search_start_frame + best_idx) * hop_length

        if split_sample is None:
            # Hard split if no silence found
            split_sample = curr_start + max_samples

        chunks.append(audio[curr_start:split_sample])
        curr_start = split_sample

    return chunks

# Test simulation with silence padding
if __name__ == "__main__":
    sr = 16000
    # Simulate: 3 seconds of dead silence + 4 seconds of speech + 2 seconds of silence
    t = np.linspace(0, 4, 4 * sr)
    speech = 0.5 * np.sin(2 * np.pi * 440 * t) # audible sound
    leading_silence = np.random.normal(0, 0.001, 3 * sr) # quiet noise (-60dB)
    trailing_silence = np.random.normal(0, 0.001, 2 * sr)
    simulated_rec = np.concatenate([leading_silence, speech, trailing_silence])

    print(f"Original recording duration: {len(simulated_rec)/sr:.2f}s (3s silence + 4s speech + 2s silence)")
    
    t0 = time.perf_counter()
    trimmed, has_speech = trim_silence(simulated_rec, sr)
    dt = (time.perf_counter() - t0) * 1000
    
    print(f"Trimmed duration: {len(trimmed)/sr:.2f}s, took {dt:.2f}ms to detect and strip silence!")
    print(f"Saved { (len(simulated_rec) - len(trimmed))/sr :.2f}s of wasted audio processing!")
    
    # Test chunking
    chunks = split_into_speech_chunks(trimmed, sr, max_chunk_duration_s=2.5)
    print(f"Split into {len(chunks)} chunks for parallel multithreaded processing:")
    for i, c in enumerate(chunks):
        print(f"  Chunk {i}: {len(c)/sr:.2f}s")
