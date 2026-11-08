# Handoff Report — Explorer Survey 3 (Language Unification Explorer - arz)

## 1. Observation
Across the codebase, the following language distributions and structures were directly observed:

1. **Project Documentation**:
   - `README.md` (lines 1–279): 100% written in technical English. Describes architecture, folder structure, quick start, endpoints, and safety features. Example:
     ```markdown
     Line 1: # 🤖 Nebula Backend — Digital Twin Robot
     Line 3: **FastAPI backend for the Nebula Digital Twin Robot project (v3.0)**
     ```
   - `read me/nebula_architecture.md` (lines 1–195): 100% written in technical English. Includes system topology, inventory of all 79 Python files, REST endpoints, auth flow, and latency budget.
   - `nebula-frontend-main/README.md` (line 1): Only `# nebula-frontend`.
   - `nebula-frontend-main/nebulla/README.md` (lines 1–18): Default Flutter boilerplate in English.

2. **Frontend UI Components & Templates**:
   - `nebula-frontend-main/nebulla/lib/screens/login_screen.dart` (lines 67, 75, 86, 117, 193, 204, 376, 537, 608, 620, 703, 740, 756, 809, 863, 904, 960, 984, 988, 1044, 1056, 1075): Written in formal Modern Standard Arabic (MSA / الفصحى), such as:
     - Line 67: `'تم تسجيل الدخول بنجاح. أهلاً بك يا ${user.fullName}'`
     - Line 86: `'يرجى إدخال البريد الإلكتروني أولاً للتحقق من بصمة الوجه.'`
     - Line 537: `'البريد الإلكتروني أو المعرّف'`
     - Line 740: `'تذكّرني على هذا الجهاز'`
     - Line 756: `'نسيت كلمة المرور؟'`
     - Line 863: `'تسجيل الدخول عبر التعرّف البيومتري (Neural Face ID)'`
     - Line 904: `'ليس لديك حساب؟ إنشاء حساب جديد'`
   - `nebula-frontend-main/nebulla/lib/screens/register_screen.dart` (lines 42, 59, 178, 336, 347, 356, 366, 369, 379, 392, 402, 416, 585, 616): Uses formal MSA (e.g., `'كلمة المرور وتأكيد كلمة المرور غير متطابقين.'`, `'الاسم الكامل'`, `'يرجى إدخال الاسم الكامل (حرفين على الأقل)'`).
   - `nebula-frontend-main/nebulla/lib/screens/main_shell.dart` (lines 28–34): Bottom navigation bar uses MSA (`'الرئيسية'`, `'المحادثة'`, `'الشخصيات'`, `'التشخيص'`, `'الإعدادات'`).
   - `nebula-frontend-main/nebulla/lib/screens/dashboard_screen.dart` (lines 97, 122, 172–183, 228, 270, 277, 309, 334): Contains mixed MSA headers (`'حالة الاتصال'`, `'الهاتف'`, `'سطح المكتب'`, `'متصل / غير متصل'`, `'الشخصية النشطة'`, `'لا توجد شخصية نشطة'`, `'نظرة عامة'`).
   - `nebula-frontend-main/nebulla/lib/screens/chat_screen.dart` (lines 125, 148, 204, 210, 461): Uses `'محادثة نيبولا'`, `'محادثة جديدة'`, `'ابدأ محادثتك مع نيبولا'`, `'اكتب رسالتك...'`.
   - `nebula-frontend-main/nebulla/lib/screens/diagnostics_screen.dart` (lines 48, 100–102, 198, 219, 234, 282, 302, 405, 469, 583–635, 755): Technical hardware controls in MSA and English ('السيرفو', 'معرّف السيرفو', 'موضع البيت', 'مستشعر المسافة', 'اختبار المحركات', 'التحكم بـ LED', 'إعادة الكل لموضع البيت').
   - `app/templates/chat_ui.html` (lines 6, 467, 474, 506–510, 536, 544, 553, 563, 565, 575, 592, 598, 609, 636, 645, 652, 703, 729): Contains Egyptian conversational prompts (`'مين أنت وعرف نفسك بالمصري؟'`, `'شايف مين قدامك دلوقتي؟'`, `'أهلاً يا باشا! أنا الروبوت نيبولا...'`), but still contains MSA & English in side panels, diagnostic indicators, and button controls (`'جاري التفكير والتوليد... ⏳'`, `'جلسة جديدة'`, `'تدفق مباشر (Streaming)'`).
   - `app/static/faces_studio.html`: Standalone video face match studio with titles and table headers in formal MSA and English.

