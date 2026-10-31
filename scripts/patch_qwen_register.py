import pathlib

p = pathlib.Path(r"D:\nebula_venv\Lib\site-packages\qwen_asr\inference\qwen3_asr.py")
if p.exists():
    c = p.read_text(encoding="utf-8")
    c = c.replace(
        'AutoConfig.register("qwen3_asr", Qwen3ASRConfig)',
        'AutoConfig.register("qwen3_asr", Qwen3ASRConfig, exist_ok=True)'
    )
    c = c.replace(
        'AutoModel.register(Qwen3ASRConfig, Qwen3ASRForConditionalGeneration)',
        'AutoModel.register(Qwen3ASRConfig, Qwen3ASRForConditionalGeneration, exist_ok=True)'
    )
    c = c.replace(
        'AutoProcessor.register(Qwen3ASRConfig, Qwen3ASRProcessor)',
        'AutoProcessor.register(Qwen3ASRConfig, Qwen3ASRProcessor, exist_ok=True)'
    )
    p.write_text(c, encoding="utf-8")
    print("qwen3_asr.py patched successfully!")
