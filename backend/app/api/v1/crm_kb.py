"""Dashboard → Knowledge base, JSON only: a clinic's facts and Q&A (Clinic Knowledge Strategy: one fact, many
answers). Staff save drafts; an admin or Super Admin approves, and only approved rows answer patients
(the bot never learns by itself). A Q&A answer may link facts by key, "{consult_fee}", filled from the
approved fact when the bot replies; an answer whose linked fact is missing is never given.
"""

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.chat import canvas, kb
from app.chat.live_facts import SOURCE, live_facts
from app.core.db import get_pool
from app.crm.auth import Staff, staff

router = APIRouter(prefix="/crm/console", tags=["crm"])

Category = Literal["clinic_info", "treatment", "cost", "doctor", "policy", "other"]
KEY = r"^[a-z][a-z0-9_]{1,49}$"


def _lines(v: str) -> str:
    """Other wordings: one per line, trimmed, no blanks or repeats."""
    return "\n".join(dict.fromkeys(x.strip() for x in v.splitlines() if x.strip()))


class FactIn(BaseModel):
    key: str = Field(pattern=KEY)  # e.g. consult_fee, used as {consult_fee} in answers
    category: Category = "clinic_info"
    value: str = Field(min_length=1, max_length=2000)
    variants: str = Field(default="", max_length=4000)  # other ways patients ask for it, one per line

    @field_validator("variants")
    @classmethod
    def _v(cls, v: str) -> str:
        return _lines(v)


class QaIn(BaseModel):
    question: str = Field(min_length=3, max_length=300)
    variants: str = Field(default="", max_length=4000)  # other wordings, one per line
    answer: str = Field(min_length=1, max_length=2000)  # may link facts: {consult_fee}
    category: Category = "other"
    treatment: str | None = Field(default=None, max_length=100)

    @field_validator("variants")
    @classmethod
    def _v(cls, v: str) -> str:
        return _lines(v)


class Fact(BaseModel):
    id: str
    key: str
    category: str
    value: str
    variants: str
    status: str  # draft | approved | retired
    used_by: int  # Q&A answers that link it
    replaced: str | None = None  # the Dashboard / CRM place that answers this key instead (retire this fact)
    updated_at: str


class Qa(BaseModel):
    id: str
    question: str
    variants: str
    answer: str
    category: str
    treatment: str | None
    status: str
    links: list[str]  # the facts its answer links
    missing: list[str]  # linked facts that are not approved: the bot does not give this answer
    updated_at: str


class Live(BaseModel):
    key: str
    value: str
    source: str  # where staff change it


class Knowledge(BaseModel):
    facts: list[Fact]
    live: list[Live]  # read from the Dashboard and CRM: not typed in the Knowledge base
    qa: list[Qa]
    can_approve: bool  # admin or Super Admin
    kb_only: bool = False  # the live chat answers typed questions from the Knowledge base alone (testing)


def _approver(user: Staff, clinic: str) -> bool:
    return user.bb_admin or user.roles.get(clinic) == "clinic_manager"


def _uuid(v: str) -> str:
    try:
        UUID(v)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.") from None
    return v


async def _knowledge(clinic: str, user: Staff) -> Knowledge:
    pool = await get_pool()
    facts = await pool.fetch(
        "select id, key, category, value, variants, status, updated_at from app.kb_facts "
        "where clinic_id = $1 order by status = 'retired', category, key",
        clinic,
    )
    qa = await pool.fetch(
        "select id, question, variants, answer, category, treatment, status, updated_at from app.kb_qa "
        "where clinic_id = $1 order by status = 'retired', category, question",
        clinic,
    )
    async with pool.acquire() as conn:
        live = await live_facts(conn, clinic)
    approved = {f["key"] for f in facts if f["status"] == "approved"} | set(live)
    used: dict[str, int] = {}
    for q in qa:
        if q["status"] != "retired":
            for k in kb.links(q["answer"]):
                used[k] = used.get(k, 0) + 1
    return Knowledge(
        facts=[
            Fact(id=str(f["id"]), key=f["key"], category=f["category"], value=f["value"],
                 variants=f["variants"],
                 status=f["status"], used_by=used.get(f["key"], 0), updated_at=f["updated_at"].isoformat(),
                 replaced=SOURCE.get(f["key"], "Chatbot settings") if f["key"] in live else None)
            for f in facts
        ],
        live=[Live(key=k, value=v, source=SOURCE.get(k, "Chatbot settings")) for k, v in live.items()],
        qa=[
            Qa(id=str(q["id"]), question=q["question"], variants=q["variants"], answer=q["answer"],
               category=q["category"], treatment=q["treatment"], status=q["status"],
               links=kb.links(q["answer"]), missing=[k for k in kb.links(q["answer"]) if k not in approved],
               updated_at=q["updated_at"].isoformat())
            for q in qa
        ],
        can_approve=_approver(user, clinic),
        kb_only=bool(await pool.fetchval(
            "select coalesce((published->>'kb_only')::boolean, false) from app.clinic_settings "
            "where clinic_id = $1",
            clinic,
        )),
    )  # fmt: skip


