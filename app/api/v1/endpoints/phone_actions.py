"""
Phone Actions API Endpoints — Contacts, Reminders, Voiceprint Enrolment,
Audit Logs, and Level-3 External Approval (benefits_section.docx Chapter 14).
"""

from datetime import datetime, timezone
import re
from typing import Any, List, Optional

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
