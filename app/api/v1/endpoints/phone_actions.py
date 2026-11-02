"""
Phone Actions API Endpoints — Contacts, Reminders, Voiceprint Enrolment,
Audit Logs, and Level-3 External Approval (benefits_section.docx Chapter 14).
"""

from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user_model
from app.core.config import settings
from app.core.logger import get_logger
from app.db.session import get_db
from app.models.action_log import ActionLog
from app.models.contact import Contact
from app.models.reminder import Reminder
from app.models.user import User
from app.models.voiceprint import Voiceprint
from app.services.phone_action import get_phone_action_service
from app.services.ai.universal_action import (
    UniversalActionParseResponse,
    UniversalActionExecuteRequest,
    UniversalActionExecuteResponse,
    get_universal_action_planner,
    get_action_capabilities,
)
from app.services.phone_action.contacts import normalize_phone
from app.services.voice_verification.speaker_service import (
    VoiceprintError,
    get_speaker_service,
)

logger = get_logger(__name__)

router = APIRouter()


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class ContactCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, description="الاسم كما ينطق (مثال: ماما)")
    phone_number: str = Field(..., min_length=7, max_length=32, description="رقم الهاتف الدولي أو المحلي")
    aliases: Optional[str] = Field("", max_length=255, description="أسماء بديلة ينطقها المستخدم (مثال: مامي,الوالدة)")
    slug: Optional[str] = Field("", max_length=64, description="المعرّف المرسل للهاتف (مثال: mama)")
    relationship: Optional[str] = Field(None, max_length=32, description="نوع العلاقة (mother, friend, work)")
    is_allowlisted: bool = Field(True, description="هل مسموح للروبوت الاتصال بهذه الجهة")
    requires_confirmation: bool = Field(True, description="طلب تأكيد لفظي قبل الاتصال")
    required_level: int = Field(1, ge=1, le=2, description="مستوى الأمان المطلوب (1 أو 2)")
    notify_on_missed: bool = Field(False, description="إبلاغ هذه الجهة عند إهمال تذكير الدوا")


class ContactUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    phone_number: Optional[str] = Field(None, min_length=7, max_length=32)
    aliases: Optional[str] = Field(None, max_length=255)
    slug: Optional[str] = Field(None, max_length=64)
    relationship: Optional[str] = Field(None, max_length=32)
    is_allowlisted: Optional[bool] = None
    requires_confirmation: Optional[bool] = None
    required_level: Optional[int] = Field(None, ge=1, le=2)
    notify_on_missed: Optional[bool] = None


class ContactResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    name: str
    aliases: str
    slug: str
    phone_number: str
    relationship: Optional[str] = None
    is_allowlisted: bool
    requires_confirmation: bool
    required_level: int
    notify_on_missed: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReminderCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120, description="نص التذكير (مثال: دوا الضغط)")
    reminder_type: str = Field("task", description="نوع التذكير: medicine | task | appointment")
    target_time: datetime = Field(..., description="موعد التنبيه (UTC)")
    recurrence: str = Field("once", description="التكرار: once | daily | weekly")
    escalation_contact_id: Optional[int] = Field(None, description="جهة الاتصال للإبلاغ عند عدم الرد")
    escalation_mode: str = Field("msg", description="وسيلة الإبلاغ: msg | call")


class ReminderResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    title: str
    reminder_type: str
    target_time: datetime
    recurrence: str
    status: str
    announced_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    escalated_at: Optional[datetime] = None
    escalation_contact_id: Optional[int] = None
    escalation_mode: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ActionLogResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    action_type: str
    target: Optional[str] = None
    security_level: int
    status: str
    reason: Optional[str] = None
    speaker_score: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True


class VoiceprintStatusResponse(BaseModel):
    enrolled: bool
    speaker_name: Optional[str] = None
    samples_count: int = 0
    max_level: int = 0
    model_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ChallengeRespondRequest(BaseModel):
    id: int = Field(..., description="معرّف سجل العملية (log_id)")
    approve: bool = Field(..., description="الموافقة (True) أو الرفض (False)")