async def _value(clinic: str, key: str, typed: str) -> str:
    """The value to keep: as typed, or for a key the Dashboard / CRM answers (live), its live value (only its
    wordings and category are the Knowledge base's own; the answer always comes from there)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        live = await live_facts(conn, clinic)
    if key not in live and key not in SOURCE:
        return typed.strip()
    if not live.get(key):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{{{key}}} is answered in {SOURCE.get(key, 'the Chatbot settings')}: fill it in there first.",
        )
    return live[key]


async def _write(user: Staff, clinic: str, sql: str, *args: Any) -> Any:
    """One change, as the signed-in person (audited). The bot reads it at once (its caches are cleared)."""
    kb.forget(clinic)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        try:
            return await conn.fetchval(sql, *args)
        except Exception as e:  # the one rule the form cannot check: a key already used in this clinic
            if "kb_facts_clinic_id_key_key" in str(e):
                raise HTTPException(
                    status.HTTP_409_CONFLICT, "A fact with this key already exists. Edit that one instead."
                ) from None
            raise


@router.get("/{clinic}/kb", response_model=Knowledge)
async def knowledge(user: Annotated[Staff, Depends(staff)], clinic: str) -> Knowledge:
    return await _knowledge(clinic, user)


@router.post("/{clinic}/kb/facts", response_model=Knowledge)
async def add_fact(user: Annotated[Staff, Depends(staff)], clinic: str, body: FactIn) -> Knowledge:
    """A new fact, as a draft (a manager approves it). For a key the Dashboard / CRM answers, only its
    wordings are the fact's: its answer is the live value."""
    value = await _value(clinic, body.key, body.value)
    await _write(
        user,
        clinic,
        "insert into app.kb_facts (clinic_id, key, category, value, variants) values ($1, $2, $3, $4, $5)",
        clinic, body.key, body.category, value, body.variants,
    )  # fmt: skip
    return await _knowledge(clinic, user)


@router.put("/{clinic}/kb/facts/{fact_id}", response_model=Knowledge)
async def save_fact(
    user: Annotated[Staff, Depends(staff)], clinic: str, fact_id: str, body: FactIn
) -> Knowledge:
    """A changed fact goes back to draft until approved again (every answer linking it waits too)."""
    value = await _value(clinic, body.key, body.value)
    done = await _write(
        user,
        clinic,
        """update app.kb_facts set key = $3, category = $4, value = $5, variants = $6, status = 'draft',
             approved_by = null, approved_at = null where id = $1::uuid and clinic_id = $2 returning id""",
        _uuid(fact_id), clinic, body.key, body.category, value, body.variants,
    )  # fmt: skip
    if done is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fact not found.")
    return await _knowledge(clinic, user)


@router.post("/{clinic}/kb/qa", response_model=Knowledge)
async def add_qa(user: Annotated[Staff, Depends(staff)], clinic: str, body: QaIn) -> Knowledge:
    """A new question and answer, as a draft."""
    await _write(
        user,
        clinic,
        """insert into app.kb_qa (clinic_id, question, variants, answer, category, treatment)
           values ($1, $2, $3, $4, $5, $6)""",
        clinic, body.question.strip(), body.variants, body.answer.strip(), body.category,
        (body.treatment or "").strip() or None,
    )  # fmt: skip
    return await _knowledge(clinic, user)


