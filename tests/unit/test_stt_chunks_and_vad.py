import numpy as np
import pytest
from app.providers.stt.qwencleo import (
    _ensure_qwen_asr_transformers_compat,
    _merge_transcripts,
    _register_auto_class,
    _split_into_chunks,
    _trim_silence_array,
)
from app.services.voice_clone.voice_clone_service import trim_audio_silence


def test_silence_array_trimming():
    sr = 16000
    silence = np.zeros(sr * 3, dtype=np.float32)
    tone = 0.5 * np.sin(2 * np.pi * 440 * np.linspace(0, 2, sr * 2, dtype=np.float32))
    combined = np.concatenate([silence, tone, silence])
    trimmed, is_silent = _trim_silence_array(combined, sr)
    assert not is_silent, "Should not be detected as silent"
    dur = len(trimmed) / sr
    assert 1.8 <= dur <= 2.3, f"Expected ~2s audio, got {dur}"


def test_chunking_and_multithreading_support():
    sr = 16000
    tone = 0.5 * np.sin(2 * np.pi * 440 * np.linspace(0, 2, sr * 2, dtype=np.float32))
    long_tone = np.tile(tone, 10)  # 20 seconds
    chunks = _split_into_chunks(long_tone, sr, chunk_s=8.0, stride_s=1.0)
    assert len(chunks) >= 3, "20s audio should be partitioned into at least 3 chunks"


def test_merge_transcripts():
    chunks_txt = ["أهلاً بيك", "بيك في نيبولا", "في نيبولا يا صديقي"]
    merged = _merge_transcripts(chunks_txt)
    assert merged == "أهلاً بيك في نيبولا يا صديقي"


def test_pure_silence_detection():
    sr = 16000
    pure_silence = np.zeros(sr * 4, dtype=np.float32)
    trimmed, is_silent = _trim_silence_array(pure_silence, sr)
    assert is_silent is True
    assert len(trimmed) == 0


def test_qwen_asr_transformers_compat_layer():
    import importlib.util

    torch = pytest.importorskip("torch")
    pytest.importorskip("transformers")
    if importlib.util.find_spec("qwen_asr") is None:
        pytest.skip("qwen_asr package not installed")

    _ensure_qwen_asr_transformers_compat()
    _ensure_qwen_asr_transformers_compat()

    import transformers.modeling_rope_utils as mru
    from transformers import AutoConfig, AutoModel, AutoModelForSpeechSeq2Seq, AutoProcessor
    from transformers.utils.generic import check_model_inputs
    from qwen_asr import Qwen3ASRModel  # noqa: F401
    from qwen_asr.core.transformers_backend import (
        Qwen3ASRConfig,
        Qwen3ASRForConditionalGeneration,
        Qwen3ASRProcessor,
    )

    @check_model_inputs()
    def _dummy_forward(self, input_ids=None, **kwargs):
        return input_ids

    class _DummyCfg:
        output_attentions = False
        output_hidden_states = False
        use_return_dict = True

    class _DummyModel:
        config = _DummyCfg()

    assert _dummy_forward(_DummyModel(), input_ids=[1, 2]) == [1, 2]
    assert "default" in mru.ROPE_INIT_FUNCTIONS

    _register_auto_class(AutoConfig, "qwen3_asr", Qwen3ASRConfig)
    _register_auto_class(AutoModel, Qwen3ASRConfig, Qwen3ASRForConditionalGeneration)
    _register_auto_class(AutoModelForSpeechSeq2Seq, Qwen3ASRConfig, Qwen3ASRForConditionalGeneration)
    _register_auto_class(AutoProcessor, Qwen3ASRConfig, Qwen3ASRProcessor)

    cfg = Qwen3ASRConfig(
        thinker_config={
            "audio_config": {
                "d_model": 64,
                "encoder_layers": 1,
                "encoder_attention_heads": 2,
                "encoder_ffn_dim": 128,
                "downsample_hidden_size": 64,
                "output_dim": 64,
            },
            "text_config": {
                "vocab_size": 256,
                "hidden_size": 64,
                "intermediate_size": 128,
                "num_hidden_layers": 1,
                "num_attention_heads": 2,
                "num_key_value_heads": 2,
                "head_dim": 32,
                "use_cache": True,
                "tie_word_embeddings": True,
                "rope_scaling": {"rope_type": "default", "mrope_section": [8, 4, 4]},
            },
        }
    )
    assert getattr(cfg.thinker_config, "tie_word_embeddings", False) is True

    model = Qwen3ASRForConditionalGeneration(cfg)
    model.eval()
    assert model.thinker.lm_head.weight.data_ptr() == model.thinker.model.embed_tokens.weight.data_ptr()

    inp_ids = torch.tensor([[1, 2, 3]], dtype=torch.long)
    attn = torch.ones_like(inp_ids)
    with torch.no_grad():
        out = model.generate(
            input_ids=inp_ids,
            attention_mask=attn,
            max_new_tokens=2,
            input_features_mask=None,
        )
    assert out.sequences.shape == (1, 5)


