"""
Contact resolution for «كلّم ماما» / «ابعت لأحمد …».

Matching is EXACT (on folded names/aliases) — never fuzzy. STT confusions such as
«مامي/ماميتي» are handled by the owner listing them as aliases, not by guessing.
A close-but-wrong guess here would mean calling the wrong person, so when a name
is unknown or ambiguous we ask instead of picking (benefits_section.docx §14.5:
«الأسماء العربي: التأكيد الصوتي قبل الاتصال شرط»).
"""

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence

from app.services.phone_action.textutil import fold, strip_marks

_NUMBER_RE = re.compile(r"(\+?\d[\d\s\-]{5,18}\d)")


@dataclass
class ContactMatch:
    contact: Optional[object] = None          # ORM Contact (or duck-typed)
    remainder_light: str = ""                 # text after the name (message body)
    ambiguous: List[object] = field(default_factory=list)


def contact_keys(contact) -> List[str]:
    """All folded spoken forms of a contact, longest first (with/without «ال»)."""
    raw = [contact.name] + [a for a in (contact.aliases or "").split(",")]
    keys = set()
    for r in raw:
        k = fold(strip_marks(r)).strip()
        if not k:
            continue
        keys.add(k)
        if k.startswith("ال") and len(k) > 3:
            keys.add(k[2:])
    return sorted(keys, key=len, reverse=True)


def _start_offsets(rest_norm: str) -> List[int]:
    """Possible name start offsets: as-is, minus a leading ب/ل particle, minus «علي »."""
    offsets = [0]
    if len(rest_norm) > 1 and rest_norm[0] in "بل":
        offsets.append(2 if rest_norm[1] == " " else 1)
    if rest_norm.startswith("علي "):
        offsets.append(4)
    return offsets


def match_contact(
    rest_norm: str,
    rest_light: str,
    contacts: Iterable,
    *,
    require_full: bool,
) -> ContactMatch:
    """
    Find the allow-listed contact named at the start of `rest_norm`.
    `require_full=True` (calls) demands the name is the WHOLE remainder, so
    «كلم ماما وبابا» does not silently call "ماما".
    """
    best_len = 0
    hits: dict = {}
    best_consumed = 0
    for contact in contacts:
        if not getattr(contact, "is_allowlisted", True):
            continue
        for key in contact_keys(contact):
            for off in _start_offsets(rest_norm):
                sub = rest_norm[off:]
                exact = sub == key
                prefix = (not require_full) and sub.startswith(key + " ")
                if exact or prefix:
                    if len(key) > best_len:
                        best_len, hits, best_consumed = len(key), {}, off + len(key)
                    if len(key) == best_len:
                        hits[contact.id] = contact
                        best_consumed = max(best_consumed, off + len(key))
    if not hits:
        return ContactMatch()
    if len(hits) > 1:
        return ContactMatch(ambiguous=list(hits.values()))
    only = next(iter(hits.values()))
    return ContactMatch(contact=only, remainder_light=rest_light[best_consumed:].strip())


def extract_number(rest_norm: str) -> Optional[str]:
    """A dialled number spoken as digits («كلم 01012345678»). Returns normalised digits or None."""
    m = _NUMBER_RE.search(rest_norm)
    if not m:
        return None
    digits = re.sub(r"[\s\-]", "", m.group(1))
    plus = digits.startswith("+")
    body = digits.lstrip("+")
    if not body.isdigit() or not (7 <= len(body) <= 15):
        return None
    return ("+" if plus else "") + body


def normalize_phone(raw: str) -> Optional[str]:
    """Validate/normalise a stored phone number; None if it is not a plausible number."""
    cleaned = re.sub(r"[\s\-()]", "", raw or "")
    plus = cleaned.startswith("+")
    body = cleaned.lstrip("+")
    if not body.isdigit() or not (7 <= len(body) <= 15):
        return None
    return ("+" if plus else "") + body


def mask_number(number: str) -> str:
    """Display-safe form, e.g. +2010****5678."""
    if not number:
        return ""
    keep_head = 5 if number.startswith("+") else 3
    if len(number) <= keep_head + 3:
        return "*" * len(number)
    return number[:keep_head] + "*" * (len(number) - keep_head - 4) + number[-4:]
