# Survey Report: AI Context Builder & Strict RAG Memory Grounding in Egyptian Arabic (`arz`)

**Agent**: Explorer 2 (AI Context & RAG Explorer)  
**Date**: 2026-11-02  
**Scope**: Codebase Survey, RAG Memory Data Flow Analysis, Egyptian Arabic Prompt Architecture, and Verification Suite Design for R3.

---

## 1. Executive Summary

This survey evaluates `app/services/ai/context_builder.py` and its surrounding AI ecosystem (`app/services/ai/pipeline.py`, `app/services/memory/rag_service.py`, `app/services/memory/fact_verifier.py`, `app/providers/llm/*`, and `app/api/v1/endpoints/conversations.py`).

### Key Findings
1. **Broken Multi-Language Branching in `context_builder.py`**:
   Lines 327–406 in `app/services/ai/context_builder.py` contain dead/redundant code where English prompt templates are repeatedly defined and overwritten, including Arabic fragments pasted into the English branch. In addition, runtime code imports translation functions from `scripts/generate_rag_dataset.py`, violating production modularity.
2. **Missing Negative Grounding Directives when Memories are Present**:
   When memories are found (`if memories:` at line 257), the generated prompt instructs the LLM to extract the answer, but omits strict negative constraints (what to do if the user asks for a detail not present in the retrieved memory, such as a phone number or unrecorded attribute). Furthermore, hardware telemetry and active personality details are omitted from the prompt when memories exist, creating an inconsistency between branches.
3. **Compatibility Anchor with Existing Integration Tests**:
   `tests/integration/test_chat_endpoint.py` (line 151) verifies that the generated system prompt contains specific verbatim strings:
   `"مازن عبد الرحيم"`, `"alex"`, `"samples/voice1.wav"`, `"الشخصية النشطة"`, `"التشخيص وحالة الأجهزة"`.
   Any refactoring must ensure this system context block is preserved consistently.
4. **Zero Unit Tests for `context_builder.py`**:
   There are currently **no** dedicated unit tests for `context_builder.py` in `tests/unit/`. The module is only exercised indirectly via `tests/integration/test_chat_endpoint.py`. A dedicated test file `tests/unit/test_context_builder.py` is needed.

---

## 2. Detailed Codebase Survey of `context_builder.py` and Related AI Services

### 2.1 File Map & Call Hierarchy
```
User / Phone Audio / Web Client
       │
       ▼
app/services/ai/pipeline.py (Voice stream: _run_pipeline / Text: process_text)
  OR
app/api/v1/endpoints/conversations.py (REST / SSE: chat, chat_stream)
       │
       ▼ calls
app/services/ai/context_builder.py (build_grounding_context)
       │
       ├── 1. Personality Resolution ──────────> DB: app/models/personality.py
       ├── 2. Face / Visual Profile ───────────> app/services/memory/person_retriever.py & UniFace
       ├── 3. RAG Memory Retrieval ────────────> app/services/memory/rag_service.py
       │                                           ├── BM25Okapi (sparse)
       │                                           ├── DatabaseVectorStore (dense)
       │                                           ├── QueryDecomposer (sub-queries)
       │                                           └── CrossReranker (reranking)
       ├── 4. Voice Sample & Speaker ID ───────> app/services/voice_clone / speaker_service
       ├── 5. Hardware Diagnostics ────────────> app/websocket/manager.py
       ├── 6. Trusted Contacts & Reminders ────> DB: Contact, Reminder
       └── 7. System Prompt Assembly (arz) ────> Output to LLM Provider
```

### 2.2 Anatomy of `app/services/ai/context_builder.py`
- **Lines 24–30 (`GroundingInfo`)**: Pydantic schema returning metadata (`personality`, `faces`, `voice_clone`, `diagnostics`, `memories`).
- **Lines 32–59 (`is_greeting_or_persona_inquiry`)**: Regex and keyword matching for greetings (e.g. "صباح الخير", "ازيك", "عامل إيه") and creator/persona inquiries (e.g. "أنت مين", "مين صممك", "اسمك إيه").
- **Lines 61–129 (Step 1: Personality Routing)**:
  - Scans query text for personality keywords (e.g., "منه", "مازن", or names of DB personalities).
  - Falls back to `personality_id`, then active personality in DB, and finally `"توت (Default)"`.
