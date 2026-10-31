with open("app/providers/tts/voicetut.py", "r", encoding="utf-8") as f:
    code = f.read()

# Fix missing imports at top
old_imp = """import asyncio
import io
import wave
from app.providers.tts.base import BaseTTSProvider"""

new_imp = """import asyncio
import io
import os
from pathlib import Path
import wave
import torch
from app.providers.tts.base import BaseTTSProvider"""

if old_imp in code:
    code = code.replace(old_imp, new_imp, 1)
    print("Replaced top imports in voicetut.py")
else:
    # Try with CRLF
    old_imp_crlf = old_imp.replace("\n", "\r\n")
    new_imp_crlf = new_imp.replace("\n", "\r\n")
    if old_imp_crlf in code:
        code = code.replace(old_imp_crlf, new_imp_crlf, 1)
        print("Replaced top imports (CRLF) in voicetut.py")
    else:
        print("Could not find top imports target, prepending 'import os'...")
        code = "import os\n" + code

# Adjust default parameters in _synth for high quality cloning:
# default_steps = 16, cfg = 2.6, spd = 1.15
code = code.replace(
    'default_steps = getattr(settings, "VOICETUT_NUM_STEPS", 36)',
    'default_steps = getattr(settings, "VOICETUT_NUM_STEPS", 16)'
)
code = code.replace(
    'cfg = guidance_scale or getattr(settings, "VOICETUT_GUIDANCE_SCALE", 2.2)',
    'cfg = guidance_scale or getattr(settings, "VOICETUT_GUIDANCE_SCALE", 2.6)'
)
code = code.replace(
    'spd = speed or getattr(settings, "VOICETUT_SPEED", 1.0)',
    'spd = speed or getattr(settings, "VOICETUT_SPEED", 1.15)'
)

with open("app/providers/tts/voicetut.py", "w", encoding="utf-8") as f:
    f.write(code)

print("voicetut.py patched successfully!")

