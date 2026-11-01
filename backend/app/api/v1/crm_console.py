"""Dashboard (the chatbot console) in the CRM, JSON only: each clinic's widget settings as a draft that staff
edit, then publish (migration 0019). Every value is checked here; the browser never writes the tables.
Clinic managers and BB Admin only. The live chatbot does not read these settings until it is switched over."""

import json
import re
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.chat import canvas, embed, kb, main_template, slots
from app.chat.content import content
from app.chat.flows import ist_now, normal_phone
from app.core.db import get_pool
from app.crm import permissions as perm
from app.crm.auth import Staff, staff
from app.crm.flow import Flow, FlowError, Problem, import_content, normalise
from app.crm.flow import check as check_flow
from app.crm.flow_eval import passed
from app.crm.flow_run import Context, run_checks, send, start

router = APIRouter(prefix="/crm/console", tags=["crm"])

COLOR = r"^#[0-9A-Fa-f]{6}$"


class Look(BaseModel):
    name: str = Field(default="Arya", min_length=2, max_length=40)
    enabled: bool = True
    logo: str = Field(default="", max_length=300_000)  # https URL or a small data:image (upload)
    avatar_letter: str = Field(default="A", min_length=1, max_length=2)
    # Header, as in the clinic designs: clinic name, then the location line and the tagline.
    location: str = Field(default="Marathahalli, Whitefield", max_length=60)
    tagline: str = Field(default="", max_length=13)  # e.g. "Instant Reply", then " · Powered by ..."
    header_arc: bool = True  # the soft arc in the light accent colour behind the header

    @field_validator("tagline", mode="before")
    @classmethod
    def _short(cls, v: Any) -> str:  # older drafts allowed 60
        return str(v or "")[:13]

    @field_validator("logo")
    @classmethod
    def _logo(cls, v: str) -> str:
        if v and not (v.startswith("https://") or v.startswith("data:image/")):
            raise ValueError("Use an https:// image address or upload an image.")
        return v


class Colours(BaseModel):
    """The widget's palette (defaults: Neo Follicle's widget today). The designs use the same roles for
    every clinic; only the values change."""

    main: str = Field(default="#3E74D9", pattern=COLOR)  # header, filled buttons, patient bubbles
    highlight: str = Field(default="#FFCC70", pattern=COLOR)  # online dot, unread badge, keyboard focus
    main_dark: str = Field(default="#2A56AE", pattern=COLOR)  # hover, sub-button text, bold text
    accent: str = Field(default="#8FB0EE", pattern=COLOR)  # header arc, typing dots, focus rings
    tint: str = Field(default="#EEF3FC", pattern=COLOR)  # icon wells, hover fills, selected slot
    surface: str = Field(default="#FAF6F7", pattern=COLOR)  # bot bubbles, home button
    line: str = Field(default="#EFE3E6", pattern=COLOR)  # borders and dividers
    text: str = Field(default="#262626", pattern=COLOR)  # body text, tile labels
    muted: str = Field(default="#6B5F63", pattern=COLOR)  # Back / Main menu, small text
    whatsapp: str = Field(default="#1F9D55", pattern=COLOR)  # WhatsApp button border
    dark_mode: bool = False  # follow the visitor's dark setting
    dark_page: str = Field(default="#1C191A", pattern=COLOR)
    dark_card: str = Field(default="#262223", pattern=COLOR)
    dark_text: str = Field(default="#F2ECEE", pattern=COLOR)
    dark_line: str = Field(default="#3A3436", pattern=COLOR)


class WidgetStyle(BaseModel):
    # Panel on desktop: small 340×540, medium 380×580 (the designs), large 420×640. On mobile: full screen.
    size: Literal["small", "medium", "large"] = "medium"
    radius: Literal["square", "rounded", "round"] = "rounded"  # 8, 20 (the designs), 28 px
    border: Literal["none", "subtle", "strong"] = "subtle"
    shadow: Literal["none", "soft", "strong"] = "soft"  # tinted with the main colour
    font: Literal["Figtree", "Inter", "System"] = "Figtree"
    footer_on: bool = True
    # The clinic's part, before " · Powered By Brilliant Brains" (always shown, with BB's link).
    footer_text: str = Field(default="Not For Medical Advice", max_length=25)
    footer_link: str = Field(  # footer_on and footer_link: BB Admin only
        default="https://brilliantbrains.ai", max_length=300, pattern=r"^(https://\S+)?$"
    )
    # Mobile: a contact row at the bottom of the chat.
    mobile_contact_row: bool = True
    contact_buttons: list[Literal["call", "book", "whatsapp"]] = ["call", "book", "whatsapp"]

    @field_validator("footer_text", mode="before")
    @classmethod
    def _own_part(cls, v: Any) -> str:  # older drafts kept the whole line
        return str(v or "").split("Powered")[0].strip(" ·")[:25]


class Launcher(BaseModel):
    position: Literal["bottom_right", "bottom_left"] = "bottom_right"
    offset_x: int = Field(default=24, ge=0, le=200)
    offset_y: int = Field(default=24, ge=0, le=200)
    shape: Literal["pill", "rounded", "circle"] = "circle"
    size: Literal["small", "medium", "large"] = "large"  # 48, 54, 60 px (the designs: 60)
    background: str = Field(default="#3E74D9", pattern=COLOR)
    icon: Literal["chat", "logo"] = "chat"
    icon_color: str = Field(default="#FFFFFF", pattern=COLOR)
    border: Literal["none", "subtle", "strong"] = "none"
    label_on: bool = True  # desktop: the "Chat with us" pill beside the button
    label_text: str = Field(default="Chat with us", max_length=32)
    label_after_s: int = Field(default=8, ge=0, le=120)  # 0: shown as soon as the page loads
    notification_dot: bool = True  # the highlight-colour dot until the chat is opened
    opens_as: Literal["panel", "full"] = "panel"
    open_on_first_visit: bool = False  # desktop only; mobile never opens by itself
    # Mobile: the button alone (no label), its own position, kept above the website's sticky bar.
    mobile_offset_x: int = Field(default=16, ge=0, le=200)
    mobile_offset_y: int = Field(default=84, ge=0, le=300)
    mobile_label: bool = False