# ── Contacts Endpoints ────────────────────────────────────────────────────────

@router.get("/contacts", response_model=List[ContactResponse], summary="List allowlisted contacts")
async def list_contacts(
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user_model),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve all contacts allowlisted for phone actions."""
    stmt = select(Contact)
    if not current_user.is_superuser:
        stmt = stmt.where(or_(Contact.user_id == current_user.id, Contact.user_id.is_(None)))
    if search:
        s = f"%{search.strip()}%"
        stmt = stmt.where(or_(Contact.name.ilike(s), Contact.aliases.ilike(s), Contact.slug.ilike(s)))
    stmt = stmt.order_by(Contact.name.asc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/contacts", response_model=ContactResponse, status_code=status.HTTP_201_CREATED, summary="Add allowlisted contact")
async def create_contact(
    body: ContactCreate,
    current_user: User = Depends(get_current_user_model),
    db: AsyncSession = Depends(get_db),
):
    """Register a new trusted contact with security tier and aliases."""
    norm_phone = normalize_phone(body.phone_number)
    if not norm_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="رقم الهاتف غير صالح. يجب إدخال رقم هاتف صحيح مع كود الدولة أو 01xxxxxxxxx.",
        )

    # Derive slug if not provided
    slug = (body.slug or "").strip().lower()
    if not slug:
        slug = re.sub(r"[^a-zA-Z0-9_\-]", "", body.name.lower()) or "contact"

    contact = Contact(
        user_id=current_user.id,
        name=body.name.strip(),
        aliases=(body.aliases or "").strip(),
        slug=slug,
        phone_number=norm_phone,
        relationship=body.relationship,
        is_allowlisted=body.is_allowlisted,
        requires_confirmation=body.requires_confirmation,
        required_level=body.required_level,
        notify_on_missed=body.notify_on_missed,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    logger.info(f"Added allowlisted contact: {contact.name} (id={contact.id}) for user {current_user.id}")
    return contact


@router.put("/contacts/{contact_id}", response_model=ContactResponse, summary="Update contact")
async def update_contact(
    contact_id: int,
    body: ContactUpdate,
    current_user: User = Depends(get_current_user_model),
    db: AsyncSession = Depends(get_db),
):
    """Update contact settings, aliases, or security level."""
    contact = await db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="جهة الاتصال غير موجودة.")
    if not current_user.is_superuser and contact.user_id != current_user.id and contact.user_id is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ليس لديك صلاحية لتعديل هذه الجهة.")

    if body.phone_number is not None:
        norm = normalize_phone(body.phone_number)
        if not norm:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="رقم الهاتف غير صالح.")
        contact.phone_number = norm
    if body.name is not None:
        contact.name = body.name.strip()
    if body.aliases is not None:
        contact.aliases = body.aliases.strip()
    if body.slug is not None:
        contact.slug = body.slug.strip().lower()
    if body.relationship is not None:
        contact.relationship = body.relationship
    if body.is_allowlisted is not None:
        contact.is_allowlisted = body.is_allowlisted
    if body.requires_confirmation is not None:
        contact.requires_confirmation = body.requires_confirmation
    if body.required_level is not None:
        contact.required_level = body.required_level
    if body.notify_on_missed is not None:
        contact.notify_on_missed = body.notify_on_missed

    await db.commit()
    await db.refresh(contact)
    return contact


@router.delete("/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete contact")
async def delete_contact(
    contact_id: int,
    current_user: User = Depends(get_current_user_model),
    db: AsyncSession = Depends(get_db),
):
    """Delete an allowlisted contact."""
    contact = await db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="جهة الاتصال غير موجودة.")
    if not current_user.is_superuser and contact.user_id != current_user.id and contact.user_id is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ليس لديك صلاحية لحذف هذه الجهة.")

    await db.delete(contact)
    await db.commit()
    return None


# ── Reminders Endpoints ───────────────────────────────────────────────────────

@router.get("/reminders", response_model=List[ReminderResponse], summary="List reminders")
async def list_reminders(
    active_only: bool = True,
    reminder_type: Optional[str] = None,
    current_user: User = Depends(get_current_user_model),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve active or historical reminders."""
    stmt = select(Reminder)
    if not current_user.is_superuser:
        stmt = stmt.where(or_(Reminder.user_id == current_user.id, Reminder.user_id.is_(None)))
    if active_only:
        stmt = stmt.where(Reminder.is_active == True)  # noqa: E712
    if reminder_type:
        stmt = stmt.where(Reminder.reminder_type == reminder_type)
    stmt = stmt.order_by(Reminder.target_time.asc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/reminders", response_model=ReminderResponse, status_code=status.HTTP_201_CREATED, summary="Create reminder")
async def create_reminder(
    body: ReminderCreate,
    current_user: User = Depends(get_current_user_model),
    db: AsyncSession = Depends(get_db),
):
    """Create a new medicine or task reminder with optional family escalation."""
    # Ensure target_time is UTC naive for SQLite
    target = body.target_time
    if target.tzinfo is not None:
        target = target.astimezone(timezone.utc).replace(tzinfo=None)

    reminder = Reminder(
        user_id=current_user.id,
        title=body.title.strip(),
        reminder_type=body.reminder_type,
        target_time=target,
        recurrence=body.recurrence,
        status="pending",
        escalation_contact_id=body.escalation_contact_id,
        escalation_mode=body.escalation_mode,
        is_active=True,
    )
    db.add(reminder)
    await db.commit()
    await db.refresh(reminder)
    logger.info(f"Created reminder: '{reminder.title}' at {reminder.target_time} (id={reminder.id})")
    return reminder


@router.patch("/reminders/{reminder_id}/acknowledge", response_model=ReminderResponse, summary="Acknowledge reminder")
async def acknowledge_reminder(
    reminder_id: int,
    current_user: User = Depends(get_current_user_model),
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge a reminder («خدت الدوا»), preventing escalation."""
    reminder = await db.get(Reminder, reminder_id)
    if not reminder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="التذكير غير موجود.")
    if not current_user.is_superuser and reminder.user_id != current_user.id and reminder.user_id is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ليس لديك صلاحية لتعديل هذا التذكير.")

    svc = get_phone_action_service()
    await svc.acknowledge_reminder(reminder_id)
    await db.refresh(reminder)
    return reminder


@router.delete("/reminders/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete or cancel reminder")
async def delete_reminder(
    reminder_id: int,
    current_user: User = Depends(get_current_user_model),
    db: AsyncSession = Depends(get_db),
):
    """Delete a reminder."""
    reminder = await db.get(Reminder, reminder_id)
    if not reminder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="التذكير غير موجود.")
    if not current_user.is_superuser and reminder.user_id != current_user.id and reminder.user_id is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ليس لديك صلاحية لحذف هذا التذكير.")

    reminder.is_active = False
    reminder.status = "cancelled"
    await db.commit()
    return None


# ── Audit Action Logs ─────────────────────────────────────────────────────────

@router.get("/logs", response_model=List[ActionLogResponse], summary="Query phone action audit logs")
async def query_action_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    action_type: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: User = Depends(get_current_user_model),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve privacy-by-design audit logs (events only).
    Zero phone numbers, zero messages, zero audio stored or returned.
    """
    stmt = select(ActionLog)
    if not current_user.is_superuser:
        stmt = stmt.where(or_(ActionLog.user_id == current_user.id, ActionLog.user_id.is_(None)))
    if action_type:
        stmt = stmt.where(ActionLog.action_type == action_type)
    if status_filter:
        stmt = stmt.where(ActionLog.status == status_filter)
    stmt = stmt.order_by(desc(ActionLog.created_at)).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return result.scalars().all()


# ── Voiceprint Management ─────────────────────────────────────────────────────

@router.get("/voiceprint/status", response_model=VoiceprintStatusResponse, summary="Get speaker voiceprint status")
async def get_voiceprint_status(
    current_user: User = Depends(get_current_user_model),
    db: AsyncSession = Depends(get_db),
):
    """Check if the current authenticated user has an enrolled acoustic voiceprint."""
    row = (
        await db.execute(select(Voiceprint).where(Voiceprint.user_id == current_user.id))
    ).scalar_one_or_none()
    if not row:
        return VoiceprintStatusResponse(enrolled=False)
    return VoiceprintStatusResponse(
        enrolled=True,
        speaker_name=row.speaker_name,
        samples_count=row.samples_count,
        max_level=row.max_level,
        model_id=row.model_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/voiceprint/enroll", response_model=VoiceprintStatusResponse, summary="Enroll speaker voiceprint")
async def enroll_voiceprint(
    speaker_name: str = Form(..., description="اسم المتحدث"),
    max_level: int = Form(2, ge=0, le=3, description="أقصى مستوى أمني مسموح لهذا المتحدث (1 أو 2)"),
    files: List[UploadFile] = File(..., description="ملفات صوتية WAV بصوت المستخدم (5 إلى 20 عينة)"),
    current_user: User = Depends(get_current_user_model),
    db: AsyncSession = Depends(get_db),
):
    """
    Enroll a voiceprint using 5–20 PCM16 WAV audio samples.
    Audio recordings are discarded immediately after computing the acoustic embedding.
    """
    if len(files) < settings.SPEAKER_ENROLL_MIN_SAMPLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"يجب توفير {settings.SPEAKER_ENROLL_MIN_SAMPLES} عينات صوتية على الأقل لتدريب بصمة الصوت.",
        )
    if len(files) > settings.SPEAKER_ENROLL_MAX_SAMPLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"الحد الأقصى للعينات هو {settings.SPEAKER_ENROLL_MAX_SAMPLES} عينات.",
        )

    samples: List[bytes] = []
    for f in files:
        content = await f.read()
        if len(content) < 1000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"الملف {f.filename} قصير جداً أو فارغ.",
            )
        samples.append(content)

    verifier = get_speaker_service()
    try:
        vp = await verifier.enroll(
            db,
            user_id=current_user.id,
            speaker_name=speaker_name.strip(),
            samples=samples,
            max_level=max_level,
        )
        await db.commit()
        await db.refresh(vp)
        logger.info(f"Enrolled voiceprint for user {current_user.id} ({speaker_name}) with {vp.samples_count} samples")
        return VoiceprintStatusResponse(
            enrolled=True,
            speaker_name=vp.speaker_name,
            samples_count=vp.samples_count,
            max_level=vp.max_level,
            model_id=vp.model_id,
            created_at=vp.created_at,
            updated_at=vp.updated_at,
        )
    except VoiceprintError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        await db.rollback()
        logger.error(f"Voiceprint enrolment error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="فشل تدريب بصمة الصوت بسبب خطأ في الخادم.",
        ) from e


