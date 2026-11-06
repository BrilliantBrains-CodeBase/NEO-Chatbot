"""Clinic codes (migration 0040). A clinic's code comes from its name: the first letter of each word (Neo
Follicle Hair Transplant: NFHT), with a number added when that code is taken (BF, BF2). Older CL01-style codes
stay valid (the hidden test clinics CL98 and CL99 keep theirs).

Clinics renamed from an old code keep answering to it where outside systems may still send it: a cached
chatbot file on a website, the Cal.com webhook address, the Google Sheet script, and lead codes patients
already received (CL01-00003). Everything new uses the new code only.
"""

import re

# 2 to 10 capital letters or digits, starting with a letter: NFHT, BF, BF2, CL99.
CLINIC_CODE = r"^[A-Z][A-Z0-9]{1,9}$"

# Old code -> new code. BB Fertility (CL02 -> BF) had nothing outside pointing at it, so it needs no alias.
RENAMED = {"CL01": "NFHT"}


def current(code: str) -> str:
    """The clinic code in use today, for a code an outside system may still send."""
    return RENAMED.get(code, code)


def current_lead(code: str) -> str:
    """A lead code in use today: CL01-00003 -> NFHT-00003."""
    prefix, dash, number = code.partition("-")
    return f"{RENAMED[prefix]}-{number}" if dash and prefix in RENAMED else code


def code_from_name(name: str, taken: set[str]) -> str:
    """The first letter of each word of the name, in capitals (Neo Follicle Hair Transplant: NFHT). A one-word
    name gives its first two letters (Apollo: AP). Taken: a number is added (BF2, BF3...)."""
    words = re.findall(r"[A-Za-z0-9]+", name)
    base = "".join(w[0] for w in words).upper()
    if len(base) < 2 and words:
        base = words[0][:2].upper()
    base = re.sub(r"^[^A-Z]+", "", base)[:8]  # starts with a letter; room for a number
    if len(base) < 2:
        base = (base + "CL")[:2] if base else "CL"
    if base not in taken:
        return base
    for n in range(2, 100):
        if f"{base}{n}" not in taken:
            return f"{base}{n}"
    raise ValueError("No free clinic code for this name.")