class Appearance(BaseModel):
    look: Look = Look()
    colours: Colours = Colours()
    widget: WidgetStyle = WidgetStyle()
    launcher: Launcher = Launcher()


class Template(BaseModel):
    """How the menu looks: tiles (today's widget), pills (quick-reply buttons under the greeting) or cards
    (two columns with an icon and a label). One main button can be filled to stand out (the designs: Book)."""

    id: Literal["tiles", "pills", "cards"] = "tiles"
    columns: Literal[2, 3] = 3  # tiles and cards per row
    filled_button: str = Field(default="Book Consultation", max_length=40)  # "" for none
    use_colours: bool = True  # choosing a template also sets its colours in Appearance (No: the clinic's own)


# What a button does. "page" opens one of the clinic's existing chat pages (e.g. a doctor's profile), so
# nothing the chat has today is lost; the others are the chat's own actions.
ACTIONS = Literal[
    "submenu",
    "book",
    "online",
    "cancel",
    "reschedule",
    "callback",
    "treatments",
    "treatment",
    "page",
    "answer",
    "link",
    "whatsapp",
    "call",
    "emergency",
]


class Figure(BaseModel):
    value: str = Field(max_length=12)  # e.g. "4.8★"
    label: str = Field(max_length=24)  # e.g. "Google rating"