@router.delete("/voiceprint", status_code=status.HTTP_204_NO_CONTENT, summary="Delete user voiceprint (Right to be forgotten)")
async def delete_voiceprint(
    current_user: User = Depends(get_current_user_model),
    db: AsyncSession = Depends(get_db),
):
    """Delete speaker voiceprint and purge cached embeddings."""
    verifier = get_speaker_service()
    deleted = await verifier.delete(db, user_id=current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="لا توجد بصمة صوت مسجلة لحسابك.")
    await db.commit()
    logger.info(f"Purged voiceprint for user {current_user.id}")
    return None


# ── Level 3 External Approval ────────────────────────────────────────────────

@router.post("/challenge/respond", summary="External confirmation for Level-3 or sensitive actions")
async def respond_external_challenge(
    body: ChallengeRespondRequest,
    current_user: User = Depends(get_current_user_model),
):
    """
    Approve or reject a pending Level-3 external confirmation request
    from the Desktop Control Room.
    """
    svc = get_phone_action_service()
    ok = await svc.confirm_external(body.id, body.approve)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="الطلب غير موجود، أو انتهت صلاحيته، أو ليس في مرحلة التأكيد الخارجي.",
        )
    return {"ok": True, "message": "تم اعتماد قرارك بنجاح." if body.approve else "تم إلغاء الطلب."}


