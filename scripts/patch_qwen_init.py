import pathlib

init_p = pathlib.Path(r"D:\nebula_venv\Lib\site-packages\qwen_asr\__init__.py")
if init_p.exists():
    c = init_p.read_text(encoding="utf-8")
    target = "from .inference.qwen3_forced_aligner import Qwen3ForcedAligner"
    replacement = """try:
    from .inference.qwen3_forced_aligner import Qwen3ForcedAligner
except Exception:
    Qwen3ForcedAligner = None"""
    if target in c:
        c = c.replace(target, replacement)
        init_p.write_text(c, encoding="utf-8")
        print("Patched __init__.py")

print("Patch complete!")
