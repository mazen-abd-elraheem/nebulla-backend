import re

# 1. Update voice_clone_service.py to auto-transcribe if transcript is not provided
with open("app/services/voice_clone/voice_clone_service.py", "r", encoding="utf-8") as f:
    vc_code = f.read()

old_txt_block = """        txt_dest = dest.with_suffix(".txt")
        if transcript and transcript.strip():
            txt_dest.write_text(transcript.strip(), encoding="utf-8")
            logger.info(f"Saved transcript for personality {personality_id}")
        elif txt_dest.exists():
            txt_dest.unlink()"""

new_txt_block = """        txt_dest = dest.with_suffix(".txt")
        if transcript and transcript.strip():
            txt_dest.write_text(transcript.strip(), encoding="utf-8")
            logger.info(f"Saved transcript for personality {personality_id}")
        else:
            # Auto-transcribe using Whisper STT on CUDA for maximum zero-shot cloning fidelity
            try:
                from app.providers.stt.factory import get_stt_provider
                stt = get_stt_provider("whisper")
                auto_txt = await stt.transcribe(dest.read_bytes())
                if auto_txt and auto_txt.strip():
                    txt_dest.write_text(auto_txt.strip(), encoding="utf-8")
                    logger.info(f"Auto-transcribed reference audio with Whisper for maximum cloning likeness: {auto_txt.strip()[:60]}...")
            except Exception as stt_err:
                logger.warning(f"Could not auto-transcribe reference audio: {stt_err}")"""

if old_txt_block in vc_code:
    vc_code = vc_code.replace(old_txt_block, new_txt_block)
    print("Updated upload_sample in voice_clone_service.py")
else:
    old_crlf = old_txt_block.replace("\n", "\r\n")
    new_crlf = new_txt_block.replace("\n", "\r\n")
    if old_crlf in vc_code:
        vc_code = vc_code.replace(old_crlf, new_crlf)
        print("Updated upload_sample (CRLF) in voice_clone_service.py")
    else:
        print("Target for upload_sample not found!")

with open("app/services/voice_clone/voice_clone_service.py", "w", encoding="utf-8") as f:
    f.write(vc_code)

# 2. Update app/api/v1/endpoints/voice_clone.py
with open("app/api/v1/endpoints/voice_clone.py", "r", encoding="utf-8") as f:
    vc_ep_code = f.read()

# Update SynthesizeRequest defaults
old_req = """class SynthesizeRequest(BaseModel):
    text: str
    voice_id: int | str | None = None
    personality_id: int | None = None
    language: str = "arz"
    ref_text: str | None = None
    num_steps: int | None = None
    guidance_scale: float | None = None
    speed: float | None = None"""

new_req = """class SynthesizeRequest(BaseModel):
    text: str = Field(..., description="النص العربي المراد تحويله إلى صوت")
    voice_id: int | str | None = Field(1, description="معرف الصوت المستنسخ (مثال: 1)")
    personality_id: int | None = Field(None, description="معرف الشخصية (اختياري)")
    language: str = Field("arz", description="اللهجة (arz للمصري)")
    ref_text: str | None = Field(None, description="نص العينة المرجعية (اختياري، يتم جلبه تلقائياً)")
    num_steps: int | None = Field(16, description="عدد خطوات التوليد (16 لجودة ونقاء صوت ونبرة ممتازة)")
    guidance_scale: float | None = Field(2.6, description="مقياس مطابقة نبرة الصوت المرجعي بدقة (2.5 - 2.8)")
    speed: float | None = Field(1.15, description="سرعة الكلام (1.15 للريتم الطبيعي السريع للعامية المصرية)")"""

if old_req in vc_ep_code:
    vc_ep_code = vc_ep_code.replace(old_req, new_req)
else:
    old_req_crlf = old_req.replace("\n", "\r\n")
    new_req_crlf = new_req.replace("\n", "\r\n")
    vc_ep_code = vc_ep_code.replace(old_req_crlf, new_req_crlf)

# Update post synthesize steps/guidance/speed fallback
old_post_call = """    actual_ref_text = body.ref_text if (body.ref_text and body.ref_text.strip() and body.ref_text.strip() != "string") else None
    steps = body.num_steps if (body.num_steps and body.num_steps > 0) else 4

    wav_bytes = await svc.synthesize(
        text=cleaned_text,
        personality_id=target_pid,
        language=body.language,
        ref_text=body.ref_text,
        num_step=body.num_steps,
        guidance_scale=body.guidance_scale,
        speed=body.speed,
    )"""

new_post_call = """    actual_ref_text = body.ref_text if (body.ref_text and body.ref_text.strip() and body.ref_text.strip() != "string") else None
    steps = body.num_steps if (body.num_steps and body.num_steps > 0) else 16
    cfg = body.guidance_scale if (body.guidance_scale and body.guidance_scale > 0) else 2.6
    spd = body.speed if (body.speed and body.speed > 0) else 1.15

    wav_bytes = await svc.synthesize(
        text=cleaned_text,
        personality_id=target_pid,
        language=body.language,
        ref_text=actual_ref_text,
        num_step=steps,
        guidance_scale=cfg,
        speed=spd,
    )"""

if old_post_call in vc_ep_code:
    vc_ep_code = vc_ep_code.replace(old_post_call, new_post_call)
else:
    old_post_crlf = old_post_call.replace("\n", "\r\n")
    new_post_crlf = new_post_call.replace("\n", "\r\n")
    vc_ep_code = vc_ep_code.replace(old_post_crlf, new_post_crlf)

# Update GET synthesize defaults
vc_ep_code = vc_ep_code.replace(
    'num_steps: int | None = Query(4, description="عدد خطوات التوليد (الافتراضي: 4 للسرعة)")',
    'num_steps: int | None = Query(16, description="عدد خطوات التوليد (الافتراضي: 16 لدقة النبرة والوضوح)"),\n    speed: float | None = Query(1.15, description="سرعة الكلام (الافتراضي: 1.15 للعامية المصرية)"),\n    guidance_scale: float | None = Query(2.6, description="مطابقة نبرة الصوت المستنسخ")'
)

with open("app/api/v1/endpoints/voice_clone.py", "w", encoding="utf-8") as f:
    f.write(vc_ep_code)

print("voice_clone.py endpoint patched successfully!")