# ── LLM Integration APIs (Speaker, Action & Voice Verification) ──────────────

class ActionParseRequest(BaseModel):
    utterance: str = Field(..., description="نص الطلب أو الأمر من المستخدم (مثال: 'كلم ماما')")
    speaker_name: Optional[str] = Field(None, description="اسم المتحدث إن وجد")
    is_verified: bool = Field(False, description="هل تم التحقق من بصمة صوته")
    verification_level: int = Field(1, description="مستوى الأمان المصرح به (1 أو 2 أو 3)")


class ActionParseResponse(BaseModel):
    has_action: bool
    intent: Optional[str] = None
    target: Optional[str] = None
    contact_name: Optional[str] = None
    contact_slug: Optional[str] = None
    is_allowlisted: bool = False
    requires_confirmation: bool = True
    decision: str  # ready | needs_confirm | unknown_contact | unverified_speaker | none
    suggested_speech: str
    llm_directive: str
    metadata: Dict[str, Any]


class LLMBundleRequest(BaseModel):
    message: str = Field(..., description="رسالة المستخدم أو الاستعلام")
    personality_id: Optional[int] = Field(None, description="معرف الشخصية (اختياري)")
    verified_speaker: Optional[str] = Field(None, description="اسم المتحدث الموثق")
    speaker_verification: Optional[Dict[str, Any]] = Field(None, description="بيانات التحقق الصوتي التفصيلية")