- **Lines 131–186 (Step 2: Faces & Vision Grounding)**:
  - Fetches registered names via `PersonImageRetriever.get_all_registered_names`.
  - Queries active camera face from `face_service.get_current_face_info()`.
  - Determines active candidate person and loads `person_profile` (including `photo_url`).
- **Lines 188–195 (Step 3: RAG Memory Retrieval)**:
  - Calls `await _rag_service.retrieve(message, personality_id=target_p.id, db=db, person_name=rag_person)`.
- **Lines 197–212 (Step 4 & 5: Voice Clone & Diagnostics)**:
  - Gathers TTS provider, voice sample path, verified speaker, and hardware connection flags (`phone`, `desktop`, `esp32`).
- **Lines 213–229 (Step 6: Contacts & Reminders)**:
  - Loads allowlisted contact names (strictly without phone numbers) and active reminders.
- **Lines 230–254 (Step 7a: Persona Metadata & Dialect)**:
  - Resolves creator name (defaulting to "منه محمد" or "مازن عبد الرحيم").
  - Computes `phone_str`, `desk_str`, `esp_str` ("متصل" / "غير متصل").
- **Lines 255–406 (Step 7b: System Prompt Assembly)**:
  - Current implementation branches on `is_arabic`.
  - If Arabic with memories: creates an over-simplified prompt with few examples and omits system diagnostics.
  - If Arabic without memories: generates refusal prompt with operational directives and hardware status.
  - If non-Arabic: messy, duplicated, and partly overwritten English/Arabic code.

---

## 3. How Memory Retrieval (RAG) is Structured, Passed, and Formatted

### 3.1 Retrieval Data Flow
1. **Input Parameters**:
   - `query: str` (User query text)
   - `personality_id: Optional[int]`
   - `person_name: Optional[str]` (Identified from camera face, voiceprint, or text entity extraction)
   - `db: AsyncSession`
2. **Retrieval Process (`RAGService.retrieve`)**:
   - Fetches candidate records from `memories` table (filtered by `personality_id` or global memories).
   - Synchronizes in-memory `DatabaseVectorStore` with current memory IDs.
   - Tokenizes corpus with `ArabicBM25Tokenizer` and builds `BM25Okapi` index.
   - Decomposes query into sub-queries via `QueryDecomposer.decompose(query)`.
   - Runs parallel search across `_RAG_EXECUTOR` thread pool combining normalized dot product vectors and BM25 scores.
   - Merges and reranks candidates using `CrossReranker.rerank_async`.
   - Filters out matches with score `< 0.35` and applies a `0.75 * top_score` cutoff.
   - Normalizes and deduplicates repeated contents (`_normalize_for_dedup`).
   - Applies **Context Re-ordering** (`_reorder_context`: alternating `[1, 3, 5, 4, 2]`) to counter LLM "Lost in the Middle" attention degradation.
   - Asynchronously updates `last_accessed` timestamps in the background.
   - Returns `memories: List[str]`.

### 3.2 Formatting and Injection into System Prompts
In `context_builder.py`, each retrieved memory string is formatted into numbered or bulleted items:
```text
الذاكرة المعتمدة:
[المصدر 1]: <نص الذاكرة الأول>
[المصدر 2]: <نص الذاكرة الثاني>
```
When `system_prompt` is constructed, `build_grounding_context` returns `(grounded_system_prompt, memories, grounding_data, active_pid)`.

### 3.3 Provider De-duplication Contract
In `app/providers/llm/local_ollama.py` (lines 56–62) and `app/providers/llm/huggingface_provider.py` (lines 98–101):
```python
already_in_prompt = any(kw in effective_system_prompt for kw in ("ذكريات", "الذاكرة", "RAG Context", "Verified Context"))
if memories_text.strip() and not already_in_prompt:
    messages.append({"role": "system", "content": f"ذكريات مرتبطة:\n{memories_text}"})
```
Because the system prompt in `context_builder.py` explicitly contains `"الذاكرة"`, downstream LLM providers recognize the context is already integrated and avoid duplicating memory tokens in subsequent system messages.

---

## 4. Current Prompts, Persona Instructions, and Local LLM Invocation Patterns

