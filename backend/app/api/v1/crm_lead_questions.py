"""Chatbot → Clinic info → Lead questions (user, 2026-11-13), JSON only: every question the bot had no
approved answer for (app.unanswered_questions, kept at once in the chat), newest first, with the patient when
they left their number. Staff mark one answered after the call, or turn it into a Knowledge base draft (the
bot never learns by itself: the draft is filled in and approved by staff). Clinic Manager and Super Admin
only, as the table's own rule (app.can_manage). After 90 days the nightly job unlinks the patient.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.v1.crm_lead_delete import managers_only
from app.chat import kb
from app.core.db import get_pool
from app.crm.auth import Staff, staff

router = APIRouter(prefix="/crm/console", tags=["crm"])
PAGE = 50


class Asked(BaseModel):
    id: int
    question: str
    reason: Literal["medical", "no_match", "llm_rejected"]
    answered: bool
    created_at: str
    lead_code: str | None  # the patient, when they left their number (and within 90 days)
    lead_name: str | None


class LeadQuestions(BaseModel):
    items: list[Asked]
    total: int
    new: int  # not answered yet (the Dashboard's "Unanswered chat questions")


class Answered(BaseModel):
    answered: bool


class Drafted(BaseModel):
    qa_id: str


@router.get("/{clinic}/lead-questions", response_model=LeadQuestions)
async def lead_questions(
    user: Annotated[Staff, Depends(staff)],
    clinic: str,
    show: Annotated[Literal["new", "answered", "all"], Query()] = "new",
    q: Annotated[str, Query(max_length=100)] = "",
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
) -> LeadQuestions:
    managers_only(user, clinic)
    where = ["u.clinic_id = $1"]
    if show != "all":
        where.append("u.reviewed" if show == "answered" else "not u.reviewed")
    args: list[object] = [clinic]
    if q.strip():
        args.append(f"%{q.strip()}%")
        where.append(
            f"(u.question_text ilike ${len(args)} or l.full_name ilike ${len(args)} "
            f"or l.lead_code ilike ${len(args)})"
        )
    sql_where = " and ".join(where)
    pool = await get_pool()
    rows = await pool.fetch(
        f"""select u.id, u.question_text, u.reason, u.reviewed, u.created_at, l.lead_code, l.full_name
            from app.unanswered_questions u
            left join app.leads l on l.id = u.lead_id and l.deleted_at is null
            where {sql_where} order by u.created_at desc, u.id desc
            limit {PAGE} offset {(page - 1) * PAGE}""",
        *args,
    )
    total = await pool.fetchval(
        f"""select count(*) from app.unanswered_questions u
            left join app.leads l on l.id = u.lead_id and l.deleted_at is null where {sql_where}""",
        *args,
    )
    new = await pool.fetchval(
        "select count(*) from app.unanswered_questions where clinic_id = $1 and not reviewed", clinic
    )
    return LeadQuestions(
        items=[
            Asked(id=r["id"], question=r["question_text"], reason=r["reason"], answered=r["reviewed"],
                  created_at=r["created_at"].isoformat(), lead_code=r["lead_code"], lead_name=r["full_name"])
            for r in rows
        ],
        total=total,
        new=new,
    )  # fmt: skip


@router.put("/{clinic}/lead-questions/{question_id}", response_model=Answered)
async def mark(
    user: Annotated[Staff, Depends(staff)], clinic: str, question_id: int, body: Answered
) -> Answered:
    """Answered after the clinic called (or back to new)."""
    managers_only(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)  # audit: who
        done = await conn.fetchval(
            "update app.unanswered_questions set reviewed = $3 where id = $1 and clinic_id = $2 returning id",
            question_id, clinic, body.answered,
        )  # fmt: skip
    if done is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found.")
    return body


class ToKb(BaseModel):
    answer: str = Field(default="", max_length=2000)  # empty: a placeholder staff replace before approving


@router.post("/{clinic}/lead-questions/{question_id}/kb", response_model=Drafted)
async def to_knowledge_base(
    user: Annotated[Staff, Depends(staff)], clinic: str, question_id: int, body: ToKb
) -> Drafted:
    """A Knowledge base Q&A DRAFT from the question (never live until a manager approves it there). The
    question is marked answered."""
    managers_only(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        text = await conn.fetchval(
            "select question_text from app.unanswered_questions where id = $1 and clinic_id = $2",
            question_id, clinic,
        )  # fmt: skip
        if text is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found.")
        question = " ".join(str(text).split())[:300]
        if len(question) < 3:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "This question is too short for a Q&A.")
        answer = body.answer.strip() or "Write the answer here, then approve it in Knowledge base."
        qa = await conn.fetchval(
            """insert into app.kb_qa (clinic_id, question, variants, answer, category)
               values ($1, $2, '', $3, 'other') returning id""",
            clinic, question, answer,
        )  # fmt: skip
        await conn.execute("update app.unanswered_questions set reviewed = true where id = $1", question_id)
    kb.forget(clinic)
    return Drafted(qa_id=str(qa))
