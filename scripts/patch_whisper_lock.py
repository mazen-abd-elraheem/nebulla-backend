import pathlib

p = pathlib.Path("app/providers/stt/whisper.py")
c = p.read_text(encoding="utf-8")

if "import threading" not in c:
    c = c.replace("import tempfile", "import tempfile\nimport threading")

if "_shared_thread_lock" not in c:
    c = c.replace(
        "_shared_lock = asyncio.Lock()",
        "_shared_lock = asyncio.Lock()\n    _shared_thread_lock = threading.Lock()\n    _shared_infer_lock = threading.Lock()"
    )

if "with WhisperProvider._shared_infer_lock:" not in c:
    old_call = """            result = self._model.transcribe(
                tmp_path,
                language=lang,
                fp16=use_fp16,
                beam_size=1,
                best_of=1,
                temperature=0.0,
                condition_on_previous_text=False,
            )"""

    new_call = """            with WhisperProvider._shared_infer_lock:
                result = self._model.transcribe(
                    tmp_path,
                    language=lang,
                    fp16=use_fp16,
                    beam_size=1,
                    best_of=1,
                    temperature=0.0,
                    condition_on_previous_text=False,
                )"""
    c = c.replace(old_call, new_call)

p.write_text(c, encoding="utf-8")
print("Whisper thread safety locks applied successfully!")
