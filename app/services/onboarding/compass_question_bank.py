"""
Nebula Compass (بوصلة نيبولا) Question Bank.
Contains 50 intelligent, indirect profiling questions designed to deduce user traits,
work style, habits, preferences, and mindset, generating long-term RAG memories.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

STANDARD_OPTIONS = [
    "نعم",
    "في الغالب نعم",
    "لا أعلم / محايد",
    "في الغالب لا",
    "لا",
]


class CompassQuestion(BaseModel):
    id: str = Field(..., description="Unique question identifier")
    index: int = Field(..., description="Order index 1 to 50")
    dimension: str = Field(..., description="Dimension category (work_tech, routine, social, preferences, mindset)")
    text: str = Field(..., description="Indirect conversational question text in Arabic")
    subtitle: Optional[str] = Field(None, description="Helpful contextual hint")
    is_core: bool = Field(False, description="True for the 15 rapid-start core questions")
    options: List[str] = Field(default_factory=lambda: list(STANDARD_OPTIONS))
    # Fact templates mapped to affirmative ("نعم" / "في الغالب نعم") and negative ("لا" / "في الغالب لا")
    affirmative_fact: str = Field(..., description="Fact recorded when answered affirmatively")
    negative_fact: Optional[str] = Field(None, description="Optional fact recorded when answered negatively")


QUESTION_BANK: List[CompassQuestion] = [
    # ── البعد 1: نمط العمل والاهتمامات التقنية والمهنية (Work & Tech Style) ────────
    CompassQuestion(
        id="q1_software_builder",
        index=1,
        dimension="work_tech",
        text="هل تقضي معظم وقتك في بناء وتفكيك الأشياء المعقدة أو البرمجيات خلف الشاشات؟",
        subtitle="يساعدنا على فهم مجالك اليومي وطبيعة شغفك التقني",
        is_core=True,
        affirmative_fact="المستخدم يعمل في مجال البرمجيات والتطوير التقني ويقضي وقتاً طويلاً أمام الشاشات.",
        negative_fact="طبيعة عمل المستخدم ليست برمجية مكتبية وقد يفضل العمل الميداني أو الإداري.",
    ),
    CompassQuestion(
        id="q2_puzzle_solver",
        index=2,
        dimension="work_tech",
        text="هل تشعر بالإثارة والنشاط عندما يُطلب منك حل مشكلة تقنية أو لغز معقد؟",
        subtitle="يكشف مدى استمتاعك بالتحديات التحليلية",
        is_core=False,
        affirmative_fact="المستخدم يحب التحديات الفكرية وتحليل المشاكل التقنية المعقدة.",
        negative_fact="المستخدم يفضل الحلول المباشرة والواضحة ويتجنب التعقيدات غير الضرورية.",
    ),
    CompassQuestion(
        id="q3_data_driven",
        index=3,
        dimension="work_tech",
        text="هل تفضل أن تكون مهامك محددة بالأرقام والنتائج المنطقية بدلاً من التوجيهات العامة؟",
        subtitle="لتخصيص أسلوب المساعد في عرض الإحصائيات والمعلومات",
        is_core=True,
        affirmative_fact="المستخدم يفضل التعامل بالأرقام والبيانات الدقيقة والنتائج القابلة للقياس.",
        negative_fact="المستخدم يفضل النظرة الشاملة والمفاهيم العامة على التفاصيل الرقمية الجافة.",
    ),
    CompassQuestion(
        id="q4_ai_enthusiast",
        index=4,
        dimension="work_tech",
        text="هل تتابع أحدث أخبار الذكاء الاصطناعي والتكنولوجيا بشغف واهتمام شبه يومي؟",
        subtitle="يحدد مدى عمق المصطلحات التقنية في المحادثات",
        is_core=True,
        affirmative_fact="المستخدم شغوف ومتابع لأحدث تطورات الذكاء الاصطناعي والتقنيات الناشئة.",
        negative_fact=None,
    ),
    CompassQuestion(
        id="q5_automation_lover",
        index=5,
        dimension="work_tech",
        text="هل تفضل أتمتة المهام الروتينية باستخدام الأدوات الرقمية بدلاً من تكرارها يدوياً؟",
        subtitle="يساعد المساعد في اقتراح حلول ذكية لتسهيل مهامك",
        is_core=False,
        affirmative_fact="المستخدم يميل لأتمتة أعماله ويفضل استخدام السكربتات والأدوات الذكية لتوفير الوقت.",
        negative_fact=None,
    ),
    CompassQuestion(
        id="q6_deep_work",
        index=6,
        dimension="work_tech",
        text="هل تجد متعتك في العمل الفردي المتواصل لساعات طويلة في تركيز عميق دون مقاطعة؟",
        subtitle="يساعد المساعد على احترام أوقات تركيزك العالي",
        is_core=False,
        affirmative_fact="المستخدم يفضل جلسات العمل الفردية العميقة المتصلة دون مقاطعة.",
        negative_fact="المستخدم يفضل العمل التفاعلي وجلسات العصف الذهني المشتركة مع الآخرين.",
    ),
    CompassQuestion(
        id="q7_hardware_curiosity",
        index=7,
        dimension="work_tech",
        text="هل تهتم بفهم كيف تعمل الأجهزة والدوائر والأنظمة من الداخل قبل أن تستخدمها؟",
        subtitle="يحدد اهتمامك بالعتاد والإلكترونيات",
        is_core=False,
        affirmative_fact="المستخدم مهتم بهندسة العتاد ومعرفة الكيفية الفيزيائية لعمل الأنظمة الذكية.",
        negative_fact=None,
    ),
    CompassQuestion(
        id="q8_doc_reader",
        index=8,
        dimension="work_tech",
        text="هل تفضل الرجوع للتوثيق الفني والمصادر الرسمية (Documentation) لحل المشاكل؟",
        subtitle="يعكس أسلوبك في البحث والتعلم الفني",
        is_core=False,
        affirmative_fact="المستخدم باحث دقيق يعتمد على التوثيق الفني والمراجع الأصلية الموثوقة.",
        negative_fact=None,
    ),
    CompassQuestion(
        id="q9_side_projects",
        index=9,
        dimension="work_tech",
        text="هل تشارك في مشاريع برمجية أو ريادية طموحة تتطلب وقتاً إضافياً خارج ساعات العمل؟",
        subtitle="لمعرفة مدى انشغالك بمشاريع تخرج أو شركات ناشئة",
        is_core=False,
        affirmative_fact="المستخدم يمتلك مشاريع تقنية وريادية طموحة يعمل عليها بشغف.",
        negative_fact=None,
    ),
    CompassQuestion(
        id="q10_keyboard_shortcuts",
        index=10,
        dimension="work_tech",
        text="هل تعتمد بشكل أساسي على اختصارات الكيبورد والأوامر السريعة في إنجاز أعمالك؟",
        subtitle="مؤشر على السرعة والاحترافية الرقمية",
        is_core=False,
        affirmative_fact="المستخدم خبير بالأدوات الرقمية ويفضل الاختصارات والسرعة في التنفيذ.",
        negative_fact=None,
    ),

    # ── البعد 2: الروتين اليومي وإيقاع الحياة والنوم (Daily Routine & Chronotype) ───
    CompassQuestion(
        id="q11_night_owl",
        index=11,
        dimension="routine",
        text="هل تشعر بذروة طاقتك وتركيزك الذهني بعد منتصف الليل والهدوء التام؟",
        subtitle="لتنسيق نبرة وتوقيت تنبيهات الروبوت",
        is_core=True,
        affirmative_fact="المستخدم كائن ليلي (Night Owl) وتبلغ ذروة إنتاجيته وإبداعه بعد منتصف الليل.",
        negative_fact="المستخدم صباحي النشاط ويفضل إنجاز مهامه الرئيسية في ساعات النهار الأولى.",
    ),
    CompassQuestion(
        id="q12_coffee_lover",
        index=12,
        dimension="routine",
        text="هل فنجان القهوة هو الطقس الأساسي الذي لا يبدأ يومك الفعلي بدونه؟",
        subtitle="لتخصيص التحيات الصباحية ومزاح المساعد",
        is_core=True,
        affirmative_fact="المستخدم يحب القهوة وتعتبر مشروبه الأساسي لبدء يومه بنشاط.",
        negative_fact="المستخدم لا يعتمد على القهوة ويفضل مشروبات أخرى مثل الشاي أو المشروبات الطبيعية.",
    ),
    CompassQuestion(
        id="q13_strict_schedule",
        index=13,
        dimension="routine",
        text="هل تلتزم بجدول يومي صارم ومواعيد استيقاظ ثابتة حتى في عطلة نهاية الأسبوع؟",
        subtitle="يحدد مدى انضباطك أو مرونتك الزمنية",
        is_core=False,
        affirmative_fact="المستخدم منضبط جداً ويلتزم بجدول زمني ومواعيد استيقاظ دقيقة.",
        negative_fact="المستخدم يتمتع بمرونة عالية في مواعيده وروتينه اليومي حسب متطلبات عمله.",
    ),
    CompassQuestion(
        id="q14_fast_meals",
        index=14,
        dimension="routine",
        text="هل تفضل تناول وجبات خفيفة وسريعة أثناء العمل بدلاً من التوقف لتناول وجبات مطولة؟",
        subtitle="يعكس أسلوبك في إدارة وقت الاستراحة",
        is_core=False,
        affirmative_fact="المستخدم يفضل الوجبات الخفيفة والعملية أثناء ساعات العمل والتركيز.",
        negative_fact="المستخدم يفضل أخذ استراحة كاملة وتناول وجبات طعام مريحة ومتأنية.",
    ),
    CompassQuestion(
        id="q15_hyperfocus",
        index=15,
        dimension="routine",
        text="هل تنسى الوقت والوسط المحيط بك تماماً عندما تنغمس في فكرة أو مشروع شيق؟",
        subtitle="حالة التركيز الفائق (Flow State)",
        is_core=True,
        affirmative_fact="المستخدم يدخل في حالة تركيز فائق ويفقد الإحساس بالوقت عند العمل على مشاريع ممتعة.",
        negative_fact=None,
    ),
    CompassQuestion(
        id="q16_dim_lights",
        index=16,
        dimension="routine",
        text="هل تفضل العمل من مساحة هادئة ذات إضاءة خافتة أو غير مباشرة؟",
        subtitle="يساعد في ضبط إضاءة كشاف الروبوت والمؤشرات البصرية",
        is_core=False,
        affirmative_fact="المستخدم يفضل بيئات العمل الهادئة ذات الإضاءة الدافئة أو الخافتة والوضع المظلم.",
        negative_fact="المستخدم يفضل المساحات المضيئة والغنية بضوء النهار الطبيعي.",
    ),
    CompassQuestion(
        id="q17_music_concentration",
        index=17,
        dimension="routine",
        text="هل تميل للاستماع للموسيقى الهادئة أو أصوات الطبيعة و الـ Lo-Fi أثناء التركيز والعمل؟",
        subtitle="لتخصيص اقتراحات الأجواء الصوتية",
        is_core=False,
        affirmative_fact="المستخدم يحب الاستماع للموسيقى الهادئة أو نغمات التركيز أثناء العمل والبرمجة.",
        negative_fact="المستخدم يفضل العمل في صمت تام دون أي مؤثرات صوتية.",
    ),
    CompassQuestion(
        id="q18_todo_planner",
        index=18,
        dimension="routine",
        text="هل تقوم بتدوين مهام يومك في قائمة مهام (To-Do List) أو تطبيق مخصص قبل بدء العمل؟",
        subtitle="يساعد في تكامل مهام التذكير والمتابعة",
        is_core=False,
        affirmative_fact="المستخدم يخطط ليومه عبر قوائم المهام ويقدر متابعة التذكيرات والمواعيد.",
        negative_fact=None,
    ),
    CompassQuestion(
        id="q19_work_afterglow",
        index=19,
        dimension="routine",
        text="هل تجد صعوبة في فصل تفكيرك عن مشاريعك وأفكارك حتى بعد انتهاء وقت العمل؟",
        subtitle="شغف مستمر بالتطوير والابتكار",
        is_core=False,
        affirmative_fact="المستخدم يفكر بمشاريعه وأفكاره باستمرار حتى في أوقات فراغه.",
        negative_fact=None,
    ),
    CompassQuestion(
        id="q20_fitness_habit",
        index=20,
        dimension="routine",
        text="هل تمارس تمارين رياضية منتظمة أو تفضل المشي لتصفية ذهنك وتجديد نشاطك؟",
        subtitle="لتشجيعك ومتابعة نشاطك البدني",
        is_core=False,
        affirmative_fact="المستخدم يهتم بالحركة والنشاط البدني أو المشي لتصفية ذهنه.",
        negative_fact=None,
    ),

    # ── البعد 3: أسلوب التواصل والتفاعل البشري (Social & Interaction Tone) ─────────
    CompassQuestion(
        id="q21_concise_replies",
        index=21,
        dimension="social",
        text="هل تفضل أن تكون إجابات مساعدك الذكي سريعة وخاطفة ومباشرة دون مقدمات مطولة؟",
        subtitle="يحدد طول الردود وسرعة التفاعل",
        is_core=True,
        affirmative_fact="المستخدم يفضل الإجابات الصوتية السريعة والمباشرة والموجزة بدون مقدمات طويلة.",
        negative_fact="المستخدم يفضل الإجابات المفصلة والشاملة التي تشرح كافة الأبعاد.",
    ),
    CompassQuestion(
        id="q22_humorous_tone",
        index=22,
        dimension="social",
        text="هل تحب أسلوب الحوار الودود والمرح المصحوب بالفكاهة المصرية العفوية؟",
        subtitle="لضبط نبرة الصوت والمزاح المصري الأصيل",
        is_core=True,
        affirmative_fact="المستخدم يفضل النبرة المصرية العفوية الودودة والمرحة مع قليل من المزاح الذكي.",
        negative_fact="المستخدم يفضل أسلوب حوار رصين وهادئ ورسمي نوعاً ما.",
    ),
    CompassQuestion(
        id="q23_english_mixing",
        index=23,
        dimension="social",
        text="هل تفضل استخدام المصطلحات والمفاهيم الإنجليزية التقنية مدمجة في السياق العربي؟",
        subtitle="مثل: commit, push, backend, deploy",
        is_core=False,
        affirmative_fact="المستخدم يفضل خلط المصطلحات التقنية الإنجليزية بشكل طبيعي في السياق العربي.",
        negative_fact="المستخدم يفضل التعبير بالكلمات والمصطلحات العربية قدر الإمكان.",
    ),
    CompassQuestion(
        id="q24_no_redundancy",
        index=24,
        dimension="social",
        text="هل يضايقك عندما يكرر الآخرون التوضيحات البديهية التي تعرفها وتفهمها بالفعل؟",
        subtitle="يمنع المساعد من إعطاء شروحات زائدة",
        is_core=False,
        affirmative_fact="المستخدم ذكي وسريع البديهة وينزعج من تكرار البديهيات والتوضيحات الزائدة.",
        negative_fact=None,
    ),
    CompassQuestion(
        id="q25_chat_over_call",
        index=25,
        dimension="social",
        text="هل تميل للتواصل عبر الرسائل النصية والدردشة أكثر من المكالمات الصوتية الطويلة؟",
        subtitle="يعكس أسلوب التواصل المفضل",
        is_core=False,
        affirmative_fact="المستخدم يفضل التواصل الكتابي السريع على المكالمات الصوتية المطولة.",
        negative_fact="المستخدم يقدر التواصل الصوتي المباشر والحديث التفاعلي.",
    ),
    CompassQuestion(
        id="q26_proactive_checkin",
        index=26,
        dimension="social",
        text="هل تحب أن يسألك رفيقك الذكي عن خططك وتفاصيل يومك ويطمئن عليك دورياً؟",
        subtitle="تفعيل التفاعل التلقائي من الروبوت",
        is_core=False,
        affirmative_fact="المستخدم يرحب بالمبادرة والتفاعل الاستباقي وسؤال المساعد عنه دورياً.",
        negative_fact="المستخدم يفضل أن يتحدث المساعد فقط عندما يُطلب منه ذلك دون مقاطعة استباقية.",
    ),
    CompassQuestion(
        id="q27_candid_sharing",
        index=27,
        dimension="social",
        text="هل تفضل مشاركة أفكارك وتحدياتك بصراحة عندما تواجهك عقبات في مشروعك؟",
        subtitle="لبناء علاقة توأم رقمي موثوق",
        is_core=False,
        affirmative_fact="المستخدم صريح ومنفتح في مناقشة أفكاره والتحديات التي يواجهها.",
        negative_fact=None,
    ),
    CompassQuestion(
        id="q28_honest_feedback",
        index=28,
        dimension="social",
        text="هل تقدّر الرأي الصادق والمباشر حتى وإن كان ينبهك لخطأ في تقديرك أو كودك؟",
        subtitle="يحدد أسلوب النقد البناء وتصحيح الأخطاء",
        is_core=False,
        affirmative_fact="المستخدم يقدر الصدق والملاحظات التقنية البناءة والمباشرة.",
        negative_fact=None,
    ),
    CompassQuestion(
        id="q29_storytelling",
        index=29,
        dimension="social",
        text="هل تحب أسلوب الشرح المدعوم بالأمثلة العملية والقصص التوضيحية الحقيقية؟",
        subtitle="يعزز أسلوب إيصال المفاهيم",
        is_core=False,
        affirmative_fact="المستخدم يستوعب ويفضل الشرح بالأمثلة الحية والنماذج الواقعية.",
        negative_fact=None,
    ),
    CompassQuestion(
        id="q30_friendly_honorifics",
        index=30,
        dimension="social",
        text="هل تشعر بالارتياح عندما يخاطبك المساعد بكنية ودية ومحترمة مثل 'يا باشمهندس' أو 'يا صديقي'؟",
        subtitle="لاختيار اللقب المفضل في التخاطب",
        is_core=True,
        affirmative_fact="المستخدم يفضل مخاطبته بلقب تقديري ودي مثل 'يا باشمهندس' مع مراعاة الاحترام.",
        negative_fact="المستخدم يفضل مناداته باسمه الأول مباشرة دون ألقاب رسمية.",
    ),

    # ── البعد 4: التفضيلات الشخصية والبيئة المحيطة (Preferences & Environment) ─────
    CompassQuestion(
        id="q31_organized_desk",
        index=31,
        dimension="preferences",
        text="هل تفضل أن يكون مكتبك ومساحة عملك مرتبة ومنظمة بدقة قبل بدء الإنتاج؟",
        subtitle="مؤشر على تنظيم البيئة المحيطة",
        is_core=False,
        affirmative_fact="المستخدم يقدر الترتيب والتنظيم في مساحة عمله ومحيطه المادي.",
        negative_fact="المستخدم يفضل الفوضى الخلاقة ويجد أفكاره وسط أدواته المتناثرة.",
    ),
    CompassQuestion(
        id="q32_scifi_fan",
        index=32,
        dimension="preferences",
        text="هل تشعر بالحنين لأفلام الخيال العلمي وعوالم الروبوتات والذكاء الاصطناعي المستقبلي؟",
        subtitle="لتنسيق تعبيرات العيون والحركات الفيزيائية",
        is_core=True,
        affirmative_fact="المستخدم معجب بعوالم الخيال العلمي وثقافة الروبوتات والتقنيات المستقبلية.",
        negative_fact=None,
    ),
    CompassQuestion(
        id="q33_explorer_spirit",
        index=33,
        dimension="preferences",
        text="هل تفضل السفر واستكشاف أفكار وتجارب غير مألوفة على البقاء في بيئتك الروتينية؟",
        subtitle="يحدد حب التجربة والمغامرة الفكرية",
        is_core=False,
        affirmative_fact="المستخدم محب للاستكشاف وتجربة كل ما هو جديد وغير مألوف.",
        negative_fact="المستخدم يفضل الاستقرار والبيئات المألوفة والمريحة.",
    ),
    CompassQuestion(
        id="q34_automotive_interest",
        index=34,
        dimension="preferences",
        text="هل تستهويك السيارات والمركبات الذكية وتتابع أخبار المحركات وقيادة السيارات؟",
        subtitle="يربط ذكريات التنقل ومفاتيح السيارة",
        is_core=False,
        affirmative_fact="المستخدم مهتم بالسيارات والمركبات والقيادة والتنقل.",
        negative_fact=None,
    ),
    CompassQuestion(
        id="q35_articles_over_video",
        index=35,
        dimension="preferences",
        text="هل تفضل قراءة المقالات والملخصات المكتوبة المركزة على مشاهدة فيديوهات مطولة؟",
        subtitle="تحديد أفضل وسائط استهلاك المحتوى",
        is_core=False,
        affirmative_fact="المستخدم يفضل القراءة السريعة والمقالات المركزة على الفيديوهات الطويلة.",
        negative_fact="المستخدم يفضل الشروحات المرئية والفيديوهات التوضيحية.",
    ),
    CompassQuestion(
        id="q36_gear_enthusiast",
        index=36,
        dimension="preferences",
        text="هل تهتم بجودة عتادك التقني مثل سماعات الرأس، الشاشات، ولوحات المفاتيح الميكانيكية؟",
        subtitle="الاهتمام بأجهزة ومعدات المكتب",
        is_core=True,
        affirmative_fact="المستخدم يهتم بجودة عتاده المكتبي والشاشات والسماعات الاحترافية.",
        negative_fact=None,
    ),
    CompassQuestion(
        id="q37_physical_robot_companion",
        index=37,
        dimension="preferences",
        text="هل تستهويك فكرة امتلاك روبوت وتوأم رقمي فيزيائي يشاركك مكتبك ويتفاعل معك بصرياً وحركياً؟",
        subtitle="جوهر تجربة روبوت نيبولا",
        is_core=True,
        affirmative_fact="المستخدم متحمس لوجود روبوت نيبولا الفيزيائي كتوأم رقمي ورفيق مكتبي ذكي.",
        negative_fact=None,
    ),
    CompassQuestion(
        id="q38_healthy_food",
        index=38,
        dimension="preferences",
        text="هل تفضل الأطعمة الصحية والوجبات المنزلية أو الخضروات على الوجبات السريعة الجاهزة؟",
        subtitle="لتوثيق التفضيلات الغذائية في الذاكرة",
        is_core=False,
        affirmative_fact="المستخدم يفضل الوجبات الصحية والخضروات والأكل المتوازن.",
        negative_fact="المستخدم يميل للوجبات السريعة والأطعمة الجاهزة العملية.",
    ),
    CompassQuestion(
        id="q39_winter_lover",
        index=39,
        dimension="preferences",
        text="هل تفضل الأجواء الشتوية والباردة والهدوء على حرارة الصيف والشواطئ الصاخبة؟",
        subtitle="مؤشر على المزاج المناخي",
        is_core=False,
        affirmative_fact="المستخدم يفضل الأجواء الشتوية والطقس البارد والهدوء المنزلي.",
        negative_fact="المستخدم يحب أجواء الصيف والنشاط الخارجي والمناطق الحيوية.",
    ),
    CompassQuestion(
        id="q40_vintage_sentimental",
        index=40,
        dimension="preferences",
        text="هل تحتفظ بمقتنيات وأدوات تذكارية قديمة لها قيمة معنوية خاصة لديك؟",
        subtitle="التقدير العاطفي للأشياء",
        is_core=False,
        affirmative_fact="المستخدم يقدر الذكريات والمقتنيات التذكارية ذات القيمة المعنوية.",
        negative_fact=None,
    ),

    # ── البعد 5: طريقة اتخاذ القرارات وحل المشكلات (Mindset & Problem Solving) ──────
    CompassQuestion(
        id="q41_logic_first",
        index=41,
        dimension="mindset",
        text="عند اتخاذ قرار مصيري، هل تعتمد على التحليل المنطقي والبيانات أكثر من الحدس والعاطفة؟",
        subtitle="أسلوب التفكير واتخاذ القرارات",
        is_core=True,
        affirmative_fact="المستخدم يتبع نهجاً عقلانياً منطقياً ويعتمد على التحليل في اتخاذ قراراته.",
        negative_fact="المستخدم يثق في حدسه الداخلي ونظرته العاطفية في القرارات المصيرية.",
    ),
    CompassQuestion(
        id="q42_risk_taker",
        index=42,
        dimension="mindset",
        text="هل تتقبل المخاطرة وتجربة أمور غير مضمونة ومبتكرة إذا كانت العوائد المحتملة استثنائية؟",
        subtitle="مستوى تقبل المخاطر الابتكارية",
        is_core=False,
        affirmative_fact="المستخدم يمتلك شجاعة المخاطرة وتجربة الطرق المبتكرة غير المألوفة.",
        negative_fact="المستخدم حذر ويفضل المسارات المجربة والمضمونة لتقليل المخاطر.",
    ),
    CompassQuestion(
        id="q43_prototype_fast",
        index=43,
        dimension="mindset",
        text="هل تفضل البدء الفوري ببناء نموذج أولي (Prototype) سريع لاختباره، بدلاً من التخطيط النظري الطويل؟",
        subtitle="منهجية العمل الرشيقة (Agile Mindset)",
        is_core=True,
        affirmative_fact="المستخدم عملي وسريع التنفيذ ويفضل اختبار الأفكار عبر نماذج أولية عملية.",
        negative_fact="المستخدم يفضل التخطيط والتوثيق المسبق الدقيق قبل كتابة أي كود أو تنفيذ.",
    ),
    CompassQuestion(
        id="q44_security_mindset",
        index=44,
        dimension="mindset",
        text="هل تشعر بالفضول الشديد لمعرفة كيفية تأمين الأنظمة وكشف الثغرات وحماية البيانات؟",
        subtitle="الوعي بالأمن السيبراني",
        is_core=False,
        affirmative_fact="المستخدم يمتلك عقلية أمنية واعية ويهتم بالأمن السيبراني وحماية البيانات.",
        negative_fact=None,
    ),
    CompassQuestion(
        id="q45_root_cause_hunter",
        index=45,
        dimension="mindset",
        text="عند حدوث خطأ غير متوقع، هل تصر على تتبع وفهم السبب الجذري بنفسك قبل طلب المساعدة؟",
        subtitle="الاستقلالية في التنقيح (Debugging)",
        is_core=False,
        affirmative_fact="المستخدم مستقل وشديد الإصرار في تنقيح الأخطاء والوصول للسبب الجذري بنفسه.",
        negative_fact=None,
    ),
    CompassQuestion(
        id="q46_ai_optimist",
        index=46,
        dimension="mindset",
        text="هل تؤمن بأن الذكاء الاصطناعي التوليدي سيُحدث ثورة حتمية تغير شكل كل الوظائف والمجالات؟",
        subtitle="الرؤية المستقبلية للتكنولوجيا",
        is_core=False,
        affirmative_fact="المستخدم مؤمن بمستقبل الذكاء الاصطناعي وقدرته التحويلية على تطوير العالم.",
        negative_fact=None,
    ),
    CompassQuestion(
        id="q47_lifelong_learner",
        index=47,
        dimension="mindset",
        text="هل تسعى باستمرار للتعلم وتطوير مهارات جديدة خارج نطاق دراستك أو وظيفتك الحالية؟",
        subtitle="حب التعلم المستمر والشغف المعرفي",
        is_core=False,
        affirmative_fact="المستخدم دائم التعلم ويحرص على اكتساب معارف ومهارات جديدة باستمرار.",
        negative_fact=None,
    ),
    CompassQuestion(
        id="q48_leadership_drive",
        index=48,
        dimension="mindset",
        text="هل تفضل قيادة وتوجيه المبادرات والمشاريع على أن تكون مجرد منفذ للمهام المطلوبة؟",
        subtitle="الروح القيادية والمبادرة",
        is_core=False,
        affirmative_fact="المستخدم يمتلك روحاً قيادية ويفضل المبادرة وإدارة وتوجيه المشاريع.",
        negative_fact="المستخدم يفضل التركيز في الجانب التخصصي والتنفيذي براحة تامة.",
    ),
    CompassQuestion(
        id="q49_perfectionist",
        index=49,
        dimension="mindset",
        text="هل تجد نفسك مدققاً في التفاصيل الصغيرة لضمان خلو العمل والمنتج من أي خلل أو عيب؟",
        subtitle="السعي نحو الجودة والكمال",
        is_core=False,
        affirmative_fact="المستخدم حريص على الجودة العالية ويهتم بالتفاصيل الدقيقة لإتقان العمل.",
        negative_fact=None,
    ),
    CompassQuestion(
        id="q50_founder_ambition",
        index=50,
        dimension="mindset",
        text="هل ترى نفسك في المستقبل مؤسساً لمشروعك التكنولوجي أو شركتك الناشئة الخاصة؟",
        subtitle="الطموح الريادي المستقبلي",
        is_core=True,
        affirmative_fact="المستخدم يمتلك طموحاً ريادياً لبناء وتأسيس شركته أو مشروعه التكنولوجي المستقل.",
        negative_fact=None,
    ),
]


def get_all_questions() -> List[CompassQuestion]:
    """Return all 50 profiling questions."""
    return QUESTION_BANK


def get_core_questions() -> List[CompassQuestion]:
    """Return the 15 rapid-start core questions (3 per dimension)."""
    return [q for q in QUESTION_BANK if q.is_core]


def get_balanced_questions(per_dimension: int = 2) -> List[CompassQuestion]:
    """
    Return a balanced subset of questions across all 5 dimensions.
    Default: 2 to 3 questions per dimension (10 to 15 questions total).
    Prioritizes core questions within each dimension.
    """
    count = max(1, min(per_dimension, 10))
    balanced: List[CompassQuestion] = []
    dimensions = ["work_tech", "routine", "social", "preferences", "mindset"]
    for dim in dimensions:
        dim_qs = [q for q in QUESTION_BANK if q.dimension == dim]
        dim_qs.sort(key=lambda q: (not q.is_core, q.index))
        balanced.extend(dim_qs[:count])
    balanced.sort(key=lambda q: q.index)
    return balanced


def get_questions_by_dimension(dimension: str) -> List[CompassQuestion]:
    """Return questions for a specific dimension."""
    return [q for q in QUESTION_BANK if q.dimension == dimension]


def get_question_by_id(qid: str) -> Optional[CompassQuestion]:
    """Find a question by ID."""
    for q in QUESTION_BANK:
        if q.id == qid:
            return q
    return None