@router.post(
    "/parse",
    response_model=ActionParseResponse,
    summary="Parse action utterance into structured data and LLM directive",
)
async def parse_action_utterance(
    body: ActionParseRequest,
    db: AsyncSession = Depends(get_db),
) -> ActionParseResponse:
    """
    Method 2 (API): Parses an utterance (e.g. «كلّم ماما», «افتح الخرايط», «فكرني بالدوا»)
    against allowlisted contacts and security levels, returning structured data + LLM directive.
    Strictly deterministic.
    """
    from app.services.phone_action.planner import ActionPlanner, CALL, MSG, APP_OPEN, REMINDER, SENSITIVE
    from app.services.phone_action.contacts import match_contact
    from app.services.phone_action.service import _APP_DISPLAY

    planner = ActionPlanner()
    intent = planner.plan(body.utterance)

    if intent and intent.kind in (CALL, MSG):
        stmt = select(Contact).where(Contact.is_allowlisted == True)
        contacts_res = await db.execute(stmt)
        allowlisted = list(contacts_res.scalars().all())

        match = match_contact(intent.raw_norm, intent.raw_light, allowlisted, require_full=(intent.kind == CALL))

        if match.contact:
            c = match.contact
            req_conf = getattr(c, "requires_confirmation", True)
            req_level = getattr(c, "required_level", 1)

            # Check speaker verification security clearance
            if req_level >= 2 and not body.is_verified:
                return ActionParseResponse(
                    has_action=True,
                    intent=intent.kind,
                    target=c.name,
                    contact_name=c.name,
                    contact_slug=c.slug,
                    is_allowlisted=True,
                    requires_confirmation=req_conf,
                    decision="unverified_speaker",
                    suggested_speech="مش قادر أتأكد إن ده صوتك، فمش هنفّذ الطلب ده.",
                    llm_directive=f"المتحدث غير موثق بالبصمة الصوتية ومستوى الأمان للجهة {c.name} يتطلب توثيقاً. ارفض الطلب بأدب.",
                    metadata={"security_level_required": req_level, "contact_id": c.id},
                )

            decision = "needs_confirm" if req_conf else "ready"
            speech = f"أكلم لك {c.name} دلوقتي؟" if req_conf else f"بتصل بـ {c.name} حالاً."
            directive = (
                f"المستخدم يطلب الاتصال بـ '{c.name}'. وهي جهة اتصال مسموحة تتطلب تأكيداً لفظياً. اسأله لتأكيد الاتصال."
                if req_conf else
                f"المستخدم يطلب الاتصال بـ '{c.name}'. الاتصال جاهز ومسموح. أكد له أنك تتصل الآن."
            )

            return ActionParseResponse(
                has_action=True,
                intent=intent.kind,
                target=c.name,
                contact_name=c.name,
                contact_slug=c.slug,
                is_allowlisted=True,
                requires_confirmation=req_conf,
                decision=decision,
                suggested_speech=speech,
                llm_directive=directive,
                metadata={"contact_id": c.id, "slug": c.slug, "relationship": getattr(c, "relationship", None)},
            )
        else:
            raw_tgt = intent.raw_light.strip() or "الجهة المطلوبة"
            return ActionParseResponse(
                has_action=True,
                intent=intent.kind,
                target=raw_tgt,
                contact_name=None,
                contact_slug=None,
                is_allowlisted=False,
                requires_confirmation=True,
                decision="unknown_contact",
                suggested_speech="مش لاقي الاسم ده في جهات الاتصال المسموحة.",
                llm_directive=f"طلب المستخدم التواصل مع '{raw_tgt}' وهو اسم غير موجود في جهات الاتصال المسموحة. ارفض الطلب واذكر أنه غير مسجل.",
                metadata={"raw_query": intent.raw_light},
            )

    elif intent and intent.kind == APP_OPEN:
        app_id = intent.params.get("app")
        app_name = _APP_DISPLAY.get(app_id, intent.params.get("requested", app_id or "التطبيق"))
        if app_id:
            return ActionParseResponse(
                has_action=True,
                intent=APP_OPEN,
                target=app_name,
                contact_name=None,
                contact_slug=None,
                is_allowlisted=True,
                requires_confirmation=False,
                decision="ready",
                suggested_speech=f"تمام، بفتحلك {app_name} حالاً.",
                llm_directive=f"المستخدم يطلب فتح تطبيق {app_name}. أكد له أن التطبيق قيد الفتح.",
                metadata={"app_id": app_id},
            )
        else:
            req = intent.params.get("requested", "التطبيق")
            return ActionParseResponse(
                has_action=True,
                intent=APP_OPEN,
                target=req,
                contact_name=None,
                contact_slug=None,
                is_allowlisted=False,
                requires_confirmation=False,
                decision="app_not_allowed",
                suggested_speech="التطبيق ده مش مسموح أفتحه.",
                llm_directive=f"التطبيق المطلوب ({req}) غير مصرح به. ارفض الطلب بأدب.",
                metadata={},
            )

    elif intent and intent.kind == REMINDER:
        title = intent.params.get("title", "تذكير")
        return ActionParseResponse(
            has_action=True,
            intent=REMINDER,
            target=title,
            contact_name=None,
            contact_slug=None,
            is_allowlisted=True,
            requires_confirmation=False,
            decision="ready",
            suggested_speech=f"تمام، فكرتك بـ {title} في ميعادها.",
            llm_directive=f"المستخدم يطلب تذكيراً: '{title}'. أكد له حفظ التذكير في الموعد المحدد.",
            metadata=intent.params,
        )

    elif intent and intent.kind == SENSITIVE:
        if not body.is_verified:
            return ActionParseResponse(
                has_action=True,
                intent=SENSITIVE,
                target=intent.params.get("action_type", "sensitive"),
                contact_name=None,
                contact_slug=None,
                is_allowlisted=False,
                requires_confirmation=True,
                decision="unverified_speaker",
                suggested_speech="الطلب ده حساس ولازم أتأكد من بصمة صوتك الأول.",
                llm_directive="الطلب من العمليات الحساسة (Level 3) وبصمة الصوت غير موثقة. ارفض الطلب فوراً.",
                metadata=intent.params,
            )

    # Evaluate via Universal Action Planner across all domains (Motion, Screen, Vision, Device, Media, Reminders)
    c_stmt = select(Contact).where(Contact.is_allowlisted == True)
    c_res = await db.execute(c_stmt)
    allowlisted = list(c_res.scalars().all())

    uni_res = get_universal_action_planner().evaluate(
        utterance=body.utterance,
        speaker_name=body.speaker_name,
        is_verified=body.is_verified,
        verification_level=body.verification_level,
        allowlisted_contacts=allowlisted,
    )
    if uni_res.has_action:
        return ActionParseResponse(
            has_action=True,
            intent=uni_res.action,
            target=uni_res.target,
            contact_name=uni_res.params.get("contact_name"),
            contact_slug=uni_res.params.get("slug"),
            is_allowlisted=(uni_res.decision != "unknown_contact" and uni_res.decision != "app_not_allowed"),
            requires_confirmation=(uni_res.decision == "needs_confirm"),
            decision=uni_res.decision,
            suggested_speech=uni_res.suggested_speech,
            llm_directive=uni_res.llm_directive,
            metadata={
                "domain": uni_res.domain,
                "action": uni_res.action,
                "action_tag": uni_res.action_tag,
                "execution_payload": uni_res.execution_payload,
                "tool_call": uni_res.tool_call,
                **uni_res.metadata,
                **uni_res.params,
            },
        )

    return ActionParseResponse(
        has_action=False,
        intent=None,
        target=None,
        contact_name=None,
        contact_slug=None,
        is_allowlisted=False,
        requires_confirmation=False,
        decision="none",
        suggested_speech="",
        llm_directive="",
        metadata={},
    )


