"""Adds the Neo Group's other clinics (scripts/group_clinics_data.py): Derma Solutions (DS), Neo Fertility
(NF) and NeoSculpt6 (NS6), and removes the earlier BB Fertility (BF).

    uv run python -m scripts.group_clinics            # check everything and show what would be made
    uv run python -m scripts.group_clinics --apply    # make it

Each clinic is built from Neo Follicle Hair Transplant's (the main template's) published chat: the same flow,
Templates and Appearance (the last two followed, so they stay in step), with its own name, bot (Mira),
contact, hours, doctors, treatment groups, prices, results, reviews and booking options. Also: its doctors
and their weekly hours, its website (approved for the chatbot), its knowledge facts, the general
typed-question phrases, and a placeholder team (1 Admin, 2 Front Desk) made through Supabase Auth without
any email; their temporary passwords go to SEED-ACCOUNTS.local.md (kept out of git). A clinic that already
exists is left as it is.
"""

import asyncio
import copy
import json
import re
import secrets
import sys
from datetime import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import asyncpg

from app.api.v1.crm_clinics import SETUP, SETUP_TABLES
from app.chat import main_template
from app.core.config import get_settings
from app.crm import flow as flows
from app.crm import supabase_admin
from scripts.group_clinics_data import CLINICS

MAIN = main_template.MAIN
LIST_MAX = 12  # buttons a treatment list holds (app/crm/flow.py)
DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
ACCOUNTS = Path(__file__).resolve().parents[2] / "SEED-ACCOUNTS.local.md"
# The main's own references that must not reach another clinic's chat.
LEFTOVER = re.compile(r"neofollicle|97312|07940|graft|Neo Follicle Hair Transplant|Arya", re.IGNORECASE)
# Typed-question topics that fit every clinic (the main's hair ones are left out); "online" and "intl" only
# where the clinic offers them.
GENERAL_INTENTS = ["about", "book", "bye", "callback", "cancel", "clinic", "greeting", "identity", "notsure",
                   "reschedule", "results", "talk", "thanks", "treat", "cost"]  # fmt: skip
HAIR_WORDS = re.compile(r"hair|transplant|graft|bald|scalp|follicle|beard", re.IGNORECASE)


def obj(raw: Any) -> Any:
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def ampm(hhmm: str) -> str:
    h, m = map(int, hhmm.split(":"))
    return f"{(h + 11) % 12 + 1}{f':{m:02d}' if m else ''} {'AM' if h < 12 else 'PM'}"


def wa_link(c: dict[str, Any]) -> str:
    return f"https://wa.me/{c['whatsapp'].lstrip('+')}?text={quote(c['whatsapp_message'])}"


def button(template: dict[str, Any], bid: str, label: str, value: str = "", action: str | None = None,
           visible: bool = True) -> dict[str, Any]:  # fmt: skip
    b = copy.deepcopy(template)
    b.update({"id": bid, "label": label, "value": value, "visible": visible})
    if action is not None:
        b["action"] = action
    return b


