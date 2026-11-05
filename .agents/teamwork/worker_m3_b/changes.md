# Changes Record — Worker M3-B (Language Unification: Frontend UI & Web Templates)

## Overview
Worker M3-B executed the complete Language Unification (`arz` — authentic colloquial Egyptian Arabic) across all assigned web templates and Flutter mobile/desktop screens according to Milestone 3 requirements and Explorer 3 survey specifications.

---

## Modified Files and Detailed Changes

### 1. `app/templates/chat_ui.html`
- **Page Title & Brand Header**:
  - Unified title to `نيبولا — محادثة الذكاء الاصطناعي المركزي (Egyptian Arabic)`.
  - Header brand: `نيبولا — الواجهة المركزية | التوأم الرقمي والروبوت الذكي`.
- **Quick Action Prompts**:
  - `إزيك يا نيبولا! عرفني بنفسك وباللي تقدر تعمله`
  - `إيه وضع المواتير والسيرفوهات وشريحة ESP32 دلوقتي؟`
  - `احكيلي حكاية قصيرة بالمصري عن الروبوتات والذكاء الاصطناعي`
- **Streaming Controls & Options**:
  - Toggles: `بث الرد كلمة بكلمة (Streaming)`, `نطق الرد صوتياً (TTS)`, `تتبع المشاعر والإيماءات (Signals)`.
- **Side Panel 1: Vision (الكاميرا والملامح)**:
  - Header: `الكاميرا وتحليل الرؤية (Vision ID)`.
  - Buttons: `افتح الكاميرا`, `لقطة سريعة`, `ارفع صورة وش`.
  - Verification badge: `تم مطابقة الملامح بنجاح!`.
- **Side Panel 2: Personality & Identity**:
  - Header: `الشخصية والتوأم الرقمي`.
  - Status: `الشخصية الشغالة: نيبولا المصري (اللهجة القاهرية arz)`.
- **Side Panel 3: Voice Clone Studio**:
  - Header: `استوديو استنساخ وبصمة الصوت`.
  - Controls: `سجل صوتك دلوقتي (10 ثواني)`, `ارفع ملف صوتي`, `استنسخ الصوت فوراً`.
  - Status indicators: `بنحلل بصمة الصوت ونعمل التوأم الصوتي...`, `تم استنساخ الصوت بنجاح!`.
- **Side Panel 4: System Diagnostics**:
  - Header: `فحص السيستم والمحركات (ESP32)`.
  - Buttons & labels: `موتور السيرفو: شغال تمام`, `حساس المسافة: 42 سم`, `🚨 وقف كل حاجة فوراً (طوارئ)`.
- **Side Panel 5: Memory Bank (RAG)**:
  - Header: `بنك الذكريات والمعلومات (RAG)`.
  - Controls: `اكتب معلومة جديدة لنيبولا...`, `احفظ في الذاكرة`, `ذكريات مسجلة`.
- **JavaScript UI Strings & Notifications**:
  - Converted all toast alerts, confirmation dialogs, audio playback status, and error notifications into authentic Egyptian Arabic (`arz`).

---

### 2. `app/static/faces_studio.html`
- **Header & Navigation**:
  - Page title: `استوديو الوجوه وبصمة الصوت — نيبولا`.
  - Header: `استوديو الوجوه وبصمة الصوت والتعرف البيومتري`.
  - Navigation tabs: `الكاميرا المباشرة`, `التعرف على الوجوه (1:N)`, `المقارنة والتطابق (1:1)`, `بروفايلات المسجلين`, `بصمة الصوت والمتحدثين`.
- **Tab 1: Live HUD Camera**:
  - Header: `متابعة الكاميرا الحية وتحليل الملامح`.
  - Controls: `شغّل الكاميرا`, `اقفل الكاميرا`, `اكتشاف فوري للوجوه`, `تتبع المشاعر`.
  - HUD overlay labels: `جاري فحص الملامح...`, `الوجه مطابق`, `شخص غير معروف`.
- **Tab 2: Recognition (1:N)**:
  - Header: `التعرف على صاحب الوجه من قاعدة البيانات`.
  - Description: `ارفع صورة أو التقط كادر عشان السيستم يبحث ويطلعلك صاحب الوجه ونسبة التطابق`.
  - Button: `ابحث عن صاحب الوجه`.