### 4.1 Invocation Configuration (`app/core/config.py`)
- **`LLM_PROVIDER`**: `"local"` (Ollama) by default; supports `"huggingface"` / `"nile"`.
- **`LLM_MODEL`**: `"nebula-masri"`.
- **`LLM_TEMPERATURE`**: `0.0` (zero randomness; enforces deterministic adherence to prompt and context).
- **`LLM_TOP_P`**: `0.85`, **`LLM_REPEAT_PENALTY`**: `1.15`.
- **`LLM_MAX_TOKENS`**: `45` (enforces 1–2 short conversational sentences).
- **Stop Tokens**: `["<|eot_id|>", "<|end_of_text|>", "<|start_header_id|>", "<|end_header_id|>", "<|im_end|>"]`.

### 4.2 Fast Refusal Guardrail & Deterministic Verification
- **Pre-LLM Fast Shortcut** (`conversations.py:203` & `pipeline.py:453`):
  If `not has_memories and not is_greeting_persona`, the pipeline bypasses the LLM and instantly returns:
  `"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"` with 0ms LLM latency.
- **Post-LLM Fact Verifier** (`app/services/memory/fact_verifier.py`):
  Validates output against context. If ungrounded numbers or sensitive patterns (e.g. phone numbers matching `01[0125]\d{8}`, passwords) are detected that are absent from retrieved context, it sanitizes the output to:
  `"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"`.

---

## 5. Detailed Design for Enhancing `context_builder.py` in Egyptian Arabic (`arz`)

### 5.1 Language Unification (`arz`)
In accordance with **R1** and **R3**, all prompt templates inside `context_builder.py` must be unified in authentic Egyptian Arabic (`arz`). The broken English branch and external script dependencies (such as `scripts.generate_rag_dataset`) must be eliminated.

### 5.2 Strict RAG Grounding Directives (Directives Structure)

The enhanced prompt must enforce five strict pillars in Egyptian Arabic:

1. **الاعتماد الحصري والمطلق على الذاكرة المسترجعة (Sole Dependence on RAG Context)**:
   - النص الإرشادي: *"أنت تعتمد حصرياً وبدقة متناهية على المعلومات الواردة في قسم 'الذاكرة المعتمدة' فقط. ممنوع نهائياً تخمين أو اختراع أو افتراض أي أحداث أو ذكريات أو بيانات خارج النص المكتوب."*
2. **منع الهلوسة وحظر البيانات غير المذكورة (Negative Grounding & Zero Hallucination)**:
   - النص الإرشادي: *"إذا سُئلت عن أي تفصيلة أو معلومة غير مذكورة نصاً في الذاكرة المعتمدة (حتى لو كانت تفصيلة صغيرة مثل رقم هاتف، تاريخ، أو عنوان شخصي)، يُحظر عليك الإجابة أو التوقع. يجب الرد حصراً بعبارة الرفض المحددة."*
3. **صيغة الرفض المعيارية الموحدة (Standard Deterministic Refusal Phrasing)**:
   - النص الإرشادي: *"عند غياب المعلومة أو السؤال عن بيانات حساسة (مثل أرقام الهواتف أو كلمات السر أو أرقام الحسابات) غير مسجلة صراحة في الذاكرة، أجب فوراً وبدون أي كلام إضافي بالعبارة التالية فقط:
   'المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]'"*
4. **طبيعة الرد واللهجة المصرية القاهرية للنطق الصوتي (Spoken Cairo Dialect for TTS)**:
   - النص الإرشادي: *"أجب بالعامية المصرية القاهرية المهذبة المباشرة (جملة واحدة أو جملتين كحد أقصى) لتناسب قارئ الصوت التوليدي (TTS). يُمنع استخدام أي جداول، علامات نجمية، أو روابط إنترنت في نص الرد."*
5. **وسم المشاعر الإلزامي (Mandatory Emotion Tag)**:
   - النص الإرشادي: *"اختم ردك دائماً وبشكل إلزامي بوسم مشاعر واحد فقط في نهاية الجملة: [happy] أو [wave] أو [like] أو [neutral] أو [sad]."*