def build(main: dict[str, Any], c: dict[str, Any]) -> dict[str, Any]:
    """The clinic's settings (draft = published), from the main's published ones."""
    s = copy.deepcopy(main)
    bot = "Mira"
    welcome = f"Hi, I'm {bot}, {c['name']}'s AI assistant. How can I help you today?"
    open_line = f"{c['name']} is open {c['hours_text'][0].lower()}{c['hours_text'][1:]}"
    flow = s["flow"]
    nodes = {n["id"]: n for n in flow["nodes"]}
    tpl_btn = nodes["page-treat"]["settings"]["buttons"][0]  # a plain button (goes to its link)
    tpl_treat = nodes["page-ht"]["settings"]["buttons"][0]  # a treatment button
    tpl_notsure = next(b for b in nodes["page-ht"]["settings"]["buttons"] if b["id"] == "b7")
    tpl_link = nodes["page-results"]["settings"]["buttons"][0]
    tpl_call = nodes["page-talk"]["settings"]["buttons"][0]
    tpl_wa = nodes["page-talk"]["settings"]["buttons"][1]
    tpl_cb = nodes["page-talk"]["settings"]["buttons"][2]
    quote_btn = nodes["page-cost_receding"]["settings"]["buttons"][0]
    book_btn = nodes["page-cost_receding"]["settings"]["buttons"][2]
    doc_tpl = nodes["page-doc_sandeep"]
    list_tpl = nodes["page-ht"]
    groups, doctors = c["groups"], c["doctors"]

    drop = {"page-ht", "page-hf", "page-doc_sandeep"} | {n for n in nodes if n.startswith("page-cost_")}
    if not c.get("intl"):
        drop |= {"page-intl", "intl-request"}
    rebuilt = {"page-about", "page-treat", "page-cost"}
    keep = [n for n in flow["nodes"] if n["id"] not in drop]
    edges = [e for e in flow["edges"] if e["source"] not in drop | rebuilt and e["target"] not in drop]
    edges = [e for e in edges if not (e["source"] == "opening" and e["exit"] == "m4" and not c.get("intl"))]

    for n in keep:
        st, nid = n["settings"], n["id"]
        if nid == "page-book" and not c["online"]:
            for b in st["buttons"]:
                if b["id"] == "b2":  # Online consultation
                    b["visible"] = False
        elif nid == "page-about":
            st["buttons"] = [button(tpl_btn, f"b{i + 1}", d["name"]) for i, d in enumerate(doctors)]
            edges += [{"exit": f"b{i + 1}", "source": nid, "target": f"page-doc_{d['slug']}"}
                      for i, d in enumerate(doctors)]  # fmt: skip
        elif nid == "page-treat":
            st["buttons"] = [button(tpl_btn, f"b{i + 1}", g["label"]) for i, g in enumerate(groups)]
            st["buttons"].append(button(tpl_notsure, f"b{len(groups) + 1}", "Not sure, help me choose"))
            edges += [
                {"exit": f"b{i + 1}", "source": nid, "target": f"page-{g['id']}"}
                for i, g in enumerate(groups)
            ]
            edges.append({"exit": f"b{len(groups) + 1}", "source": nid, "target": "page-notsure"})
        elif nid == "page-emergency":
            st["text"] = f"Call on the below attached Contact number. \n\n{open_line}"
            st["buttons"] = [
                st["buttons"][0],
                button(st["buttons"][1], "b2", f"Call {c['phone_label']}", c["phone"]),
            ]
        elif nid == "page-notsure":
            st["message"] = c["notsure"]
            old = {b["label"]: b for b in st["buttons"]}
            st["buttons"] = []
            if c.get("analysis"):
                st["buttons"].append(
                    button(old["Try AI Hair Analysis"], "b1", "Try AI Hair Analysis", c["analysis"])
                )
            st["buttons"] += [
                button(old["Book a consultation"], "", "Book a consultation", "Not sure yet"),
                button(old["Get a callback"], "", "Get a callback", "Help choosing a treatment"),
                button(old["WhatsApp us"], "", "WhatsApp us", wa_link(c)),
            ]
            for i, b in enumerate(st["buttons"]):
                b["id"] = f"b{i + 1}"
        elif nid == "page-intl":
            st["message"] = c["intl"]
            st["buttons"] = [
                st["buttons"][0],
                button(st["buttons"][1], "b2", "Share photos on WhatsApp", wa_link(c)),
                button(st["buttons"][2], "b3", "Read more", c["intl_page"]),
            ]
        elif nid == "page-talk":
            st["message"] = (
                f"Choose how you would like to reach us. We are open {c['hours_text'][0].lower()}"
                f"{c['hours_text'][1:]}"
            )
            st["buttons"] = [
                button(tpl_call, "b1", f"Call {c['phone_label']}", c["phone"]),
                button(tpl_wa, "b2", "WhatsApp us", wa_link(c)),
                button(tpl_cb, "b3", "Request a callback", "General enquiry"),
            ]
        elif nid == "page-clinic":
            st["message"] = (f"**{c['full_name']}**\n{c['address']}, {c['city']} {c['postal_code']}.\n"
                             f"Open {c['hours_text'][0].lower()}{c['hours_text'][1:]}")  # fmt: skip
            st["buttons"] = [
                button(st["buttons"][0], "b1", "Open in Google Maps", c["maps_link"]),
                button(st["buttons"][1], "b2", f"Call {c['phone_label']}", c["phone"]),
            ]
        elif nid == "page-results":
            message, links = c["results"]
            st["message"] = message
            st["buttons"] = [
                button(tpl_link, f"b{i + 1}", label, url) for i, (label, url) in enumerate(links)
            ]
            if not links:
                st["buttons"] = [button(tpl_wa, "b1", "WhatsApp us", wa_link(c)),
                                 button(tpl_cb, "b2", "Request a callback", "Results enquiry")]  # fmt: skip
        elif nid == "page-cost":
            st["message"] = c["cost"]
            st["buttons"] = [button(quote_btn, "b1", "Get exact quote", f"{c['name']} cost"),
                             button(book_btn, "b2", "Book consultation")]  # fmt: skip
            edges.append({"exit": "b2", "source": nid, "target": "page-book"})
        elif nid == "opening":
            st["welcome"] = welcome
            st["figures"] = []
            st["buttons"] = [b for b in st["buttons"] if b["id"] != "m4" or c.get("intl")]
            for b in st["buttons"]:
                if b["id"] == "m6":
                    b["value"] = wa_link(c)

    added = []
    for i, d in enumerate(doctors):
        n = copy.deepcopy(doc_tpl)
        n.update({"id": f"page-doc_{d['slug']}", "title": f"Doc {d['slug'].title()}", "x": 680.0,
                  "y": 1784.0 + 220 * i})  # fmt: skip
        n["settings"].update({
            "doctor": d["name"], "title": d["title"], "qualifications": d["qualifications"],
            "about": d["about"],
            "stats": [{"label": a, "value": b} for a, b in d["stats"]], "profile_url": d["profile_url"],
        })  # fmt: skip
        added.append(n)
    for i, g in enumerate(groups):
        n = copy.deepcopy(list_tpl)
        n.update({"id": f"page-{g['id']}", "title": g["label"], "x": 680.0 + 260 * (i % 3),
                  "y": 684.0 + 300 * (i // 3)})  # fmt: skip
        # A list shows up to 12 buttons: 11 treatments and "Not sure" (all of them stay bookable and typed).
        shown = g["items"][: LIST_MAX - 1]
        btns = [button(tpl_treat, f"b{j + 1}", t["name"], t["name"]) for j, t in enumerate(shown)]
        btns.append(button(tpl_notsure, f"b{len(btns) + 1}", "Not sure, help me choose"))
        n["settings"]["buttons"] = btns
        edges.append({"exit": btns[-1]["id"], "source": n["id"], "target": "page-notsure"})
        added.append(n)
    flow["nodes"] = keep + added
    flow["edges"] = edges

    # The classic menu, the same buttons.
    menu = s["menu"]
    menu["welcome"] = welcome
    menu["figures"], menu["show_figures"] = [], False
    out = []
    for b in menu["buttons"]:
        if b["label"] == "International Patients" and not c.get("intl"):
            continue
        if b["label"] == "Book Consultation":
            for sub in b["sub"]:
                if sub["action"] == "online":
                    sub["visible"] = c["online"]
        elif b["label"] == "Explore Treatments":
            sub0 = b["sub"][0]
            b["sub"] = [dict(sub0, label=g["label"], value=g["id"], action="page") for g in groups]
            b["sub"].append(dict(sub0, label="Not sure, help me choose", value="notsure", action="page"))
        elif b["label"] == "About Doctors":
            sub0 = b["sub"][0]
            b["sub"] = [dict(sub0, label=d["name"], value=f"doc_{d['slug']}", action="page") for d in doctors]
        elif b["label"] == "International Patients":
            b["message"] = c["intl"]
            b["sub"][1]["value"], b["sub"][2]["value"] = wa_link(c), c["intl_page"]
        elif b["action"] == "whatsapp":
            b["value"] = wa_link(c)
        out.append(b)
    menu["buttons"] = out

    hours = []
    for i, day in enumerate(DAYS):
        hours.append({"day": day, "start": c["open"], "end": c["close"], "open": i not in c["closed"]})
    s["contact"].update({
        "email": c["email"], "phone": c["phone"], "whatsapp": c["whatsapp"], "hours": hours,
        "address": f"{c['address']}, {c['city']} {c['postal_code']}", "maps_link": c["maps_link"],
        "landmark": c["landmark"], "parking": "", "whatsapp_message": c["whatsapp_message"],
    })  # fmt: skip
    s["reviews"] = {
        "link": c["maps_link"], "count": "", "rating": "", "videos": "", "celebrities": "",
        "quotes": [{"name": n, "show": True, "text": t, "topic": tp} for n, tp, t in c["reviews"]],
    }  # fmt: skip
    item0 = s["services"]["items"][0]
    s["services"] = {
        "items": [
            dict(
                item0,
                name=t["name"],
                page=t["page"],
                description=t["description"],
                category=g["label"],
                photo="",
                price=None,
                show_price=False,
                duration="",
                book_as="",
                show=True,
            )
            for g in groups
            for t in g["items"]
        ],  # fmt: skip
        "not_offered": c["not_offered"],
        "booking_options": c["booking_options"],
    }
    look = s["appearance"]["look"]
    look.update({"name": bot, "avatar_letter": bot[0], "logo": "", "location": ""})
    s["chat"] = {"canvas": True}

    leftover = LEFTOVER.findall(
        json.dumps({k: s[k] for k in ("flow", "menu", "contact", "services", "reviews")})
    )
    if leftover:
        raise SystemExit(f"{c['code']}: the main's own words are still in its chat: {sorted(set(leftover))}")
    # The chatbot's own checks, as the Dashboard runs them before publishing.
    flows.normalise(s["flow"])
    errors = [p.message for p in flows.check(s["flow"]) if p.level == "error"]
    if errors:
        raise SystemExit(f"{c['code']}: the flow has errors: {errors}")
    return s


def facts(c: dict[str, Any]) -> dict[str, str]:
    """The clinic's facts (Knowledge base -> Clinic info), under the main's keys and other wordings."""
    hours = f"{ampm(c['open'])} to {ampm(c['close'])}"
    wa = c["whatsapp"]
    out = {
        "clinic_name": c["full_name"],
        "clinic_address": f"{c['address']}, {c['city']}, {c['state']} {c['postal_code']}",
        "clinic_city": f"{c['city']} (Bangalore), {c['state']}",
        "clinic_phone": c["phone_label"],
        "clinic_whatsapp": f"+91 {wa[3:8]} {wa[8:]}",
        "clinic_email": c["email"],
        "clinic_website": c["website"],
        "google_maps_link": c["maps_link"],
        "landmark": c["landmark"],
        "branches_count": "1",
        "clinic_type": c["clinic_type"],
        "primary_specialty": c["specialty"],
        "doctors_count": str(len(c["doctors"])),
        "clinic_doctors_kind": "Multi doctor" if len(c["doctors"]) > 1 else "Single doctor",
        "social_media": c["social"],
        "languages": c["languages"],
        "online_consultations": "Yes" if c["online"] else "",
        "time_clinic_open": ampm(c["open"])
        + (" (closed on Tuesday)" if c["closed"] else " (all seven days)"),
        "time_clinic_close": ampm(c["close"]),
    }
    for i, day in enumerate(DAYS):
        out[f"timings_{day.lower()}"] = "Closed" if i in c["closed"] else hours
    return {k: v for k, v in out.items() if v}


async def main(apply: bool, rebuild: bool) -> None:
    pool = await asyncpg.connect(get_settings().database_url, statement_cache_size=0, timeout=30)
    made: list[tuple[str, str, str, str, str]] = []
    try:
        main_row = await pool.fetchrow("select * from app.clinics where id = $1", MAIN)
        main_pub = obj(
            await pool.fetchval("select published from app.clinic_settings where clinic_id = $1", MAIN)
        )
        variants = {r["key"]: r["variants"] for r in await pool.fetch(
            "select key, variants from app.kb_facts where clinic_id = $1", MAIN)}  # fmt: skip
        phrases = await pool.fetch(
            "select intent, example from app.intent_examples where clinic_id = $1 and status = 'approved'",
            MAIN,
        )
        taken = {r["id"] for r in await pool.fetch("select id from app.clinics")}
        built = {c["code"]: build(main_pub, c) for c in CLINICS}  # every check before anything changes
        for c in CLINICS:
            s = built[c["code"]]
            n = len(s["flow"]["nodes"])
            print(f"{c['code']} {c['name']}: {'exists, left as is' if c['code'] in taken else 'new'}; "
                  f"{n} flow steps, {len(s['services']['items'])} treatments in {len(c['groups'])} groups, "
                  f"{len(c['doctors'])} doctors, team of {len(c['team'])}")  # fmt: skip
        print("BF (BB Fertility):", "will be removed" if "BF" in taken else "not there")
        if not apply:
            print("Nothing changed. Run with --apply to make it (--rebuild-chat: rebuild existing chats).")
            return

        async with pool.transaction():
            if "BF" in taken:
                # Published versions are never changed: paused for this removal only, in this transaction.
                guard = "clinic_setting_versions_no_update"
                await pool.execute(f"alter table app.clinic_setting_versions disable trigger {guard}")
                for table in SETUP_TABLES:
                    await pool.execute(f"delete from app.{table} where clinic_id = 'BF'")
                await pool.execute(f"alter table app.clinic_setting_versions enable trigger {guard}")
                await pool.execute("delete from app.clinics where id = 'BF'")
                print("removed BF")
            for c in CLINICS:
                code = c["code"]
                if code in taken:
                    if rebuild:  # the chat only, published as a new version
                        data = json.dumps(built[code])
                        version = await pool.fetchval(
                            """update app.clinic_settings set draft = $2::jsonb, published = $2::jsonb,
                                 version = version + 1, published_at = now(), updated_at = now()
                               where clinic_id = $1 returning version""",
                            code, data,
                        )  # fmt: skip
                        await pool.execute(
                            """insert into app.clinic_setting_versions (clinic_id, version, settings,
                                 published_at)
                               values ($1, $2, $3::jsonb, now())""",
                            code, version, data,
                        )  # fmt: skip
                        print(f"rebuilt {code}'s chat (version {version})")
                    continue
                s = built[code]
                cols = ["id", "name", "bot_name", "phone", "whatsapp", "website", "email", "address", "city",
                        "state", "postal_code", "country", "allowed_origins", *SETUP]  # fmt: skip
                values = [code, c["name"], "Mira", c["phone"], c["whatsapp"], c["website"], c["email"],
                          c["address"], c["city"], c["state"], c["postal_code"], "India", [c["website"]],
                          *(main_row[k] for k in SETUP)]  # fmt: skip
                marks = ", ".join(f"${i}" for i in range(1, len(cols) + 1))
                await pool.execute(f"insert into app.clinics ({', '.join(cols)}) values ({marks})", *values)
                await pool.execute(
                    """update app.clinics set open_time = $2::time, close_time = $3::time,
                         closed_weekdays = $4,
                         lead_assignment = 'inbox' where id = $1""",
                    code, time.fromisoformat(c["open"]), time.fromisoformat(c["close"]), c["closed"],
                )  # fmt: skip
                data = json.dumps(s)
                await pool.execute(
                    """insert into app.clinic_settings (clinic_id, draft, published, version, published_at,
                         follows)
                       values ($1, $2::jsonb, $2::jsonb, 1, now(), $3)""",
                    code, data, ["template", "appearance"],
                )  # fmt: skip
                await pool.execute(
                    """insert into app.clinic_setting_versions (clinic_id, version, settings, published_at)
                       values ($1, 1, $2::jsonb, now())""",
                    code, data,
                )  # fmt: skip
                await pool.execute(
                    """insert into app.clinic_websites (clinic_id, origin, status, decided_at)
                       values ($1, $2, 'approved', now())""",
                    code, c["website"],
                )  # fmt: skip
                for i, d in enumerate(c["doctors"]):
                    doc = await pool.fetchval(
                        """insert into app.doctors (clinic_id, name, role_title, qualifications, profile,
                             sort_order)
                           values ($1, $2, $3, $4, $5::jsonb, $6) returning id""",
                        code, d["name"], d["title"], d["qualifications"],
                        json.dumps({"about": d["about"], "photo": "", "profile_url": d["profile_url"],
                                    "stats": [{"label": a, "value": b} for a, b in d["stats"]]}), i,
                    )  # fmt: skip
                    for day in range(7):
                        if day in c["closed"]:
                            continue
                        for mode in ("in_clinic", "online") if c["online"] else ("in_clinic",):
                            await pool.execute(
                                """insert into app.doctor_availability (doctor_id, clinic_id, weekday, mode,
                                     start_time, end_time) values ($1, $2, $3, $4, $5::time, $6::time)""",
                                doc, code, day, mode, time.fromisoformat(c["open"]),
                                time.fromisoformat(c["close"]),
                            )  # fmt: skip
                for key, v in facts(c).items():
                    await pool.execute(
                        """insert into app.kb_facts (clinic_id, key, category, value, variants, status,
                             approved_at)
                           values ($1, $2, 'clinic_info', $3, $4, 'approved', now())""",
                        code, key, v, variants.get(key) or "",
                    )  # fmt: skip
                wanted = set(GENERAL_INTENTS) | ({"online"} if c["online"] else set()) | (
                    {"intl"} if c.get("intl") else set())  # fmt: skip
                for p in phrases:
                    if p["intent"] not in wanted or (
                        p["intent"] in ("cost", "notsure") and HAIR_WORDS.search(p["example"])
                    ):
                        continue
                    example = re.sub(r"\barya\b", "mira", p["example"], flags=re.IGNORECASE)
                    await pool.execute(
                        """insert into app.intent_examples (clinic_id, intent, example, status, approved_at)
                           values ($1, $2, $3, 'approved', now()) on conflict do nothing""",
                        code, p["intent"], example,
                    )  # fmt: skip
                print(f"made {code}")
    finally:
        await pool.close()

    # The team: logins made directly (no email is sent), then their roles. Only for a clinic with no team yet,
    # so running again finishes what an interrupted run left.
    pool = await asyncpg.connect(get_settings().database_url, statement_cache_size=0, timeout=30)
    try:
        for c in CLINICS:
            if await pool.fetchval("select count(*) from app.user_clinics where clinic_id = $1", c["code"]):
                continue
            for name, role in c["team"]:
                email = f"{name.lower().replace(' ', '.')}@{c['code'].lower()}.example.com"
                password = secrets.token_urlsafe(12)
                uid = await supabase_admin.create_user(email, password, name)
                await pool.execute(
                    "insert into app.profiles (id, full_name, email) values ($1::uuid, $2, $3) "
                    "on conflict do nothing",
                    uid, name, email,
                )  # fmt: skip
                await pool.execute(
                    """insert into app.user_clinics (user_id, clinic_id, role, in_round_robin)
                       values ($1::uuid, $2, $3, $3 = 'front_desk')""",
                    uid, c["code"], role,
                )  # fmt: skip
                made.append((c["code"], name, role, email, password))
    finally:
        await pool.close()
    if made:
        lines = ["# Placeholder logins for the new clinics (local only, not in git)", "",
                 "Temporary: replace with the real staff before going live.", "",
                 "| Clinic | Name | Role | Email | Password |", "|---|---|---|---|---|"]  # fmt: skip
        lines += [f"| {a} | {b} | {'Admin' if r == 'clinic_manager' else 'Front Desk'} | {e} | `{p}` |"
                  for a, b, r, e, p in made]  # fmt: skip
        ACCOUNTS.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"{len(made)} logins made; passwords in {ACCOUNTS.name}")


if __name__ == "__main__":
    asyncio.run(main(apply="--apply" in sys.argv, rebuild="--rebuild-chat" in sys.argv))
