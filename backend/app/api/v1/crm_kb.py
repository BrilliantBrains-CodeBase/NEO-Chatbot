"""Dashboard → Knowledge base, JSON only: a clinic's facts and Q&A (Clinic Knowledge Strategy: one fact, many
answers). Staff save drafts; a clinic manager or BB Admin approves, and only approved rows answer patients
(the bot never learns by itself). A Q&A answer may link facts by key, "{consult_fee}", filled from the
approved fact when the bot replies; an answer whose linked fact is missing is never given.
"""

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.chat import kb
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


class Knowledge(BaseModel):
    facts: list[Fact]
    qa: list[Qa]
    can_approve: bool  # clinic manager or BB Admin


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
    approved = {f["key"] for f in facts if f["status"] == "approved"}
    used: dict[str, int] = {}
    for q in qa:
        if q["status"] != "retired":
            for k in kb.links(q["answer"]):
                used[k] = used.get(k, 0) + 1
    return Knowledge(
        facts=[
            Fact(id=str(f["id"]), key=f["key"], category=f["category"], value=f["value"],
                 variants=f["variants"],
                 status=f["status"], used_by=used.get(f["key"], 0), updated_at=f["updated_at"].isoformat())
            for f in facts
        ],
        qa=[
            Qa(id=str(q["id"]), question=q["question"], variants=q["variants"], answer=q["answer"],
               category=q["category"], treatment=q["treatment"], status=q["status"],
               links=kb.links(q["answer"]), missing=[k for k in kb.links(q["answer"]) if k not in approved],
               updated_at=q["updated_at"].isoformat())
            for q in qa
        ],
        can_approve=_approver(user, clinic),
    )  # fmt: skip


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
    """A new fact, as a draft (a manager approves it)."""
    await _write(
        user,
        clinic,
        "insert into app.kb_facts (clinic_id, key, category, value, variants) values ($1, $2, $3, $4, $5)",
        clinic, body.key, body.category, body.value.strip(), body.variants,
    )  # fmt: skip
    return await _knowledge(clinic, user)


@router.put("/{clinic}/kb/facts/{fact_id}", response_model=Knowledge)
async def save_fact(
    user: Annotated[Staff, Depends(staff)], clinic: str, fact_id: str, body: FactIn
) -> Knowledge:
    """A changed fact goes back to draft until approved again (every answer linking it waits too)."""
    done = await _write(
        user,
        clinic,
        """update app.kb_facts set key = $3, category = $4, value = $5, variants = $6, status = 'draft',
             approved_by = null, approved_at = null where id = $1::uuid and clinic_id = $2 returning id""",
        _uuid(fact_id), clinic, body.key, body.category, body.value.strip(), body.variants,
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


@router.post("/{clinic}/kb/{kind}/{row_id}/{action}", response_model=Knowledge)
async def set_status(
    user: Annotated[Staff, Depends(staff)],
    clinic: str,
    kind: Literal["facts", "qa"],
    row_id: str,
    action: Literal["approve", "retire", "draft"],
) -> Knowledge:
    """Approve (manager or BB Admin: the bot uses it from now), retire (the bot stops using it), or back to
    draft. Approving a Q&A whose answer links a missing fact is refused."""
    if action == "approve" and not _approver(user, clinic):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a clinic manager or BB Admin can approve.")
    table = "app.kb_facts" if kind == "facts" else "app.kb_qa"
    if action == "approve" and kind == "qa":
        pool = await get_pool()
        answer = await pool.fetchval(
            "select answer from app.kb_qa where id = $1::uuid and clinic_id = $2", _uuid(row_id), clinic
        )
        rows = await pool.fetch(
            "select key from app.kb_facts where clinic_id = $1 and status = 'approved'", clinic
        )
        approved = {r["key"] for r in rows}
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