@router.get(
    "/llm-context",
    summary="Get actions, allowlisted contacts, and reminders formatted for LLM context",
)
async def get_actions_llm_context(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns full allowlisted contacts, supported apps, and active reminders
    formatted as structured data ready to be passed directly to the LLM.
    """
    from app.services.phone_action.planner import _APP_NAMES

    c_stmt = select(Contact).where(Contact.is_allowlisted == True)
    c_res = await db.execute(c_stmt)
    contacts = [
        {
            "name": c.name,
            "slug": c.slug,
            "relationship": c.relationship,
            "requires_confirmation": c.requires_confirmation,
            "required_level": c.required_level,
        }
        for c in c_res.scalars().all()
    ]

    r_stmt = select(Reminder).where(Reminder.is_active == True, Reminder.status == "pending")
    r_res = await db.execute(r_stmt)
    reminders = [{"id": r.id, "title": r.title, "type": r.reminder_type} for r in r_res.scalars().all()]

    return {
        "contacts_count": len(contacts),
        "allowlisted_contacts": contacts,
        "supported_apps": list(_APP_NAMES.keys()),
        "active_reminders": reminders,
        "capabilities": ["call", "msg", "app_open", "reminder"],
    }


@router.post(
    "/llm-bundle",
    summary="Create full LLM Grounding Bundle (Metadata + Prompt + RAG + Actions + Speaker)",
)
async def create_llm_bundle(
    body: LLMBundleRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Unified API for LLM consumption:
    Takes user query, speaker info, and voice verification state.
    Generates the complete grounded system prompt, messages list, RAG memories,
    and structured metadata (Speaker, Action, Voice Verification).
    """
    from app.services.ai.context_builder import build_grounding_context
    from app.providers.llm.prompt_builder import build_rag_messages

    active_prompt, memories, grounding, active_pid = await build_grounding_context(
        db=db,
        personality_id=body.personality_id,
        message=body.message,
        verified_speaker=body.verified_speaker,
        speaker_verification=body.speaker_verification,
    )

    messages = build_rag_messages(
        prompt=body.message,
        context=memories,
        system_prompt=active_prompt,
        speaker_info=grounding.speaker,
        action_info=grounding.action,
        voice_verification=grounding.voice_verification,
    )

    return {
        "query": body.message,
        "personality_id": active_pid,
        "system_prompt": active_prompt,
        "messages": messages,
        "has_action": grounding.action.get("has_action", False),
        "action": grounding.action,
        "speaker": grounding.speaker,
        "voice_verification": grounding.voice_verification,
        "memories": memories,
    }


@router.post(
    "/universal/parse",
    response_model=UniversalActionParseResponse,
    summary="Universal Action Parser across all domains (Motion, Screen, Vision, Device, Phone, Media, Sensitive)",
)
async def universal_parse_action(
    body: ActionParseRequest,
    db: AsyncSession = Depends(get_db),
) -> UniversalActionParseResponse:
    """
    Method 2 (API): Universal Action Evaluator.
    Parses any utterance (gestures, screen eyes mood, gaze, camera photo, IoT light, phone calls, reminders)
    and verifies speaker authorization.
    """
    c_stmt = select(Contact).where(Contact.is_allowlisted == True)
    c_res = await db.execute(c_stmt)
    allowlisted = list(c_res.scalars().all())

    return get_universal_action_planner().evaluate(
        utterance=body.utterance,
        speaker_name=body.speaker_name,
        is_verified=body.is_verified,
        verification_level=body.verification_level,
        allowlisted_contacts=allowlisted,
    )


@router.get(
    "/universal/capabilities",
    summary="Get full action registry with schemas for LLM Tool / Function Calling",
)
async def get_universal_capabilities() -> Dict[str, Any]:
    """
    Method 2 (API): Returns the entire registry of executable tools and action schemas
    formatted for LLM function calling and system instructions.
    """
    caps = get_action_capabilities()
    return {
        "capabilities_count": len(caps),
        "domains": ["motion", "screen", "vision", "device", "phone", "reminder", "media", "sensitive"],
        "tools": caps,
    }


@router.post(
    "/universal/execute",
    response_model=UniversalActionExecuteResponse,
    summary="Execute any action command across ESP32, Phone, or Desktop",
)
async def execute_universal_action(
    body: UniversalActionExecuteRequest,
    db: AsyncSession = Depends(get_db),
) -> UniversalActionExecuteResponse:
    """
    Method 2 (API): Dispatches an authorized action to the target device channel
    (ESP32 / Phone / Desktop) with speaker verification safety gating.
    """
    from app.websocket.manager import manager

    # Level gating
    if body.domain == "sensitive" or body.action in ("memory_wipe", "payment"):
        if not body.is_verified or body.verification_level < 3:
            return UniversalActionExecuteResponse(
                ok=False,
                status="unverified_speaker",
                dispatched_channel="none",
                action=body.action,
                error="عملية حساسة تتطلب التحقق الصوتي وموافقة غرفة التحكم (Level 3)",
            )

    dispatched = "internal"
    payload = body.params

    try:
        if body.domain == "motion":
            dispatched = "esp"
            if body.action == "stop":
                await manager.send_to_esp({"t": "stop"})
                payload = {"t": "stop"}
            else:
                from app.websocket.handlers import _get_signal_planner, _get_motion_guard
                planner = _get_signal_planner()
                guard = _get_motion_guard()
                cmds = await planner.resolve(body.action)
                payload = {"commands": [c.model_dump() for c in cmds]}
                for c in cmds:
                    safe = guard.validate_joint(c)
                    if safe:
                        await manager.send_to_esp(safe.model_dump())

        elif body.domain == "screen":
            if body.action == "eyes_mood":
                dispatched = "phone"
                payload = {"t": "eyes", "mood": body.params.get("mood", "happy")}
                await manager.send_to_phone(payload)
            elif body.action == "gaze":
                dispatched = "phone"
                payload = {"t": "gaze", **body.params}
                await manager.send_to_phone(payload)
            elif body.action == "show_person_photo":
                dispatched = "desk"
                payload = {"t": "screen_action", "action": "show_person_photo", "name": body.target}
                await manager.broadcast_to_desks(payload)

        elif body.domain == "device":
            dispatched = "esp"
            if body.action == "light_toggle":
                payload = {"t": "relay", "pin": 1, "state": body.params.get("state", True)}
                await manager.send_to_esp(payload)

        elif body.domain == "vision":
            if body.action == "capture_photo":
                dispatched = "phone"
                payload = {"t": "camera_capture"}
                await manager.send_to_phone(payload)

        return UniversalActionExecuteResponse(
            ok=True,
            status="dispatched",
            dispatched_channel=dispatched,
            action=body.action,
            payload=payload,
        )
    except Exception as e:
        logger.error(f"Error executing universal action {body.action}: {e}")
        return UniversalActionExecuteResponse(
            ok=False,
            status="error",
            dispatched_channel=dispatched,
            action=body.action,
            error=str(e),
        )