3. **Backend User-Facing Strings & API Responses**:
   - `app/auth/router.py`:
     - Line 116: `detail="البريد الإلكتروني مسجل بالفعل. يرجى تسجيل الدخول أو استخدام بريد آخر."`
     - Line 176: `detail="البريد الإلكتروني أو كلمة المرور غير صحيحة."`
     - Line 183: `detail="هذا الحساب معطل حالياً. يرجى التواصل مع الدعم الفني."`
     - Line 238: `detail="لم يتم العثور على حساب بهذا البريد الإلكتروني."`
     - Line 244: `detail="بصمة الوجه (Neural Face ID) غير مفعلة لهذا الحساب بعد. سجل الدخول بكلمة المرور لتفعيلها."`
     - Line 252: `detail="حجم صورة الوجه يتجاوز الحد المسموح به (5 ميجابايت)."`
     - Line 258: `detail="صيغة الصورة غير مدعومة. يرجى التقاط صورة بصيغة JPEG أو PNG."`
     - Line 266: `detail="تعذر العثور على بصمة الوجه المسجلة للحساب."`
     - Line 279: `detail="لم يتم اكتشاف وجه واضح في الصورة. يرجى توجيه الكاميرا جيداً وإعادة المحاولة."`
     - Line 292: `detail="فشل التحقق: بصمة الوجه غير متطابقة مع بيانات الحساب المسجلة."`
     - Line 440: `detail="رمز استعادة كلمة المرور غير صالح أو انتهت صلاحيته."`
     - Line 453: `message="تمت إعادة تعيين كلمة المرور بنجاح. يمكنك الآن تسجيل الدخول بكلمة المرور الجديدة."`
     - Line 489: `detail="Invalid pairing code"` (English)
   - `app/auth/jwt.py`:
     - Line 55: `detail="Token expired"`
     - Line 57: `detail="Invalid token"`
     - Line 93: `detail="Invalid API key"`
     - Line 113: `detail="No credentials provided. Use X-API-Key or Bearer token."`
     - Line 149: `detail="User account is deactivated."`
     - Line 176: `detail="User associated with token not found."`
   - `app/auth/schemas.py`: Pydantic `ValueError` exceptions in MSA (lines 57, 69, 71, 73, 79, 81, 132, 142).
   - `app/core/security.py` line 24: `detail="Command rate limit exceeded"`.
   - `app/api/v1/endpoints/personalities.py` lines 86, 99, 106, 121, 126, 132, 143, 157, 162, 168, 188: English error details (e.g. `"Personality not found"`, `"You do not have permission to access this personality."`, `"Cannot modify a global system default personality."`).
   - `app/api/v1/endpoints/memories.py` lines 142, 167, 180, 192: Mix of English details and responses (`"Memory content cannot be empty..."`, `"Memory added and embedded successfully"`, `"Not found"`).
   - `app/api/v1/endpoints/devices.py` lines 45, 57: `"Device not found"`.
   - `app/api/v1/endpoints/signals.py` lines 48, 60: `f"Signal {name!r} not found"`, `"Not found"`.
   - `app/api/v1/endpoints/calibration.py` line 55: `"Home command sent to all servos"`.
   - `app/api/v1/endpoints/diagnostics.py` lines 52, 60, 70, 78, 84, 94, 108, 117, 119, 131: `"ESP32 not connected"`, `"Emergency stop sent to all channels"`.
   - `app/api/v1/endpoints/conversations.py` line 138: `"Message cannot be empty"`, line 416: `"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"`.
   - `app/api/v1/endpoints/voice_clone.py` lines 142, 193, 198, 244: `"Sample not found"`, `"Text cannot be empty."`, `"Received text has no pronounceable characters."`, `"Voice cloning failed to produce valid audio output."`.