- **Tab 3: Verification (1:1)**:
  - Header: `مقارنة صورتين وتأكيد التطابق البيومتري`.
  - Inputs: `الصورة الأولى (المرجع)`, `الصورة الثانية (للفحص)`.
  - Button: `قارن الملامح دلوقتي`.
- **Tab 4: Profiles Management**:
  - Header: `إدارة بروفايلات الوجوه المسجلة`.
  - Controls: `تسجيل بروفايل جديد`, `اسم الشخص بالكامل`, `ارفع صور التدريب`, `حفظ البروفايل`.
- **Tab 5: Voiceprint & Diarization**:
  - Header: `التعرف على المتحدثين وبصمة الصوت`.
  - Controls: `تحليل ملف صوتي`, `فصل أصوات المتحدثين (Diarization)`, `مطابقة بصمة الصوت`.
- **JavaScript Dialogs & Feedback**:
  - Unified all alert prompts, error banners, and success toasts to authentic Cairo Egyptian Arabic.

---

### 3. `nebula-frontend-main/nebulla/lib/screens/login_screen.dart`
- **Feedback & Snackbars**:
  - Success: `نورت يا ${user.fullName}! دخلت على حسابك تمام.`
  - Error: `مش عارفين ندخلك: $e`
  - Biometric validation: `اكتب إيميلك الأول عشان نقدر نطابق بصمة وشك.`
  - Biometric success: `اتأكدنا من بصمة وشك بنجاح! منور يا ${user.fullName}.`
  - Biometric error: `معرفناش نطابق بصمة الوش: $e`
- **Biometric Scanning Dialog**:
  - `بنفحص بصمة وشك دلوقتي...`
  - `بنطابق ملامح الوش عبر شبكة Neural Face ID...`
- **Header & Form**:
  - Title: `ادخل على حسابك` (was `تسجيل الدخول`).
  - Subtitle: `أهلاً بيك تاني! سجّل دخولك عشان تكمل شغلك على السيستم.`
  - Email label: `الإيميل أو كود التعريف بتاعك`.
  - Email validator: `لازم تكتب الإيميل أو كود التعريف بتاعك`.
  - Password label: `كلمة السر (الباسورد)`.
  - Password validator: `من فضلك اكتب الباسورد بتاعك`.
  - Remember me: `افتكرني على الجهاز ده ومتخرجنيش`.
  - Forgot password: `نسيت الباسورد؟`.
  - Submit button: `ادخل على حسابك`.
  - Biometric button: `ادخل ببصمة الوش (Neural Face ID)`.
  - Footer link: `معندكش حساب؟ ` / `اعمل حساب جديد من هنا`.
- **Forgot Password Modal Sheet**:
  - Step 1 title: `استرجاع الباسورد`.
  - Step 2 title: `اكتب الباسورد الجديد`.
  - Step 1 subtitle: `اكتب إيميلك المسجل عشان نبعتلك كود الاسترجاع حالاً.`.
  - Step 2 subtitle: `اكتب كود الاسترجاع والباسورد الجديد عشان نكمل.`.
  - Input hints: `الإيميل بتاعك`, `كود الاسترجاع اللي وصلك`, `الباسورد الجديد`, `أكّد الباسورد الجديد تاني`.
  - Buttons: `ابعت كود الاسترجاع`, `تأكيد الباسورد الجديد`.
  - Error messages: `اكتب إيميل مظبوط عشان نقدر نبعتلك.`, `معرفناش نطلب كود الاسترجاع: $e`, `اكتب كود الاسترجاع اللي وصلك.`, `الباسورد مينفعش يقل عن 8 خانات.`, `الباسورد وتأكيده مش متطابقين خالص.`, `معرفناش نغير الباسورد: $e`.

---

### 4. `nebula-frontend-main/nebulla/lib/screens/register_screen.dart`
- **Feedback & Snackbars**:
  - Password mismatch: `الباسورد وتأكيده مش متطابقين خالص.`
  - Registration success: `نورت نيبولا يا ${user.fullName}! حسابك اتعمل بنجاح.`
  - Error: `معرفناش نعمل الحساب: $e`