@router.put("/{clinic}/kb/qa/{qa_id}", response_model=Knowledge)
async def save_qa(user: Annotated[Staff, Depends(staff)], clinic: str, qa_id: str, body: QaIn) -> Knowledge:
    """A changed Q&A goes back to draft until approved again."""
    done = await _write(
        user,
        clinic,
        """update app.kb_qa set question = $3, variants = $4, answer = $5, category = $6, treatment = $7,
             status = 'draft', approved_by = null, approved_at = null
           where id = $1::uuid and clinic_id = $2 returning id""",
        _uuid(qa_id), clinic, body.question.strip(), body.variants, body.answer.strip(), body.category,
        (body.treatment or "").strip() or None,
    )  # fmt: skip
    if done is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found.")
    return await _knowledge(clinic, user)


class Mode(BaseModel):
    kb_only: bool


@router.post("/{clinic}/kb/mode", response_model=Knowledge)
async def set_mode(user: Annotated[Staff, Depends(staff)], clinic: str, body: Mode) -> Knowledge:
    """Typed questions in the live chat: from the Knowledge base only (testing), or as usual. Kept in the
    published and the draft settings, so publishing the canvas does not undo it. Manager or Super Admin."""
    if not _approver(user, clinic):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin or Super Admin can change this.")
    await _write(
        user,
        clinic,
        """update app.clinic_settings
             set published = jsonb_set(published, '{kb_only}', to_jsonb($2::boolean)),
                 draft = jsonb_set(draft, '{kb_only}', to_jsonb($2::boolean))
           where clinic_id = $1 returning clinic_id""",
        clinic, body.kb_only,
    )  # fmt: skip
    canvas.forget(clinic)  # the live chat follows the switch at once
    return await _knowledge(clinic, user)


class ImportRow(BaseModel):
    """One row of an uploaded file, as the CRM read it (it is checked here, row by row)."""

    row: int  # its line in the file, for the report
    kind: Literal["fact", "qa"]
    key: str = ""
    category: str = ""
    value: str = ""  # a fact's value, or a Q&A's answer
    question: str = ""
    variants: str = ""
    treatment: str = ""


class ImportIn(BaseModel):
    rows: list[ImportRow] = Field(max_length=2000)


class Imported(BaseModel):
    added: int
    updated: int
    unchanged: int
    problems: list[str]  # "Row 7: ..."
    knowledge: Knowledge


