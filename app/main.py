"""
Nebula Backend — Digital Twin Robot
FastAPI application entry point.

Architecture: Phone/Desk/ESP32 all connect to THIS backend.
No device talks to another device directly (design decision from doc §4).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logger import get_logger
from app.api.v1.router import api_router
from app.websocket.hub import router as ws_router
from app.db.session import init_db

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("Nebula backend starting up...")
    await init_db()
    yield
    logger.info("Nebula backend shutting down...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "Backend for the Nebula Digital-Twin Robot. "
        "Connects the Flutter phone app (face), the Flutter desktop app (control room), "
        "and the ESP32 firmware via WebSocket channels. "
        "Runs the AI pipeline: STT → LLM → TTS with streaming, "
        "UniFace vision, RAG memory, motion guard, and signal planner."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — local-network only (doc §6, security: local Wi-Fi, no open internet)
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(api_router, prefix="/api/v1")   # REST endpoints
app.include_router(ws_router)                       # WebSocket hub (ws/phone, ws/desk, ws/esp)


from fastapi.responses import HTMLResponse, RedirectResponse

@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "version": settings.VERSION}


@app.get("/demo", response_class=HTMLResponse, include_in_schema=False)
async def voice_clone_demo():
    """Interactive web page to test cloned voice directly in browser."""
    html_content = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Nebula - استنساخ الصوت الحي</title>
    <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0d0f17;
            --card: rgba(22, 27, 44, 0.75);
            --border: rgba(99, 102, 241, 0.25);
            --primary: #6366f1;
            --primary-hover: #4f46e5;
            --accent: #06b6d4;
            --accent-green: #10b981;
            --text: #f8fafc;
            --text-muted: #94a3b8;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Cairo', sans-serif;
            background: radial-gradient(circle at top, #1e223f 0%, var(--bg) 75%);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 25px 15px;
        }
        .container {
            max-width: 650px;
            width: 100%;
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 24px;
            padding: 35px 30px;
            backdrop-filter: blur(20px);
            box-shadow: 0 25px 60px rgba(0,0,0,0.6), 0 0 50px rgba(99, 102, 241, 0.15);
        }
        .badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: rgba(99, 102, 241, 0.15);
            border: 1px solid var(--border);
            padding: 6px 16px;
            border-radius: 25px;
            font-size: 0.88rem;
            color: var(--accent);
            margin-bottom: 12px;
            font-weight: 600;
        }
        h1 {
            font-size: 1.85rem;
            font-weight: 800;
            margin-bottom: 6px;
            background: linear-gradient(135deg, #ffffff 40%, var(--accent) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        p.subtitle {
            color: var(--text-muted);
            font-size: 0.95rem;
            margin-bottom: 25px;
            line-height: 1.6;
        }
        .card-section {
            background: rgba(13, 15, 23, 0.6);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 22px;
        }
        .section-title {
            font-size: 1.05rem;
            font-weight: 700;
            color: #e2e8f0;
            margin-bottom: 14px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            margin-bottom: 7px;
            font-weight: 600;
            font-size: 0.9rem;
            color: #cbd5e1;
        }
        input[type="text"], input[type="file"], textarea {
            width: 100%;
            background: rgba(10, 12, 20, 0.85);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 12px 14px;
            color: var(--text);
            font-family: inherit;
            font-size: 0.95rem;
            outline: none;
            transition: all 0.2s;
        }
        textarea {
            height: 95px;
            resize: none;
            font-size: 1.05rem;
        }
        input[type="file"] {
            padding: 8px 12px;
            cursor: pointer;
            color: var(--text-muted);
        }
        input:focus, textarea:focus {
            border-color: var(--primary);
            box-shadow: 0 0 15px rgba(99, 102, 241, 0.35);
        }
        .btn-action {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--accent) 100%);
            border: none;
            border-radius: 12px;
            color: white;
            font-size: 1.05rem;
            font-weight: 700;
            font-family: inherit;
            cursor: pointer;
            transition: all 0.2s;
            box-shadow: 0 6px 20px rgba(99, 102, 241, 0.35);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
        }
        .btn-action:hover {
            opacity: 0.95;
            transform: translateY(-2px);
            box-shadow: 0 10px 25px rgba(99, 102, 241, 0.5);
        }
        .btn-secondary {
            background: rgba(99, 102, 241, 0.2);
            border: 1px solid var(--border);
            color: #fff;
            padding: 10px 16px;
            font-size: 0.9rem;
            box-shadow: none;
        }
        .btn-secondary:hover {
            background: rgba(99, 102, 241, 0.4);
            transform: translateY(-1px);
        }
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none !important;
        }
        .status-msg {
            margin-top: 14px;
            font-size: 0.92rem;
            text-align: center;
            min-height: 22px;
            color: var(--text-muted);
        }
        .result-box {
            margin-top: 20px;
            padding: 20px;
            background: rgba(10, 12, 20, 0.85);
            border: 1px solid rgba(6, 182, 212, 0.4);
            border-radius: 16px;
            display: none;
        }
        .result-header {
            font-weight: 700;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--accent);
        }
        audio {
            width: 100%;
            margin-bottom: 12px;
            outline: none;
            border-radius: 10px;
        }
        .actions {
            display: flex;
            gap: 10px;
        }
        .btn-download {
            flex: 1;
            padding: 10px;
            background: rgba(6, 182, 212, 0.15);
            border: 1px solid rgba(6, 182, 212, 0.3);
            border-radius: 8px;
            color: #fff;
            font-family: inherit;
            font-weight: 600;
            font-size: 0.9rem;
            text-decoration: none;
            text-align: center;
            transition: all 0.2s;
        }
        .btn-download:hover {
            background: rgba(6, 182, 212, 0.35);
        }
        .spinner {
            display: inline-block;
            width: 18px;
            height: 18px;
            border: 3px solid rgba(255,255,255,0.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 0.8s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .tag-ok {
            background: rgba(16, 185, 129, 0.2);
            color: #34d399;
            padding: 2px 10px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 700;
            border: 1px solid rgba(16, 185, 129, 0.4);
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="badge">🎙️ Nebula Voice Twin • استنساخ الصوت الحي</div>
        <h1>استمع لصوتك المستنسخ</h1>
        <p class="subtitle">اكتب أي جملة بالمصري واضغط توليد لسماعها بصوتك المستنسخ فوراً، أو ارفع عينة صوت/فيديو جديدة لاستنساخ صوت آخر!</p>

        <!-- Section 1: Upload or Choose Voice Sample -->
        <div class="card-section">
            <div class="section-title">
                <span>🎙️ مصدر الصوت للاستنساخ:</span>
                <span class="tag-ok" id="activeSampleTag">عينة نشطة جاهزة ✓</span>
            </div>
            
            <div class="form-group">
                <label for="voiceFile">اختر ملف الصوت أو الريك أو الفيديو (WAV, MP3, M4A, MP4, AAC, OGG, Opus):</label>
                <input type="file" id="voiceFile" accept="audio/*,video/*,.wav,.mp4,.m4a,.mp3,.webm,.ogg,.aac,.opus,.flac,.3gp,.amr">
            </div>

            <!-- Preview box for selected file -->
            <div id="selectedPreviewBox" style="display: none; margin-bottom: 15px; padding: 12px; background: rgba(99, 102, 241, 0.1); border-radius: 10px; border: 1px dashed var(--accent);">
                <div id="previewFileName" style="font-size: 0.88rem; color: var(--accent); margin-bottom: 8px; font-weight: 600;"></div>
                <audio id="previewAudio" controls style="height: 38px;"></audio>
            </div>

            <div class="form-group">
                <label for="voiceTranscript">ما قيل في التسجيل (اختياري، كتابته ترفع دقة مخارج الحروف لأقصى حد):</label>
                <input type="text" id="voiceTranscript" placeholder="مثال: الكلام اللي صاحب الصوت بيقوله في الريكورد...">
            </div>
            <div id="uploadStatus" class="status-msg" style="min-height: 10px; margin-top: 5px;"></div>
        </div>

        <!-- Section 2: Synthesize in Cloned Voice -->
        <div class="card-section">
            <div class="section-title">
                <span>✍️ اكتب النص المطلوب نطقه بالصوت:</span>
            </div>
            <div class="form-group">
                <textarea id="textInput" placeholder="اكتب جملتك هنا بالمصري...">أهلاً بيكم يا شباب، ده الصوت الجديد المستنسخ وشغال مية مية!</textarea>
            </div>

            <button id="genBtn" class="btn-action" onclick="generateVoice()">
                <span id="btnIcon">⚡</span>
                <span id="btnText">استنساخ ونطق بالصوت</span>
            </button>

            <div id="statusMsg" class="status-msg"></div>

            <div id="resultBox" class="result-box">
                <div class="result-header">🔊 المقطع الصوتي المنطوق بالصوت المستنسخ:</div>
                <audio id="audioPlayer" controls autoplay></audio>
                <div class="actions">
                    <a id="downloadLink" class="btn-download" href="#" download="cloned_voice.wav">📥 تنزيل الملف الصوتي (WAV)</a>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Audio preview when file is selected
        document.getElementById('voiceFile').addEventListener('change', function(e) {
            const previewBox = document.getElementById('selectedPreviewBox');
            const previewAudio = document.getElementById('previewAudio');
            const previewName = document.getElementById('previewFileName');
            const activeTag = document.getElementById('activeSampleTag');

            if (this.files && this.files[0]) {
                const file = this.files[0];
                previewAudio.src = URL.createObjectURL(file);
                previewName.innerText = '🎵 الريك المختار: ' + file.name + ' (' + (file.size / 1024).toFixed(1) + ' KB)';
                previewBox.style.display = 'block';
                activeTag.innerText = 'سيتم استنساخ هذا الريك الجديد ⚡';
                activeTag.style.background = 'rgba(6, 182, 212, 0.2)';
                activeTag.style.color = '#38bdf8';
            } else {
                previewBox.style.display = 'none';
            }
        });

        async function uploadVoiceSampleDirect(file, transcript) {
            const formData = new FormData();
            formData.append('file', file);
            if (transcript && transcript.trim()) {
                formData.append('transcript', transcript.trim());
            }

            const res = await fetch('/api/v1/voice-clone/upload/1', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.detail || 'فشل رفع ملف الصوت');
            }
            return data;
        }

        async function generateVoice() {
            const text = document.getElementById('textInput').value.trim();
            if (!text) {
                alert('من فضلك اكتب نصاً للتوليد');
                return;
            }

            const btn = document.getElementById('genBtn');
            const btnText = document.getElementById('btnText');
            const btnIcon = document.getElementById('btnIcon');
            const statusMsg = document.getElementById('statusMsg');
            const resultBox = document.getElementById('resultBox');
            const audioPlayer = document.getElementById('audioPlayer');
            const downloadLink = document.getElementById('downloadLink');
            const fileInput = document.getElementById('voiceFile');
            const transcriptInput = document.getElementById('voiceTranscript');

            btn.disabled = true;
            btnIcon.innerHTML = '<span class="spinner"></span>';
            resultBox.style.display = 'none';

            try {
                // 1. If a new voice file is selected, automatically upload and convert it first!
                if (fileInput.files && fileInput.files.length > 0) {
                    const chosenFile = fileInput.files[0];
                    btnText.innerText = 'جاري استيراد الريك الجديد...';
                    statusMsg.innerHTML = '⏳ جاري استخراج صوت الريك (' + chosenFile.name + ') وضبطه للاستنساخ...';
                    
                    await uploadVoiceSampleDirect(chosenFile, transcriptInput.value);

                    document.getElementById('activeSampleTag').innerText = 'تم اعتماد الريك الجديد ✓';
                    document.getElementById('activeSampleTag').style.background = 'rgba(16, 185, 129, 0.2)';
                    document.getElementById('activeSampleTag').style.color = '#34d399';
                }

                // 2. Synthesize text in cloned voice
                btnText.innerText = 'جاري توليد الكلام بالصوت المستنسخ...';
                statusMsg.innerHTML = '⏳ جاري نطق الكلام بالصوت المستنسخ على كارت الشاشة، ثواني...';

                const response = await fetch('/api/v1/voice-clone/synthesize', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        text: text,
                        personality_id: 1,
                        language: 'ar'
                    })
                });

                if (!response.ok) {
                    const errJson = await response.json().catch(() => ({}));
                    throw new Error(errJson.detail || ('فشل الطلب: كود ' + response.status));
                }

                const blob = await response.blob();
                const audioUrl = URL.createObjectURL(blob);

                audioPlayer.src = audioUrl;
                audioPlayer.load();
                audioPlayer.play().catch(e => console.log('Autoplay prevented'));

                downloadLink.href = audioUrl;
                resultBox.style.display = 'block';
                statusMsg.innerHTML = '<span style="color: #34d399; font-weight: bold;">✅ تم الاستنساخ والنطق بنجاح! تم تشغيل الصوت ويمكنك تنزيله بالأسفل.</span>';
            } catch (err) {
                console.error(err);
                statusMsg.innerHTML = '<span style="color: #f87171;">❌ خطأ: ' + err.message + '</span>';
            } finally {
                btn.disabled = false;
                btnIcon.innerText = '⚡';
                btnText.innerText = 'استنساخ ونطق بالصوت';
            }
        }
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/demo")