### 5.3 System Context Block (Preserving Test Compatibility)
To preserve test compatibility with `tests/integration/test_chat_endpoint.py`, the system context block must be included across all prompt branches:
```text
معلومات النظام والسياق النشط:
- الشخصية النشطة: {robot_name} (اللهجة: {p_info.get('dialect') or 'cairo'})
- بصمة الصوت: {voice_str}
- التشخيص وحالة الأجهزة: الهاتف ({phone_str}) | الحاسوب ({desk_str}) | شريحة الروبوت ({esp_str})
```
And conditionally appended:
- `- الكاميرا: الشخص أمامك هو {current_face['face_id']}.`
- `- الصوت: تم التعرف على المتحدث بالبصمة الصوتية: {verified_speaker}.`
- `- شاشة العرض والصور: صورة {person_profile['name']} مسجلة في النظام ومتاحة للعرض على الشاشة.`
- `- جهات الاتصال المسموحة (أسماء فقط): {', '.join(trusted_contacts)}.`
- `- التذكيرات الحالية: {', '.join(active_reminders_list)}.`

### 5.4 Proposed Prompt Templates (Egyptian Arabic `arz`)

#### Case A: Memories Present (`if memories:`)
```python
mem_bullets = "\n".join(f"[المصدر {idx}]: {m.strip()}" for idx, m in enumerate(memories, 1))
grounded_system_prompt = f"""أنت "{robot_name}" (Nebula)، {robot_desc}، صممه وطوره {creator_name}.
{persona_extra}

توجيهات التشغيل والاستناد الصارم للذاكرة (Strict RAG Grounding & Zero-Hallucination):
1. استخرج الإجابة حصراً وبدقة متناهية من سياق الذاكرة المعتمدة أدناه. ممنوع منعاً باتاً تخمين، تأليف، أو افتراض أي وقائع أو ذكريات أو تفاصيل لم تُذكر صراحة في المصادر.
2. إذا كان السؤال يطلب تفصيلة أو رقماً غير موجود نصاً في الذاكرة أدناه (مثل أرقام الهواتف الشخصية، كلمات السر، أو البيانات المالية)، يجب الرد حصراً بعبارة:
   "المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"
3. أسلوب الرد: أجب بجملة واحدة مباشرة أو جملتين كحد أقصى بالعامية المصرية القاهرية المهذبة لتناسب النطق الصوتي (TTS)، وبدون أي جداول أو علامات نجمية أو روابط.
4. وسم المشاعر: اختم إجابتك دائماً وبشكل إلزامي بوسم مشاعر واحد فقط في النهاية مثل: [happy] أو [wave] أو [like].

أمثلة توضيحية لأسلوب الإجابة المباشر ومنع التأليف:
- المصدر المعتمد: [المصدر 1]: أحمد مهندس برمجيات مقيم في حلوان.
  سؤال: أحمد شغال إيه؟
  إجابة: أحمد شغال مهندس برمجيات في حلوان. [like]
- المصدر المعتمد: [المصدر 1]: أحمد مهندس برمجيات مقيم في حلوان.
  سؤال: ممكن تديني رقم تليفون أحمد الشخصي؟
  إجابة: المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]

سياق الذاكرة المعتمدة:
{mem_bullets}

معلومات النظام والسياق النشط:
- الشخصية النشطة: {robot_name} (اللهجة: {p_info.get('dialect') or 'cairo'})
- بصمة الصوت: {voice_str}
- التشخيص وحالة الأجهزة: الهاتف ({phone_str}) | الحاسوب ({desk_str}) | شريحة الروبوت ({esp_str})
"""
```

#### Case B: Greeting or Persona Inquiry (`elif is_greeting_or_persona_inquiry(message):`)
```python
grounded_system_prompt = f"""أنت "{robot_name}" (Nebula)، {robot_desc}، صممه وطوره {creator_name}.
{persona_extra}

المستخدم يحييك أو يسأل عن هويتك وصانعك:
1. رحب بالمستخدم بلطف بلهجة مصرية قاهرية ودودة وعرفه بنفسك كـ {robot_name} وبصانعك {creator_name}، واسأله كيف تساعده اليوم.
2. أجب بإيجاز (جملة أو جملتين) بدون حشو أو جداول لتناسب الصوت.
3. اختم إجابتك دائماً بوسم مشاعر مناسب في النهاية مثل [happy] أو [wave].

معلومات النظام والسياق النشط:
- الشخصية النشطة: {robot_name} (اللهجة: {p_info.get('dialect') or 'cairo'})
- بصمة الصوت: {voice_str}
- التشخيص وحالة الأجهزة: الهاتف ({phone_str}) | الحاسوب ({desk_str}) | شريحة الروبوت ({esp_str})
"""
```

