"""Clinic content (menus, fixed answers, treatments), read-only JSON in app/clinics.

CL01.json is exported from the approved Arya mock (frontend/widgets/mock/arya.ts), so the wording and
links are exactly the ones the widget tests check.
"""

import json
from functools import cache
from pathlib import Path
from typing import Any

DIR = Path(__file__).resolve().parent.parent / "clinics"


@cache
def content(clinic_id: str) -> dict[str, Any] | None:
    path = DIR / f"{clinic_id}.json"
    if not path.is_file():
        return None
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data