- **Header**:
  - Title: `اعمل حساب جديد` (was `إنشاء حساب جديد`).
  - Subtitle: `انضم دلوقتي لشبكة نيبولا والذكاء الاصطناعي المركزي`.
- **Form Fields & Validation**:
  - Full name label: `اسمك بالكامل`, validator: `اكتب اسمك بالكامل (حرفين على الأقل)`.
  - Email label: `الإيميل بتاعك`, empty validator: `من فضلك اكتب إيميلك`, format validator: `الإيميل ده مش مظبوط`.
  - Password label: `كلمة السر (الباسورد)`, validator: `الباسورد مينفعش يقل عن 8 خانات`.
  - Confirm password label: `أكّد كلمة السر تاني`, empty validator: `من فضلك أكّد الباسورد`, mismatch validator: `الباسورد وتأكيده مش متطابقين خالص`.
- **Action Buttons & Footer**:
  - Submit button: `سجّل حسابي دلوقتي`.
  - Footer link: `عندك حساب شغال بالفعل؟ ` / `ادخل من هنا ›`.

---

### 5. `nebula-frontend-main/nebulla/lib/screens/main_shell.dart`
- **Bottom Navigation Items**:
  - `الرئيسية` (Home)
  - `الدردشة` (Chat, was `المحادثة`)
  - `الشخصيات` (Personalities)
  - `فحص السيستم` (Diagnostics, was `التشخيص`)
  - `الظبط` (Settings, was `الإعدادات`)

---

### 6. `nebula-frontend-main/nebulla/lib/screens/dashboard_screen.dart`
- **Feedback & Emergency Stop**:
  - Load error: `معرفناش نجيب البيانات: $e`.
  - Emergency stop success: `🚨 وقفنا كل حاجة فوراً (طوارئ)`.
  - Emergency stop error: `معرفناش نوقف السيستم: $e`.
  - Emergency button label: `🚨 وقف كل حاجة فوراً (طوارئ)`.
- **AppBar & Card Headers**:
  - Title: `شاشة التحكم (الداشبورد)`.
  - Connection card title: `حالة الاتصال بالأجهزة`.
  - Channels: `الموبايل (الشاشة)`, `الكمبيوتر (أوضة التحكم)`, `شريحة الروبوت (ESP32)`.
  - Connection status: `متصل وشغال` / `مش متصل`.
- **Active Personality Card**:
  - Header: `الشخصية اللي شغالة دلوقتي`.
  - Empty personality: `مفيش شخصية شغالة دلوقتي`.
  - Badge: `شغالة` / `واقفة`.
- **System Overview**:
  - Header: `نظرة سريعة على السيستم`.
  - Stat items: `كل الشخصيات`, `اللي شغالين`.

---

### 7. `nebula-frontend-main/nebulla/lib/screens/chat_screen.dart`
- **Header & Controls**:
  - Title: `شات نيبولا`.
  - Subtitle: `شغال بالذكاء الاصطناعي والتوأم الرقمي`.
  - New chat tooltip: `افتح شات جديد`.
- **Empty State**:
  - Heading: `ابدأ دردشتك دلوقتي مع نيبولا`.
  - Subtitle: `اكتب اللي نفسك فيه تحت ونيبولا هيرد عليك`.
- **Input & Feedback**:
  - Send error: `حصلت مشكلة في الإرسال: $e`.
  - Input field placeholder: `اكتب اللي في بالك هنا...`.

---

### 8. `nebula-frontend-main/nebulla/lib/screens/diagnostics_screen.dart`
- **Header & Tabs**:
  - Title: `فحص وتحكم السيستم`.
  - Tooltips: `سجّل بصمة وش جديدة`, `إشارات وحركات الروبوت`.
  - Tab 1: `مواتير السيرفو`.
  - Tab 2: `المواتير و الليدات`.
  - Tab 3: `معايرة الزوايا`.
- **Servo Tab**:
  - Section header: `تجربة مواتير السيرفو`.
  - Servo ID label: `رقم السيرفو: $_servoId`.
  - Angle label: `الزاوية: ${_angle.toStringAsFixed(0)} درجة`.
  - Speed label: `السرعة: $_speedMs مللي ثانية`.
  - Action buttons: `جرّب الحركة`, `وضع السكون (الهوم)`.
  - Feedback snackbars: `حركنا السيرفو تمام`, `رجعنا كل السيرفوهات لوضع السكون`, `حصلت مشكلة: $e`.
  - Ultrasonic sensor card: `حساس المسافة بالألتراسونيك (HC-SR04)`, empty text: `دوس هنا عشان تقيس المسافة`, button: `قيس دلوقتي`.