@router.post("/{clinic}/kb/import", response_model=Imported)
async def import_rows(user: Annotated[Staff, Depends(staff)], clinic: str, body: ImportIn) -> Imported:
    """An uploaded file's rows as drafts: a fact by key, a Q&A by question (the same key or question updates
    that entry, back to draft; a new one is added). Nothing is approved here. A wrong row is reported and
    skipped; the rest are saved."""
    pool = await get_pool()
    added = updated = unchanged = 0
    problems: list[str] = []
    kb.forget(clinic)
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        live = await live_facts(conn, clinic)
        facts = {
            r["key"]: r
            for r in await conn.fetch(
                "select id, key, category, value, variants from app.kb_facts where clinic_id = $1", clinic
            )
        }
        qas = {
            " ".join(r["question"].lower().split()): r
            for r in await conn.fetch(
                "select id, question, variants, answer, category, treatment from app.kb_qa "
                "where clinic_id = $1",
                clinic,
            )
        }
        for r in body.rows:
            try:
                category = r.category.strip().lower() or ("clinic_info" if r.kind == "fact" else "other")
                if r.kind == "fact" and (r.key.strip() in live or r.key.strip() in SOURCE):
                    where = SOURCE.get(r.key.strip(), "the Chatbot settings")
                    problems.append(
                        f"Row {r.row}: {{{r.key.strip()}}} is answered in {where}; change it there"
                    )
                    continue
                if r.kind == "fact":
                    f = FactIn(key=r.key.strip(), category=category, value=r.value, variants=r.variants)
                    old = facts.get(f.key)
                    if old and (old["value"], old["category"], old["variants"]) == (
                        f.value.strip(),
                        f.category,
                        f.variants,
                    ):
                        unchanged += 1
                    elif old:
                        await conn.execute(
                            """update app.kb_facts set category = $2, value = $3, variants = $4,
                                 status = 'draft', approved_by = null, approved_at = null where id = $1""",
                            old["id"], f.category, f.value.strip(), f.variants,
                        )  # fmt: skip
                        updated += 1
                    else:
                        await conn.execute(
                            """insert into app.kb_facts (clinic_id, key, category, value, variants)
                               values ($1, $2, $3, $4, $5)""",
                            clinic, f.key, f.category, f.value.strip(), f.variants,
                        )  # fmt: skip
                        facts[f.key] = {
                            "value": f.value.strip(),
                            "category": f.category,
                            "variants": f.variants,
                        }
                        added += 1
                else:
                    q = QaIn(question=r.question, variants=r.variants, answer=r.value, category=category,
                             treatment=r.treatment or None)  # fmt: skip
                    same = " ".join(q.question.lower().split())
                    old = qas.get(same)
                    treatment = (q.treatment or "").strip() or None
                    if old and (old["answer"], old["variants"], old["category"], old["treatment"]) == (
                        q.answer.strip(),
                        q.variants,
                        q.category,
                        treatment,
                    ):
                        unchanged += 1
                    elif old:
                        await conn.execute(
                            """update app.kb_qa set variants = $2, answer = $3, category = $4, treatment = $5,
                                 status = 'draft', approved_by = null, approved_at = null where id = $1""",
                            old["id"], q.variants, q.answer.strip(), q.category, treatment,
                        )  # fmt: skip
                        updated += 1
                    else:
                        await conn.execute(
                            """insert into app.kb_qa
                                 (clinic_id, question, variants, answer, category, treatment)
                               values ($1, $2, $3, $4, $5, $6)""",
                            clinic, q.question.strip(), q.variants, q.answer.strip(), q.category, treatment,
                        )  # fmt: skip
                        qas[same] = {
                            "answer": q.answer.strip(), "variants": q.variants, "category": q.category,
                            "treatment": treatment,
                        }  # fmt: skip
                        added += 1
            except ValidationError as e:
                why = "; ".join(
                    f"{'.'.join(str(x) for x in err['loc'])}: {err['msg'].replace('Value error, ', '')}"
                    for err in e.errors()
                )
                problems.append(f"Row {r.row}: {why}")
    return Imported(
        added=added, updated=updated, unchanged=unchanged, problems=problems[:100],
        knowledge=await _knowledge(clinic, user),
    )  # fmt: skip


@router.post("/{clinic}/kb/{kind}/{row_id}/{action}", response_model=Knowledge)
async def set_status(
    user: Annotated[Staff, Depends(staff)],
    clinic: str,
    kind: Literal["facts", "qa"],
    row_id: str,
    action: Literal["approve", "retire", "draft"],
) -> Knowledge:
    """Approve (manager or Super Admin: the bot uses it from now), retire (the bot stops using it), or back to
    draft. Approving a Q&A whose answer links a missing fact is refused."""
    if action == "approve" and not _approver(user, clinic):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin or Super Admin can approve.")
    table = "app.kb_facts" if kind == "facts" else "app.kb_qa"
    if action == "approve" and kind == "qa":
        pool = await get_pool()
        answer = await pool.fetchval(
            "select answer from app.kb_qa where id = $1::uuid and clinic_id = $2", _uuid(row_id), clinic
        )
        rows = await pool.fetch(
            "select key from app.kb_facts where clinic_id = $1 and status = 'approved'", clinic
        )
        async with pool.acquire() as conn:
            approved = {r["key"] for r in rows} | set(await live_facts(conn, clinic))
        missing = [k for k in kb.links(answer or "") if k not in approved]
        if missing:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Approve these facts first (the answer links them): "
                + ", ".join("{" + k + "}" for k in missing),
            )
    new = {"approve": "approved", "retire": "retired", "draft": "draft"}[action]
    done = await _write(
        user,
        clinic,
        f"""update {table} set status = $3,
              approved_by = case when $3 = 'approved' then $4::uuid end,
              approved_at = case when $3 = 'approved' then now() end
            where id = $1::uuid and clinic_id = $2 returning id""",
        _uuid(row_id), clinic, new, user.id,
    )  # fmt: skip
    if done is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    return await _knowledge(clinic, user)