#### Case C: No Memories Available (`else:`)
```python
grounded_system_prompt = f"""أنت "{robot_name}" (Nebula)، {robot_desc}، صممه وطوره {creator_name}.
{persona_extra}

سياق الذاكرة: لا توجد أي معلومات مسجلة متعلقة بهذا السؤال.
تنبيه صارم لمنع الهلوسة والتخمين:
يجب الاعتذار فوراً وبدقة بدون أي تأليف بالعبارة المحددة التالية فقط:
"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"

قواعد التشغيل والتوجيه الصوتي:
1. أجب حصراً بالعامية المصرية القاهرية وبجملة الرفض المحددة أعلاه.
2. يُمنع منعاً باتاً تخمين أو افتراض أي إجابة خارج ما هو مسجل في الذاكرة.
3. اختم ردك دائماً بوسم المشاعر [wave].

معلومات النظام والسياق النشط:
- الشخصية النشطة: {robot_name} (اللهجة: {p_info.get('dialect') or 'cairo'})
- بصمة الصوت: {voice_str}
- التشخيص وحالة الأجهزة: الهاتف ({phone_str}) | الحاسوب ({desk_str}) | شريحة الروبوت ({esp_str})
"""
```

---

## 6. Existing and Needed Test Suites

### 6.1 Current Test Landscape
- `tests/unit/test_rag_llm.py`: Tests `app/providers/llm/prompt_builder.py` and lexical scoring of `RAGService`. Does **not** test `context_builder.py`.
- `tests/unit/test_multimodal_rag_extensions.py`: Tests `DatabaseVectorStore`, `PersonImageRetriever`, and `FactVerifier`.
- `tests/integration/test_chat_endpoint.py`: Tests `/api/v1/conversations/chat` end-to-end, asserting that certain substrings appear in the system prompt.
- `scripts/test_nile_rag.py` & `scripts/test_rag_hallucination.py`: Standalone benchmarking scripts for Ollama/Nile-Chat.

### 6.2 Proposed Dedicated Test Suite: `tests/unit/test_context_builder.py`
A new test file `tests/unit/test_context_builder.py` should be implemented to thoroughly verify prompt generation and grounding logic:

| Test Case Name | Purpose | Key Assertions |
|----------------|---------|----------------|
| `test_context_builder_grounded_with_memories` | Validates prompt when memories are returned | Asserts `سياق الذاكرة المعتمدة`, `[المصدر 1]`, `Strict RAG Grounding`, absence of English text, presence of system status block |
| `test_context_builder_empty_memories_refusal` | Validates refusal directive when no memories exist | Asserts `"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"`, presence of system status block |
| `test_context_builder_greeting_and_persona` | Validates welcoming prompt for greetings and creator inquiries | Asserts greeting response guidance, presence of robot and creator names |
| `test_context_builder_vision_and_screen_awareness` | Validates camera face and screen photo profile formatting | Asserts camera face profile line, photo URL line, and screen awareness directives |
| `test_context_builder_hardware_diagnostics_integration` | Validates phone, desktop, and ESP32 states | Asserts phone, desktop, ESP strings appear correctly formatted |
| `test_context_builder_negative_grounding_directives` | Validates anti-hallucination rules for unrecorded details | Asserts explicit prohibition against guessing phone numbers and passwords |

---

## 7. Recommendations for Implementation Phase
1. **Direct Edit**: Modify `app/services/ai/context_builder.py` directly without python injection.
2. **Clean Up Unused Imports**: Remove `from scripts.generate_rag_dataset import to_english_memory` from `context_builder.py`.
3. **Preserve Compatibility**: Keep the system status section (`معلومات النظام والسياق النشط:`) with `"الشخصية النشطة"`, `"التشخيص وحالة الأجهزة"`, etc., in all prompt branches so `test_chat_endpoint.py` continues to pass cleanly.
4. **Create New Test File**: Add `tests/unit/test_context_builder.py` to provide 100% unit test coverage for prompt formatting and grounding rules.