- **Motor & LED Tab**:
  - Motors header: `تجربة مواتير الحركة`.
  - Labels: `الموتور الشمال: $_left`, `الموتور اليمين: $_right`, `المدة: $_durationMs مللي ثانية`.
  - Button: `دور المواتير`.
  - Feedback: `شغّلنا المواتير بنجاح`.
  - LED header: `ظبط إضاءة ونبض الليدات (LED)`.
  - Button: `شغّل الإضاءة دي`.
  - Feedback: `ظبطنا إضاءة الليدات تمام`.
  - Emergency stop: `🚨 وقف كل حركة فوراً`, feedback: `🚨 وقفنا كل المواتير والسيستم فوراً`.
- **Calibration Tab**:
  - Error: `معرفناش نجيب بيانات المعايرة: $e`.
  - Reset feedback: `رجعنا كل السيرفوهات لوضع السكون`.
  - Dialog title: `سيرفو رقم #${entry.servoId}`.
  - Form labels: `اسم السيرفو (مثلاً: الرقبة، العين)`, `أقل زاوية: ...`, `أعلى زاوية: ...`, `زاوية السكون (الهوم): ...`.
  - Dialog buttons: `إلغاء`, `احفظ التعديلات`.
  - Success feedback: `حفظنا المعايرة تمام`.
  - Empty state: `مفيش أي بيانات معايرة متسجلة`.
  - Reset all button: `رجّع كل السيرفوهات لوضع السكون`.

---

### 9. `nebula-frontend-main/nebulla/lib/screens/face_registration_screen.dart`
- **Header & Info Card**:
  - Title: `تسجيل بصمة الوش`.
  - Explanation: `هنسجل بصمة الوش في قاعدة بيانات UniFace عشان الروبوت يتعرف عليه بالكاميرا أول ما يشوفه.`.
- **Image Picker & Form**:
  - Pick placeholder: `دوس هنا عشان تختار أو تصور صورة`.
  - Hint: `JPG / PNG · ملامح الوش لازم تكون واضحة ومباشرة للكاميرا`.
  - Change photo button: `غيّر الصورة`.
  - Name label: `اسم صاحب البصمة بالكامل`.
  - Submit button: `سجّل بصمة الوش دلوقتي`.
- **Pick Options Sheet**:
  - Camera: `افتح الكاميرا وصوّر`.
  - Gallery: `اختار صورة من المعرض`.
- **Feedback Snackbars**:
  - Validation error: `من فضلك اكتب الاسم واختار صورة واضحة للوش`.
  - Success: `سجلنا بصمة الوش بنجاح تمام`.
  - Error: `معرفناش نسجل الوش: $e`.

---

### 10. `nebula-frontend-main/nebulla/lib/screens/memories_screen.dart`
- **Header & Search**:
  - Title: `ذكريات ومعلومات الروبوت (RAG)`.
  - Search placeholder: `دور في ذكريات ومعلومات الروبوت...`.
- **Add Memory Dialog**:
  - Title: `ضيف معلومة أو ذكرى جديدة`.
  - Content placeholder: `اكتب المعلومة اللي عايز نيبولا يفتكرها هنا...`.
  - Importance slider: `درجة الأهمية:`.
  - Buttons: `إلغاء`, `احفظ المعلومة`.
  - Success feedback: `ضيفنا الذكرى دي بنجاح`.
  - Error feedback: `معرفناش نحفظ الذكرى: $e`.
- **List & Items**:
  - Empty state: `مفيش أي ذكريات متسجلة للشخصية دي لسه`.
  - Importance badge: `أهمية: ${memory.importance} / 10`.
  - Delete feedback: `مسحنا الذاكرة دي خلاص`, error: `معرفناش نمسح الذاكرة: $e`.

---

### 11. `nebula-frontend-main/nebulla/lib/screens/personalities_screen.dart`
- **Header & Empty State**:
  - Title: `شخصيات وبروفايلات نيبولا`.
  - Add button: `ضيف شخصية`.
  - Empty state text: `مفيش أي شخصيات متسجلة لسه`.
  - Empty state button: `اعمل أول شخصية دلوقتي`.
