"""
Phone-action services (benefits_section.docx, ch.14):
ActionPlanner → ActionGuard → challenge/confirm → WebSocket dispatch.
"""

from typing import Optional

from app.services.phone_action.service import ActionOutcome, PhoneActionService

_service: Optional[PhoneActionService] = None


def get_phone_action_service() -> PhoneActionService:
    """Process-wide singleton (one robot, one phone, one pending action)."""
    global _service
    if _service is None:
        _service = PhoneActionService()
    return _service


__all__ = ["ActionOutcome", "PhoneActionService", "get_phone_action_service"]