4. **AI Persona Prompts & Default System Messages**:
   - `app/services/ai/context_builder.py` (lines 256–406):
     - Lines 328–345 & 367–406: Entire branches generating English system prompts when non-Arabic text is processed (`"You are {robot_name}, digital twin robot created by {creator_name}... Verified Memory Sources... STRICT ZERO-HALLUCINATION DIRECTIVES..."`).
     - Line 290–316: Egyptian Arabic directives already present for missing memory, but require expansion under Requirement R3 with strict zero-hallucination guardrails forbidding the local LLM from generating or hallucinating memories outside retrieved RAG context.
   - `app/services/ai/pipeline.py` (line 763): Fallback personality system prompt `"أنت توأم رقمي مصري."`.
   - `Modelfile.nebula-masri` (lines 13–44): System prompt written in English with operational rules and action tags (`"You are 'Nebula', an intelligent digital-twin physical robot created and developed by Mazen Abdelraheem..."`).
   - `Modelfile.nebula-llama3` (lines 13–31): System prompt written in English with strict operational rules in English.
   - `Modelfile.nebula-rag` (lines 17–33): System prompt written in English with few-shot examples.
   - `Modelfile.nebula-nile` (lines 24–34): Written in Arabic, but uses formal MSA phrasing.
   - `app/db/session.py` (lines 172–183 & 198–207): Seeded Personality 1 (Mazen) and personalized RAG memories.

## 2. Logic Chain
1. *Observation 1 (Documentation)* shows that both `README.md` and `read me/nebula_architecture.md` are 100% in English, creating a disconnect with the requirement to unify the project to Egyptian Arabic (`arz`).
2. *Observation 2 (Frontend)* shows that while some Egyptian Arabic phrases exist in `chat_ui.html`, all Flutter UI screens (Auth, Dashboard, Shell, Diagnostics, Faces, Personalities, Settings, Signals) are implemented using formal MSA or English.
3. *Observation 3 (Backend API)* shows that `HTTPException` detail strings and status messages are split between English and formal MSA, causing inconsistent error messages in the client toasts and snackbars.
4. *Observation 4 (AI Prompts & Context Builder)* demonstrates that `context_builder.py` branches into English and lacks the comprehensive Egyptian Arabic grounding directives required by R1 and R3, while Ollama Modelfiles have English system prompts.
5. Therefore, a complete unification requires:
   - Converting project documentation to authentic Egyptian Arabic (`arz`).
   - Refactoring frontend UI text, error toasts, and navigation strings to Egyptian Arabic.
   - Standardizing backend HTTP exception details and responses to Egyptian Arabic.
   - Expanding `context_builder.py` and Modelfiles with detailed Egyptian Arabic instructions strictly grounding the local LLM to RAG memories and forbidding hallucinations.

## 3. Caveats
- Technical identifiers, protocol names, HTTP headers, and API paths (`/api/v1/...`, `Bearer`, `X-API-Key`, `Content-Type`, `ESP32`, `QwenCleo`, `XTTS v2`, `UniFace`) must remain in their standard ASCII format to maintain network protocol interoperability.
- Existing tests in `tests/integration/test_user_auth_endpoints.py` assert `assert "مسجل بالفعل" in res_dup.json()["detail"]`. Proposed Egyptian Arabic translations intentionally keep `"مسجل بالفعل"` (e.g. `"الإيميل ده مسجل بالفعل عندنا. سجّل دخولك على طول أو استخدم إيميل تاني."`) to prevent breaking existing test assertions.

## 4. Conclusion
The codebase is ready for unified transformation to authentic Egyptian Arabic (`arz`). A detailed inventory of every affected file, line number range, current string, and exact replacement translation has been compiled and documented in:
`c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\explorer_survey_3\survey_report.md`.

## 5. Verification Method
1. Read the full survey report:
   `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\explorer_survey_3\survey_report.md`
2. Inspect the observed files and lines documented above using `view_file` to confirm line content matches.
3. Invalidation conditions: If any user-facing endpoint or UI screen is found that was omitted from the survey report, or if any proposed translation violates authentic Cairo Egyptian Arabic idioms.