- **Card Actions & Badges**:
  - Active badge: `شغالة دلوقتي`.
  - Voice tag: `بصمة صوت مسجلة`.
  - Buttons: `شغّلها دلوقتي`, `عدّل`, `الذكريات`, `امسح`, `بصمة صوت`.
  - Delete dialog: `مسح الشخصية`, `متأكد إنك عايز تمسح شخصية "${p.name}"؟`, `امسح`.
  - Feedback: `شغّلنا شخصية ${p.name} دلوقتي`, `مسحنا الشخصية خلاص`, `رفعنا عينة الصوت بنجاح`.
- **Personality Form Screen**:
  - Title: `عمل شخصية جديدة` / `تعديل بيانات الشخصية`.
  - Field labels: `اسم الشخصية (مثلاً: نيبولا المصري)`, `نبذة عن الشخصية ودورها (اختياري)`, `تعليمات وطريقة تفكير الشخصية (System Prompt)`, `اللهجة وطريقة الكلام`, `خلطة اللغات (عربي / إنجليزي)`.
  - Validation: `لازم تكتب اسم للشخصية`.
  - Save button: `احفظ بيانات الشخصية`.
  - Feedback: `حفظنا الشخصية تمام`, `معرفناش نحفظ الشخصية: $e`.

---

### 12. `nebula-frontend-main/nebulla/lib/screens/settings_screen.dart`
- **Header & Connections**:
  - Title: `الظبط وإعدادات السيستم`.
  - Server card: `الاتصال بالسيرفر المركزي`, `عنوان ورابط السيرفر (Base URL)`.
- **AI Providers Card**:
  - Header: `محركات ومزودي الذكاء الاصطناعي`.
  - Dropdown labels: `التعرف على الصوت (STT)`, `توليد ونطق الصوت (TTS)`, `محرك ونموذج الذكاء (LLM)`.
  - Model field: `اسم موديل الذكاء (LLM Model)`.
  - Ollama/LLM URL field: `رابط خادم Ollama أو الـ API`.
- **Version & Logout**:
  - Version card: `روبوت نيبولا الذكي`, `السيرفر الحالي: ${_store.getBaseUrl()}`.
  - Save button: `احفظ الإعدادات دي`.
  - Logout button: `اخرج من الحساب`.
  - Feedback: `حفظنا الإعدادات تمام`, `معرفناش نحفظ الإعدادات: $e`.

---

### 13. `nebula-frontend-main/nebulla/lib/screens/signals_screen.dart`
- **Header & Empty State**:
  - Title: `حركات وإيماءات الروبوت (Signals)`.
  - Add button: `حركة جديدة`.
  - Empty state text: `مفيش أي إشارات أو حركات متسجلة لسه`.
- **Create Signal Dialog**:
  - Title: `إضافة حركة أو إيماءة جديدة`.
  - Field labels: `اسم الحركة (مثلاً: التحية، الضحك)`, `شرح الحركة ودورها (اختياري)`, `العاطفة المرتبطة بالحركة (اختياري)`, `أوامر زوايا المفاصل (كود JSON)`.
  - Dialog button: `سجّل الحركة`.
  - Feedback: `عملنا الحركة الجديدة تمام`.
- **Card Actions & Feedback**:
  - Fire feedback: `⚡ نفذنا حركة ${s.name} على الروبوت`.
  - Delete dialog: `مسح الحركة`, `متأكد إنك عايز تمسح حركة "${s.name}"؟`, `امسح`.
  - Delete feedback: `مسحنا الحركة خلاص`, `معرفناش نمسحها: $e`.

---

### 14. `nebula-frontend-main/nebulla/lib/widgets/common_widgets.dart`
- **Inspection & Validation**:
  - Inspected for hardcoded MSA text. Confirmed all reusable widgets (`NebulaCard`, `NebulaPrimaryButton`, `NebulaDangerButton`, `StatusDot`, `SectionHeader`, `LoadingOverlay`, `showSuccessSnackbar`, `showErrorSnackbar`) receive their string inputs dynamically from the screens, which have all been unified into authentic Egyptian Arabic (`arz`).