class SubButton(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    action: ACTIONS = "answer"
    value: str = Field(default="", max_length=500)  # the page, treatment, text, link, number or message
    visible: bool = True


class MainButton(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    icon: str = Field(default="", max_length=20)
    action: ACTIONS = "submenu"
    value: str = Field(default="", max_length=500)
    message: str = Field(default="", max_length=500)  # shown above the sub-buttons
    variant: Literal["", "wa", "sos"] = ""  # WhatsApp (green) or Emergency (red, full width)
    visible: bool = True
    sub: list[SubButton] = Field(default=[], max_length=12)


class Menu(BaseModel):
    """The chat's opening: welcome message, trust figures, then the main buttons and their sub-buttons."""

    welcome: str = Field(default="", max_length=500)
    show_figures: bool = True
    figures: list[Figure] = Field(default=[], max_length=3)
    fallback: str = Field(
        default="I don't have a confirmed answer for that yet. Would you like our team to call you back?",
        max_length=300,
    )  # shown with a call-back button when no answer is found
    buttons: list[MainButton] = Field(default=[], max_length=12)


def menu_from_content(clinic: str) -> dict[str, Any]:
    """Today's chat menu (the clinic's content file) as the first draft of Menu buttons."""
    c = content(clinic) or {}
    nodes = c.get("nodes", {})

    def button(o: dict[str, Any]) -> dict[str, Any]:
        href, action, value = o.get("href", ""), o.get("action", ""), str(o.get("value", ""))
        if href.startswith("tel:"):
            return {"action": "call", "value": href[4:]}
        if "wa.me" in href:
            return {"action": "whatsapp", "value": href}
        if href:
            return {"action": "link", "value": href}
        if action == "start" and value in ("book", "online", "cancel", "reschedule", "callback"):
            return {"action": value, "value": ""}
        if action == "callback":
            return {"action": "callback", "value": value}
        if action == "treat":
            return {"action": "treatment", "value": value}
        return {"action": "page", "value": value}

    out = []
    for item in (c.get("menu") or {}).get("items", []):
        b: dict[str, Any] = {
            "label": item["label"],
            "icon": item.get("icon", ""),
            "variant": item.get("variant", ""),
        }
        node = nodes.get(item.get("value", "")) if item.get("action") == "go" else None
        if item.get("variant") == "sos":
            b |= {"action": "emergency", "value": ""}
        elif node:
            msgs = node.get("messages", [])
            b |= {
                "action": "submenu",
                "message": msgs[0].get("text", "") if msgs else "",
                "sub": [
                    {"label": o["label"], **button(o)} for o in (node.get("ui") or {}).get("options", [])
                ][:12],
            }
        else:
            b |= button(item)
        out.append(b)
    reviews = c.get("reviews") or {}
    figures = [{"value": f"{reviews['rating']}★", "label": "Google rating"}] if reviews.get("rating") else []
    return {
        "welcome": c.get("greeting") or (c.get("config") or {}).get("greeting", ""),
        "figures": figures,
        "buttons": out,
    }


PHONE = r"^(\+[1-9]\d{7,14})?$"
TIME = r"^([01]\d|2[0-3]):[0-5]\d$"
DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


class Day(BaseModel):
    day: Literal["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    open: bool = True
    start: str = Field(default="10:00", pattern=TIME)
    end: str = Field(default="19:00", pattern=TIME)


class Contact(BaseModel):
    """Clinic info → Contact & hours. Every chat button that calls, opens WhatsApp or a map uses these."""

    phone: str = Field(default="", max_length=16, pattern=PHONE)  # reception, e.g. +919731207940
    emergency_number: str = Field(default="108", max_length=16, pattern=r"^\+?\d{3,15}$")
    whatsapp: str = Field(default="", max_length=16, pattern=PHONE)
    whatsapp_message: str = Field(default="", max_length=300)  # typed for the patient; they can change it
    email: str = Field(default="", max_length=120, pattern=r"^([^\s@]+@[^\s@]+\.[^\s@]{2,})?$")
    address: str = Field(default="", max_length=300)
    landmark: str = Field(default="", max_length=120)
    parking: str = Field(default="", max_length=200)
    maps_link: str = Field(default="", max_length=300, pattern=r"^(https://\S+)?$")
    hours: list[Day] = Field(default=[Day(day=d) for d in DAYS], min_length=7, max_length=7)
    closed_message: str = Field(
        default="The clinic is closed right now. Leave your number and we will call you back.", max_length=300
    )


def contact_from_clinic(row: Any, clinic: str) -> dict[str, Any]:
    """Today's details (the clinic's row and its chat page) as the first draft of Contact & hours."""
    c = content(clinic) or {}
    page = (c.get("nodes") or {}).get("clinic") or {}
    text = ((page.get("messages") or [{}])[0].get("text") or "").split("\n")
    links = {o.get("label", ""): o.get("href", "") for o in (page.get("ui") or {}).get("options", [])}
    wa = next(
        (i.get("href", "") for i in (c.get("menu") or {}).get("items", []) if i.get("variant") == "wa"), ""
    )
    wa_text = unquote(wa.split("text=", 1)[1]) if "text=" in wa else ""
    closed = set(row["closed_weekdays"] or [])
    start, end = row["open_time"].strftime("%H:%M"), row["close_time"].strftime("%H:%M")
    return {
        "phone": row["phone"] or "",
        "whatsapp": row["whatsapp"] or "",
        "whatsapp_message": wa_text,
        "address": text[1].strip() if len(text) > 1 else "",
        "maps_link": next((h for label, h in links.items() if "Maps" in label), ""),
        "hours": [
            {"day": d, "open": i not in closed, "start": start, "end": end} for i, d in enumerate(DAYS)
        ],
    }


class Service(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    category: str = Field(default="", max_length=40)
    description: str = Field(default="", max_length=400)
    page: str = Field(default="", max_length=300, pattern=r"^(https://\S+)?$")  # "Read more" on the website
    photo: str = Field(default="", max_length=300, pattern=r"^(https://\S+)?$")
    duration: str = Field(default="", max_length=30)  # e.g. "6 to 8 hours"
    price: int | None = Field(default=None, ge=0, le=10_000_000)  # starting price in rupees
    show_price: bool = False  # off: "the price is shared at consultation"
    book_as: str = Field(default="", max_length=80)  # the booking-list option its Book button chooses
    show: bool = True


class Services(BaseModel):
    """Clinic info → Services: every treatment the chat can show, the booking list, what is not offered."""

    items: list[Service] = Field(default=[], max_length=80)
    booking_options: list[str] = Field(default=[], max_length=20)  # "Which treatment?" when booking
    not_offered: list[str] = Field(default=[], max_length=80)  # words the chat answers "not offered" to


GROUP = {"ht": "Hair transplant", "hf": "Hair fall & scalp", "treat": "Other treatments"}


def services_from_content(clinic: str) -> dict[str, Any]:
    """Today's treatments, booking list and "not offered" words as the first draft of Services."""
    c = content(clinic) or {}
    site = str(c.get("site") or "").rstrip("/") + "/"
    options = list((c.get("config") or {}).get("treatments", []))
    mapping = c.get("booking_option") or {}
    items = [
        {
            "name": name,
            "category": GROUP.get(t.get("list", ""), "Other treatments"),
            "description": t.get("text", ""),
            "page": site + t["path"] if t.get("path") and site.startswith("https://") else "",
            "book_as": mapping.get(name) or (name if name in options else ""),
        }
        for name, t in (c.get("treatments") or {}).items()
    ]
    return {
        "items": items,
        "booking_options": options,
        "not_offered": [w.rstrip("?") for w in c.get("not_offered", [])],
    }


class Quote(BaseModel):
    name: str = Field(min_length=2, max_length=40)  # first name and last initial only, e.g. "Venkat A."
    topic: str = Field(default="", max_length=30)  # e.g. transplant, gfc, international
    text: str = Field(min_length=10, max_length=1500)  # word for word from the review
    show: bool = True


class Reviews(BaseModel):
    """Clinic info → Reviews: Google rating, selected patient quotes, the links, well-known patients."""

    rating: str = Field(default="", max_length=3, pattern=r"^([1-5](\.\d)?)?$")  # e.g. 4.8
    count: str = Field(default="", max_length=12)  # e.g. 1,040
    link: str = Field(
        default="", max_length=600, pattern=r"^(https://\S+)?$"
    )  # the Reviews tab on Google Maps
    videos: str = Field(default="", max_length=300, pattern=r"^(https://\S+)?$")  # patient videos page
    quotes: list[Quote] = Field(default=[], max_length=30)
    celebrities: str = Field(default="", max_length=600)  # "well-known patients" answer


def reviews_from_content(clinic: str) -> dict[str, Any]:
    """Today's Google rating, quotes and links, and the well-known patients fact, as the first draft."""
    r = (content(clinic) or {}).get("reviews") or {}
    facts = (kb_file(clinic) or {}).get("facts", [])
    celeb = next((f.get("value", "") for f in facts if f.get("key") == "celebrity_clients"), "")
    return {
        "rating": str(r.get("rating", "")),
        "count": str(r.get("count", "")),
        "link": r.get("link", ""),
        "videos": r.get("videos", ""),
        "quotes": [
            {"name": q["name"], "topic": q.get("topic", ""), "text": q["text"]} for q in r.get("items", [])
        ],
        "celebrities": celeb,
    }


def kb_file(clinic: str) -> dict[str, Any] | None:
    """The clinic's knowledge-base file (app/clinics/<id>.kb.json), if it has one."""
    path = Path(__file__).resolve().parents[2] / "clinics" / f"{clinic}.kb.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# The sections of the settings; each later screen (Menu buttons, ...) adds its own.
class Chat(BaseModel):
    """Which engine answers patients. canvas: the published workflow canvas (Menu buttons); off: the chatbot
    as before (the clinic's file and the simple Menu buttons). Live after Publish, like everything else."""

    canvas: bool = False


SECTIONS: dict[str, type[BaseModel]] = {
    "appearance": Appearance,
    "template": Template,
    "menu": Menu,
    "contact": Contact,
    "services": Services,
    "reviews": Reviews,
    "flow": Flow,  # the workflow canvas; checked by app.crm.flow.normalise on save
    "chat": Chat,
}


class MenuItem(BaseModel):
    label: str
    icon: str | None = None
    variant: str | None = None  # wa (WhatsApp) or sos (Emergency)


class Settings(BaseModel):
    clinic: str
    draft: dict[str, Any]  # every section, filled with defaults where nothing is saved yet
    published: dict[str, Any]
    version: int  # 0: never published
    changed: bool  # the draft differs from what is published
    published_at: str | None
    updated_at: str | None
    flow_problems: list[Problem] = []  # loose ends (block a publish) and unreachable blocks (warnings)
    menu: list[MenuItem]  # the clinic's chat menu today, for the previews (Menu buttons edits it later)
    follows: list[str] = []  # parts shown from the main template (Neo Follicle): flow, template, appearance
    main_behind: bool = False  # the main only: its live canvas/Templates/Appearance are not yet for all


def _filled(saved: dict[str, Any]) -> dict[str, Any]:
    """Each section checked and completed with defaults (old drafts keep working when fields are added)."""
    return {
        name: model.model_validate(saved.get(name) or {}).model_dump() for name, model in SECTIONS.items()
    }


async def _manager(user: Staff, clinic: str) -> None:
    if not (user.bb_admin or user.roles.get(clinic) == "clinic_manager" or perm.granted(user, clinic)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The Dashboard is for clinic managers and BB Admin.")


async def _load(clinic: str) -> Settings:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if not await conn.fetchval("select 1 from app.clinics where id = $1 and active", clinic):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown clinic.")
        r = await conn.fetchrow("select * from app.clinic_settings where clinic_id = $1", clinic)
        info = await conn.fetchrow(
            """select bot_name, phone, whatsapp, open_time, close_time, closed_weekdays from app.clinics
               where id = $1""",
            clinic,
        )
        bot = info["bot_name"]
        draft_saved = _json(r["draft"]) if r else {}
        published_saved = _json(r["published"]) if r else {}
        both = [draft_saved, published_saved] if published_saved else [draft_saved]
        follows = await main_template.apply(conn, clinic, *both)  # followed parts: the main's, in our names
    if not draft_saved.get("contact"):  # start from the clinic's details today
        draft_saved["contact"] = contact_from_clinic(info, clinic)
    if not draft_saved.get("services"):  # start from the chat's treatments today
        draft_saved["services"] = services_from_content(clinic)
    if not draft_saved.get("reviews"):  # start from the Google reviews shown today
        draft_saved["reviews"] = reviews_from_content(clinic)
    if not draft_saved.get("flow"):  # start from the chat today: menu, pages, booking questions
        draft_saved["flow"] = import_content(content(clinic) or {})
    if not draft_saved.get("menu"):  # start from the chat's menu today
        draft_saved["menu"] = menu_from_content(clinic)
    if not draft_saved.get("appearance"):  # start from the clinic's bot name
        draft_saved["appearance"] = {"look": {"name": bot, "avatar_letter": bot[:1].upper()}}
    draft, published = _filled(draft_saved), _filled(published_saved) if published_saved else {}
    return Settings(
        clinic=clinic, draft=draft, published=_slim(published), version=r["version"] if r else 0,
        changed=_to_publish(draft, published) != published,
        published_at=r["published_at"].isoformat() if r and r["published_at"] else None,
        updated_at=r["updated_at"].isoformat() if r else None,
        flow_problems=check_flow(draft["flow"]),
        menu=[MenuItem.model_validate(i) for i in _menu_items(clinic, draft)], follows=follows,
        main_behind=clinic == main_template.MAIN and any(
            published_saved.get(k) != _json(r["shared"]).get(k) for k in main_template.PARTS
        ),
    )  # fmt: skip


def _menu_items(clinic: str, draft: dict[str, Any]) -> list[dict[str, Any]]:
    """The clinic's own main buttons, for the Templates previews: its canvas's opening buttons when it runs on
    the canvas, else its Menu buttons, else (older clinics) its content file's menu."""

    def item(b: dict[str, Any]) -> dict[str, Any]:
        return {"label": b["label"], "icon": b.get("icon") or None, "variant": b.get("variant") or None}

    if (draft.get("chat") or {}).get("canvas"):
        opening = next((n for n in draft["flow"].get("nodes", []) if n["type"] == "opening"), None)
        buttons = ((opening or {}).get("settings") or {}).get("buttons") or []
        if buttons:
            return [item(b) for b in buttons if b.get("visible", True)]
    own = [b for b in (draft.get("menu") or {}).get("buttons", []) if b.get("visible", True)]
    if own:
        return [item(b) for b in own]
    items: list[dict[str, Any]] = ((content(clinic) or {}).get("menu") or {}).get("items", [])
    return items


def _json(v: Any) -> dict[str, Any]:
    return dict(json.loads(v) if isinstance(v, str) else v or {})


@router.get("/{clinic}/settings", response_model=Settings)
async def get_settings_(user: Annotated[Staff, Depends(staff)], clinic: str) -> Settings:
    await _manager(user, clinic)
    return await _load(clinic)


@router.put("/{clinic}/settings/{section}", response_model=Settings)
async def save_draft(
    user: Annotated[Staff, Depends(staff)], clinic: str, section: str, body: dict[str, Any]
) -> Settings:
    """Saves one section of the draft (checked against its rules). Patients see nothing until it is
    published."""
    await _manager(user, clinic)
    model = SECTIONS.get(section)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown settings section.")
    try:
        value = normalise(body) if section == "flow" else model.model_validate(body).model_dump()
    except FlowError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    except ValidationError as e:  # the first wrong field, in words staff can act on
        err = e.errors()[0]
        field = " → ".join(str(x) for x in err["loc"])
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{field}: {err['msg']}") from None
    if section == "appearance" and not user.bb_admin:  # the "Powered by" footer and its link: BB only
        widget = (await _load(clinic)).draft["appearance"]["widget"]
        value["widget"] |= {k: widget[k] for k in ("footer_on", "footer_link")}
    if section == "flow":
        value["phrases"] = _phrase_status(value["phrases"], (await _load(clinic)).draft["flow"])
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)  # audit: who
        await main_template.make_own(conn, clinic, [section])  # a changed part is the clinic's own
        await conn.execute(
            """insert into app.clinic_settings (clinic_id, draft, updated_by)
               values ($1, jsonb_build_object($2::text, $3::jsonb), $4::uuid)
               on conflict (clinic_id) do update
                 set draft = app.clinic_settings.draft || jsonb_build_object($2::text, $3::jsonb),
                     updated_by = $4::uuid""",
            clinic, section, json.dumps(value), user.id,
        )  # fmt: skip
    return await _load(clinic)


def _phrase_status(new: list[dict[str, Any]], old_flow: dict[str, Any]) -> list[dict[str, Any]]:
    """Saving never approves a phrase: an unchanged phrase keeps its status; a new or edited one is pending
    until a manager approves it (POST /flow/phrases/approve)."""
    old = {p["id"]: p for p in old_flow.get("phrases") or []}
    out = []
    for p in new:
        was = old.get(p["id"])
        if was and was["text"] == p["text"] and was["target"] == p["target"]:
            out.append(p | {"status": was["status"], "approved_by": was.get("approved_by")})
        else:
            out.append(p | {"status": "pending", "approved_by": None})
    return out


class Approve(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=200)


@router.post("/{clinic}/flow/phrases/approve", response_model=Settings)
async def approve_phrases(user: Annotated[Staff, Depends(staff)], clinic: str, body: Approve) -> Settings:
    """A clinic manager approves typed phrases: only then does the chat use them (no self-training)."""
    await _manager(user, clinic)
    flow = (await _load(clinic)).draft["flow"]
    for p in flow["phrases"]:
        if p["id"] in body.ids:
            p.update(status="approved", approved_by=user.id)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        await main_template.make_own(conn, clinic, ["flow"])
        await conn.execute(
            """insert into app.clinic_settings (clinic_id, draft, updated_by)
               values ($1, jsonb_build_object('flow', $2::jsonb), $3::uuid)
               on conflict (clinic_id) do update
                 set draft = app.clinic_settings.draft || jsonb_build_object('flow', $2::jsonb),
                     updated_by = $3::uuid""",
            clinic, json.dumps(flow), user.id,
        )  # fmt: skip
    return await _load(clinic)


def _add_live_phrases(flow: dict[str, Any], rows: list[tuple[str, str]]) -> int:
    """Adds the live chat's approved (topic, phrase) rows to the flow's phrases; returns how many were new."""
    ids = {n["id"] for n in flow["nodes"]}
    have = {" ".join(re.sub(r"[^a-z0-9]+", " ", p["text"].lower()).split()) for p in flow["phrases"]}
    added = 0
    for topic, example in rows:
        if topic in SMALL_TALK_TARGETS_BY_TOPIC:
            target = SMALL_TALK_TARGETS_BY_TOPIC[topic]
        elif topic.startswith("t_"):
            target = "@treatment:" + topic
        elif topic in ids:
            target = topic
        elif "page-" + topic in ids:
            target = "page-" + topic
        else:
            continue  # no block for this topic in the flow
        key = " ".join(re.sub(r"[^a-z0-9]+", " ", example.lower()).split())
        if not key or key in have:
            continue
        have.add(key)
        added += 1
        flow["phrases"].append(
            {
                "id": f"pl{added}",
                "target": target,
                "text": example[:100],
                "status": "approved",
                "approved_by": "live chat",
            }  # fmt: skip
        )
    return added


@router.post("/{clinic}/flow/phrases/import-live", response_model=Settings)
async def import_live_phrases(user: Annotated[Staff, Depends(staff)], clinic: str) -> Settings:
    """The live chat's APPROVED phrases (app.intent_examples) into the draft flow, each to the block of its
    topic ("cost" -> the cost page, "t_prp_treatment" -> the PRP card, "greeting" -> small talk). They were
    approved by staff for the live chat, so they come in approved (marked "live chat"); a phrase already in
    the flow is skipped, never changed."""
    await _manager(user, clinic)
    flow = (await _load(clinic)).draft["flow"]
    pool = await get_pool()
    rows = await pool.fetch(
        """select intent, example from app.intent_examples where clinic_id = $1 and status = 'approved'
           order by intent, example""",
        clinic,
    )
    added = _add_live_phrases(flow, [(r["intent"], r["example"]) for r in rows])
    if added:
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
            await main_template.make_own(conn, clinic, ["flow"])
            await conn.execute(
                """update app.clinic_settings set updated_by = $3::uuid,
                     draft = draft || jsonb_build_object('flow', $2::jsonb) where clinic_id = $1""",
                clinic, json.dumps(flow), user.id,
            )  # fmt: skip
    return await _load(clinic)


SMALL_TALK_TARGETS_BY_TOPIC = {
    "identity": "@identity",
    "greeting": "@greeting",
    "thanks": "@thanks",
    "bye": "@bye",
}


# Sections Publish leaves as published (none now: the workflow canvas is published with the rest).
ON_HOLD: set[str] = set()


def _to_publish(draft: dict[str, Any], published: dict[str, Any]) -> dict[str, Any]:
    """What Publish makes live: the draft, except the sections on hold (kept as published)."""
    return draft | {k: published[k] for k in ON_HOLD if k in published}


def _slim(published: dict[str, Any]) -> dict[str, Any]:
    """The published copy for the Dashboard, without an uploaded logo's data (it is in the draft)."""
    look = (published.get("appearance") or {}).get("look") or {}
    if not str(look.get("logo", "")).startswith("data:"):
        return published
    appearance = published["appearance"] | {"look": look | {"logo": "(uploaded image)"}}
    return published | {"appearance": appearance}


@router.post("/{clinic}/publish", response_model=Settings)
async def publish(user: Annotated[Staff, Depends(staff)], clinic: str, for_all: bool = False) -> Settings:
    """The draft becomes what the widget shows, as a new numbered version (kept for roll back). For the main
    template (Neo Follicle), ``for_all`` also makes its canvas, Templates and Appearance what every following
    clinic shows (BB Admin only); without it, only the main changes."""
    canvas.forget()  # the live chat reads the new version at once (followers too)
    await _manager(user, clinic)
    if for_all and clinic != main_template.MAIN:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only the main template is published for all.")
    if for_all and not user.bb_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Publishing for all clinics is for BB Admin.")
    current = await _load(clinic)
    if not current.changed and for_all and current.main_behind:  # already live here: now for all too
        async with (await get_pool()).acquire() as conn, conn.transaction():
            await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
            await main_template.share(conn, current.published)
        return await _load(clinic)
    if not current.changed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing new to publish.")
    live = _to_publish(current.draft, current.published)
    flow = live["flow"] != current.published.get("flow")  # the workflow itself changes
    errors = [p for p in current.flow_problems if p.level == "error"] if flow else []
    if errors:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Fix the workflow first ({len(errors)} to fix): {errors[0].message}",
        )
    checks = run_checks(current.draft["flow"], _check_context(current.draft)) if flow else []
    failed = [c for c in checks if not c["ok"]]
    if failed:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A publish check failed ({len(failed)}): '{failed[0]['name']}' {failed[0]['message']}.",
        )
    # The test sets (slow: hundreds of messages) no longer block Publish; staff run them on the canvas
    # ("Run test sets"), which shows any set below its bar.
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        # After the highest version on record, so numbers never repeat (versions are never deleted).
        version = await conn.fetchval(
            "select coalesce(max(version), 0) + 1 from app.clinic_setting_versions where clinic_id = $1",
            clinic,
        )
        await conn.execute(
            """insert into app.clinic_settings (clinic_id, draft, published, version, published_by,
                 published_at, updated_by)
               values ($1, $2::jsonb, $5::jsonb, $4, $3::uuid, now(), $3::uuid)
               on conflict (clinic_id) do update set draft = $2::jsonb, published = $5::jsonb,
                 version = $4, published_by = $3::uuid, published_at = now()""",
            clinic, json.dumps(current.draft), user.id, version, json.dumps(live),
        )  # fmt: skip
        await conn.execute(
            """insert into app.clinic_setting_versions (clinic_id, version, settings, published_by)
               values ($1, $2, $3::jsonb, $4::uuid)""",
            clinic, version, json.dumps(live), user.id,
        )  # fmt: skip
        if for_all:
            await main_template.share(conn, live)
    return await _load(clinic)


class Follow(BaseModel):
    part: Literal["flow", "template", "appearance"]
    follow: bool


@router.put("/{clinic}/main-template", response_model=Settings)
async def set_follow(user: Annotated[Staff, Depends(staff)], clinic: str, body: Follow) -> Settings:
    """Follow the main template (Neo Follicle) again for this part, or make it the clinic's own (starting
    from the main's version). The main itself follows nothing."""
    canvas.forget()  # the live chat reads the new version at once (followers too)
    await _manager(user, clinic)
    if clinic == main_template.MAIN:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This clinic is the main template.")
    await _load(clinic)  # a known, active clinic
    async with (await get_pool()).acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        await conn.execute(
            """insert into app.clinic_settings (clinic_id, updated_by) values ($1, $2::uuid)
               on conflict do nothing""",
            clinic, user.id,
        )  # fmt: skip
        if body.follow:
            await main_template.follow(conn, clinic, [body.part])
        else:
            await main_template.make_own(conn, clinic, [body.part])
    return await _load(clinic)


class TestChat(BaseModel):
    """One message in the test chat: none to start (state empty), a tapped button id, or typed text."""

    state: dict[str, Any] | None = None  # as returned by the last reply
    tap: str | None = Field(default=None, max_length=200)
    text: str | None = Field(default=None, max_length=500)
    device: Literal["desktop", "mobile"] = "desktop"


WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def techniques(items: list[dict[str, Any]]) -> dict[str, list[str]]:
    """A booking choice -> the shown services set to "book as" it, when there are 2 or more."""
    out: dict[str, list[str]] = {}
    for i in items:
        if i.get("show") and i.get("book_as") and i.get("name"):
            out.setdefault(i["book_as"], []).append(i["name"])
    return {k: v for k, v in out.items() if len(v) > 1}


def _context(draft: dict[str, Any], device: str) -> Context:
    """The test chat reads the draft: Services, Contact & hours, Reviews (nothing published is used)."""
    today, minutes = ist_now()
    contact, reviews = draft["contact"], draft["reviews"]
    day = next((d for d in contact["hours"] if d["day"] == WEEKDAYS[today.weekday()]), None)
    hm = f"{minutes // 60:02d}:{minutes % 60:02d}"
    open_now = bool(day and day["open"] and day["start"] <= hm < day["end"])
    where = [contact["address"], contact["landmark"], contact["maps_link"]]
    return Context(
        today=today, minutes=minutes, device=device,
        services=draft["services"]["items"],
        booking_options=draft["services"]["booking_options"],
        techniques=techniques(draft["services"]["items"]),
        open_now={"in_clinic": open_now, "online": open_now},
        location="\n".join(x for x in where if x),
        phone=contact["phone"],
        reviews=[f"“{q['text']}” — {q['name']}" for q in reviews["quotes"] if q["show"]],
    )  # fmt: skip


TEST_CLINIC, TEST_MARK = "CL99", "crm:test-chat"  # test leads: the hidden test clinic only, marked


async def _save_test_lead(
    user: Staff, lead: dict[str, Any], device: str, stage: str = "follow_up"
) -> dict[str, str]:
    """A finished test booking / call back ... as a lead and an Inbox request in CL99, marked as a test.
    No email, no task, no staff assigned (unlike a patient's lead); Delete test leads removes them."""
    phone = (lead.get("phone") or "").replace(" ", "") or None
    if not phone and not lead.get("email"):
        return {"error": "Not saved: a test lead needs a phone number or an email."}
    data = {k: v for k, v in lead.items() if k not in ("type", "block")}
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        lead_id = await conn.fetchval(
            """select id from app.leads where clinic_id = $1 and deleted_at is null
                 and (phone_e164 = $2 or ($2 is null and email = $3))""",
            TEST_CLINIC, phone, lead.get("email"),
        )  # fmt: skip
        if lead_id is None:
            lead_id = await conn.fetchval(
                """insert into app.leads (clinic_id, full_name, phone_e164, phone_cc, email, source,
                     treatment, page_url, device, campaign)
                   values ($1, $2, $3, $4, $5, 'chatbot', $6, $7, $8, $9) returning id""",
                TEST_CLINIC, lead.get("name") or "Test patient", phone, "+91" if phone else None,
                lead.get("email"), lead.get("treatment"), TEST_MARK, device, lead.get("campaign"),
            )  # fmt: skip
        else:
            await conn.execute(
                """update app.leads set contact_count = contact_count + 1, last_contact_at = now()
                   where id = $1""",
                lead_id,
            )
        await conn.execute(
            "insert into app.requests (clinic_id, lead_id, type, data) values ($1, $2, $3, $4::jsonb)",
            TEST_CLINIC, lead_id, lead["type"], json.dumps(data),
        )  # fmt: skip
        if lead["type"] in ("book", "online") and stage == "follow_up":  # the flow's stage rule
            await conn.execute(
                "update app.leads set stage = 'follow_up', updated_at = now() "
                "where id = $1 and stage = 'new'",
                lead_id,
            )
        code: str = await conn.fetchval("select lead_code from app.leads where id = $1", lead_id)
    return {"code": code, "clinic": TEST_CLINIC}


async def _test_alert(user: Staff, alert: dict[str, Any], device: str) -> str:
    """A test chat's emergency alert. With the patient's phone: an urgent call back in CL99's Inbox (the
    bell). No email is queued for a test (live, the clinic manager is emailed)."""
    if not alert.get("phone"):
        return "Staff alert (test): live, the clinic manager is emailed. No phone yet, so no Inbox call back."
    said = alert.get("said") or "emergency words"
    lead = {"type": "callback", "name": "Test patient", "phone": alert["phone"], "urgent": "yes",
            "reason": f"EMERGENCY in chat: {said}"}  # fmt: skip
    saved = await _save_test_lead(user, lead, device)
    code = saved.get("code", "")
    return f"Staff alert (test): urgent call back {code} in CL99's Inbox; live, the manager is emailed."


def _check_context(draft: dict[str, Any]) -> Context:
    """Checks run as if the clinic is open at 11 AM, so a check passes or fails the same at any hour."""
    ctx = _context(draft, "desktop")
    ctx.minutes, ctx.open_now = 11 * 60, {"in_clinic": True, "online": True}
    return ctx


@router.post("/{clinic}/flow/checks")
async def flow_checks(user: Annotated[Staff, Depends(staff)], clinic: str) -> list[dict[str, Any]]:
    """Replays the draft's publish checks (saved test chats): pass or fail for each."""
    await _manager(user, clinic)
    draft = (await _load(clinic)).draft
    return run_checks(draft["flow"], _check_context(draft))


@router.post("/{clinic}/flow/test")
async def test_chat(user: Annotated[Staff, Depends(staff)], clinic: str, body: TestChat) -> dict[str, Any]:
    """Runs the DRAFT flow, one message at a time, for the test chat on the canvas (patients see nothing).
    A finished booking / call back ... is saved as a test lead in CL99 (never in the clinic itself)."""
    await _manager(user, clinic)
    draft = (await _load(clinic)).draft
    ctx = _context(draft, body.device)
    if body.state is None:
        return start(draft["flow"], ctx)
    # The engine is synchronous: what it may ask for this message is looked up first, live.
    waiting = (body.state.get("ask") or {}).get("kind")
    if body.text and waiting in (None, "knowledge", "lead", "question"):  # typed questions, mid-booking too
        found = await _kb_answer(clinic, body.text)
        ctx.kb = lambda q: found
    if waiting == "check" and body.text:
        booked = await _upcoming(clinic, body.text)
        ctx.appointments = lambda phone: booked
    if body.text and not waiting:
        near = await _nearest_phrase(draft["flow"], body.text)
        ctx.meaning = lambda t: near
    at = next((n for n in draft["flow"]["nodes"] if n["id"] == body.state.get("at")), None)
    # Known patient / returning: a lead with the phone given so far (or typed now) exists in this clinic.
    phone = (body.state.get("fields") or {}).get("phone") or normal_phone((body.text or "").strip(), None)
    if phone:
        ctx.returning = bool(
            await (await get_pool()).fetchval(
                "select 1 from app.leads where clinic_id = $1 and phone_e164 = $2 and deleted_at is null",
                clinic, phone.replace(" ", ""),
            )
        )  # fmt: skip
    if at and at["type"] in ("book", "online", "reschedule", "follow_up"):
        ctx.slots = await _free(clinic, at["settings"].get("doctor") or "")
    reply = send(draft["flow"], ctx, body.state, tap=body.tap, text=body.text)
    stage = draft["flow"].get("globals", {}).get("request_stage", "follow_up")
    if reply["lead"]:
        reply["saved"] = await _save_test_lead(user, reply["lead"], body.device, stage)
    if reply["alert"]:
        reply["alert_note"] = await _test_alert(user, reply["alert"], body.device)
    return reply


async def _free(clinic: str, doctor: str) -> dict[str, dict[str, list[str]]]:
    """Free slots for the booking window, in-clinic and online (one diary), as the live chat reads them;
    only the named doctor's when the block always uses one doctor."""
    today, now = ist_now()
    last = today + timedelta(days=(content(clinic) or {}).get("config", {}).get("bookingWindowDays", 14))
    pool = await get_pool()
    async with pool.acquire() as conn:
        doctor_id = None
        if doctor:
            doctor_id = await conn.fetchval(
                "select id::text from app.doctors where clinic_id = $1 and name = $2 and active",
                clinic,
                doctor,
            )
        return {
            mode: await slots.free_slots_range(conn, clinic, today, last, mode, today, now, "", doctor_id)
            for mode in ("in_clinic", "online")
        }


_phrase_vectors: dict[str, list[float]] = {}  # by phrase text (the model's numbers never change)


async def _nearest_phrase(flow: dict[str, Any], text: str) -> dict[str, Any] | None:
    """The approved phrase closest in meaning to the typed text, if close enough (the Knowledge base's
    threshold); None while the model is loading. Used only when no words matched."""
    approved = [p for p in flow.get("phrases") or [] if p["status"] == "approved"]
    if not approved or not embed.ready():
        return None
    missing = [p["text"] for p in approved if p["text"] not in _phrase_vectors]
    if missing:
        for t, v in zip(missing, await embed.vectors(missing), strict=True):
            _phrase_vectors[t] = [float(x) for x in v]
    q = await embed.vector(text)
    scores = [sum(a * b for a, b in zip(q, _phrase_vectors[p["text"]], strict=True)) for p in approved]
    score, best = max(zip(scores, approved, strict=True), key=lambda x: x[0])
    if score < kb.SEMANTIC_MIN:
        return None
    return {"target": best["target"], "text": best["text"], "score": round(score * 100, 1)}


async def _kb_answer(clinic: str, text: str) -> str | None:
    """The clinic's approved Knowledge base, as the live chat searches it (no LLM): approved Q/A, then facts;
    by words, then by meaning. Medical questions never get here (the engine's guard)."""
    hit = await kb_hit(clinic, text)
    return hit[0] if hit else None


async def kb_hit(clinic: str, text: str) -> tuple[str, str] | None:
    """As _kb_answer, with what answered: "qa" (a question staff wrote) or "fact" (a single fact), by its
    words; "qa_meaning" / "fact_meaning" when only by meaning."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        for find in (kb.search, kb.fact):
            hit = await find(conn, clinic, text)
            if hit:
                return hit.answer, hit.source
        for near in (kb.semantic, kb.fact_semantic):
            hit, _ = await near(conn, clinic, text)
            if hit:
                return hit.answer, f"{hit.source}_meaning"  # by meaning: looser than by words
    return None


async def _upcoming(clinic: str, typed: str) -> list[str]:
    """The upcoming appointments of the lead with this phone (CRM → Appointments), as short lines."""
    phone = normal_phone(typed.strip(), None)
    if not phone:
        return []
    pool = await get_pool()
    rows = await pool.fetch(
        """select a.type, a.status, d.name doctor,
                  to_char(lower(a.slot) at time zone c.timezone, 'Dy DD Mon, HH12:MI AM') at_,
                  to_char(a.preferred_date, 'Dy DD Mon') on_day
           from app.appointments a join app.leads l on l.id = a.lead_id
             join app.clinics c on c.id = a.clinic_id left join app.doctors d on d.id = a.doctor_id
           where a.clinic_id = $1 and l.phone_e164 = $2 and l.deleted_at is null
             and a.status in ('pending', 'confirmed')
             and coalesce((lower(a.slot) at time zone c.timezone)::date, a.preferred_date)
                 >= (now() at time zone c.timezone)::date
           order by coalesce(lower(a.slot), a.preferred_date::timestamptz) limit 3""",
        clinic, phone.replace(" ", ""),
    )  # fmt: skip
    return [
        f"{r['at_'] or r['on_day'] + ' (time to be confirmed)'}"
        f"{' with ' + r['doctor'] if r['doctor'] else ''}"
        f" · {'online' if r['type'] == 'online' else 'in clinic'} · {r['status']}"
        for r in rows
    ]


def _always(value: Any) -> Any:
    """A lookup that returns what was already looked up for this message."""
    return lambda _: value


def _test_sets(clinic: str) -> dict[str, list[tuple[str, str, str]]]:
    """The clinic's typed-message test sets (only CL01 has them so far)."""
    if clinic != "CL01":
        return {}
    from scripts.eval_chat import CASES as SMALL
    from scripts.eval_set_buttons_cl01 import CASES as BUTTONS
    from scripts.eval_set_cl01 import CASES as BIG

    return {"Buttons typed": BUTTONS, "Typed messages": BIG, "Small set": SMALL}


@router.post("/{clinic}/flow/test-sets")
async def run_test_sets(user: Annotated[Staff, Depends(staff)], clinic: str) -> list[dict[str, Any]]:
    """Every message of the clinic's test sets, sent to the DRAFT flow (one new chat each, nothing saved):
    the score per set, its bar, and the messages that failed."""
    await _manager(user, clinic)
    return await _score_sets(clinic, (await _load(clinic)).draft)


# Publish needs at least these scores (the canvas flow's scores on 28 Oct 2026, with the live chat's approved
# phrases). Raise them as the flow gets better; never lower them.
TEST_SET_BARS = {"CL01": {"Buttons typed": 70, "Typed messages": 317, "Small set": 80}}


async def _score_sets(clinic: str, draft: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for name, cases in _test_sets(clinic).items():
        failures = []
        for message, expected, word in cases:
            ctx = _context(draft, "desktop")
            found, near = await _kb_answer(clinic, message), await _nearest_phrase(draft["flow"], message)
            ctx.kb, ctx.meaning = _always(found), _always(near)
            first = start(draft["flow"], ctx)
            reply = send(draft["flow"], ctx, first["state"], text=message)
            ok, got = passed(draft["flow"], reply, expected, word)
            if not ok:
                said = " / ".join(m["text"] for m in reply["messages"] if m["text"])[:160]
                failures.append(
                    {"message": message, "expected": expected, "got": got, "word": word, "reply": said}
                )
        bar = TEST_SET_BARS.get(clinic, {}).get(name, 0)
        score = len(cases) - len(failures)
        out.append({"name": name, "total": len(cases), "passed": score, "bar": bar, "failures": failures})
    return out


@router.delete("/{clinic}/flow/test-leads")
async def delete_test_leads(user: Annotated[Staff, Depends(staff)], clinic: str) -> dict[str, int]:
    """Deletes the test chat's leads (CL99, marked as tests) with their requests and timeline."""
    await _manager(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        gone = await conn.fetch(
            "delete from app.leads where clinic_id = $1 and page_url = $2 returning id",
            TEST_CLINIC,
            TEST_MARK,
        )
    return {"deleted": len(gone)}


@router.post("/{clinic}/flow/rebuild", response_model=Settings)
async def rebuild_flow(user: Annotated[Staff, Depends(staff)], clinic: str) -> Settings:
    """Replaces the draft workflow with one built from today's chat again (the published one is untouched)."""
    await _manager(user, clinic)
    flow = import_content(content(clinic) or {})
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        await main_template.make_own(conn, clinic, ["flow"])
        await conn.execute(
            """insert into app.clinic_settings (clinic_id, draft, updated_by)
               values ($1, jsonb_build_object('flow', $2::jsonb), $3::uuid)
               on conflict (clinic_id) do update
                 set draft = app.clinic_settings.draft || jsonb_build_object('flow', $2::jsonb),
                     updated_by = $3::uuid""",
            clinic, json.dumps(flow), user.id,
        )  # fmt: skip
    return await _load(clinic)
