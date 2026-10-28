"""
Pydantic Schemas for User Registration, Login, Biometric Verification, and Password Reset.
Directly maps to the Neural Interface UI design (Register & Login screens).
"""

import re
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

try:
    import email_validator  # noqa: F401
    from pydantic import EmailStr
except ImportError:
    EmailStr = str  # fallback if email-validator package is missing


class UserRegister(BaseModel):
    """
    Schema for user registration as shown in the UI screen:
    - الاسم الكامل (Full Name)
    - البريد الإلكتروني (Email)
    - كلمة المرور المشفرة (Encrypted Password)
    - تأكيد كلمة المرور (Confirm Password)
    - أوافق على شروط استخدام الذكاء الاصطناعي المركزي (Accept Terms Checkbox)
    """
    full_name: str = Field(
        ...,
        min_length=2,
        max_length=128,
        description="الاسم الكامل للمستخدم (Full Name, e.g. د. عبد الرحمن الخالدي)",
    )
    email: EmailStr = Field(
        ...,
        description="البريد الإلكتروني الموحد (Email address)",
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=72,
        description="كلمة المرور المشفرة (At least 8 characters with letters & numbers)",
    )
    confirm_password: str = Field(
        ...,
        description="تأكيد كلمة المرور (Must match password)",
    )
    terms_accepted: bool = Field(
        ...,
        description="الموافقة على شروط استخدام الذكاء الاصطناعي المركزي",
    )

    @field_validator("full_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        clean = v.strip()
        if len(clean) < 2:
            raise ValueError("الاسم الكامل يجب أن يحتوي على حرفين على الأقل.")
        return clean

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("كلمة المرور يجب ألا تقل عن 8 خانات.")
        if not re.search(r"[a-zA-Z\u0600-\u06FF]", v):
            raise ValueError("كلمة المرور يجب أن تحتوي على أحرف.")
        if not re.search(r"[0-9]", v):
            raise ValueError("كلمة المرور يجب أن تحتوي على رقم واحد على الأقل.")
        return v

    @model_validator(mode="after")
    def validate_confirm_and_terms(self) -> "UserRegister":
        if self.password != self.confirm_password:
            raise ValueError("كلمة المرور وتأكيد كلمة المرور غير متطابقين.")
        if not self.terms_accepted:
            raise ValueError("يجب الموافقة على شروط استخدام الذكاء الاصطناعي المركزي للمتابعة.")
        return self


class UserLogin(BaseModel):
    """
    Schema for standard user login as shown in the UI screen:
    - البريد الإلكتروني (Email)
    - كلمة المرور (Password)
    - تذكّرني على هذا الجهاز (Remember me on this device)
    """
    email: EmailStr = Field(
        ...,
        description="البريد الإلكتروني المسجل",
    )
    password: str = Field(
        ...,
        min_length=1,
        description="كلمة المرور",
    )
    remember_me: bool = Field(
        False,
        description="تذكّرني على هذا الجهاز (تمديد صلاحية الجلسة إلى 30 يوماً)",
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class ForgotPasswordRequest(BaseModel):
    """Request password reset token for given email."""
    email: EmailStr = Field(..., description="البريد الإلكتروني لاستعادة الحساب")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class ResetPasswordRequest(BaseModel):
    """Reset password using secure token."""
    token: str = Field(..., min_length=10, description="رمز استعادة كلمة المرور")
    new_password: str = Field(..., min_length=8, max_length=72, description="كلمة المرور الجديدة")
    confirm_password: str = Field(..., description="تأكيد كلمة المرور الجديدة")

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("كلمة المرور الجديدة يجب ألا تقل عن 8 خانات.")
        if not re.search(r"[a-zA-Z\u0600-\u06FF]", v):
            raise ValueError("كلمة المرور يجب أن تحتوي على أحرف.")
        if not re.search(r"[0-9]", v):
            raise ValueError("كلمة المرور يجب أن تحتوي على رقم واحد على الأقل.")
        return v

    @model_validator(mode="after")
    def validate_matching_passwords(self) -> "ResetPasswordRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("كلمة المرور الجديدة وتأكيدها غير متطابقين.")
        return self


class UserResponse(BaseModel):
    """Public user profile response."""
    id: int
    full_name: str
    email: str
    is_active: bool
    has_biometric: bool = False
    personalities_count: int = 0
    created_at: datetime


class AuthTokenResponse(BaseModel):
    """JWT Token response returned upon login or registration."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class MessageResponse(BaseModel):
    """Generic status response."""
    message: str
    details: Optional[dict[str, Any]] = None
