"""Free appointment slots, from the database: clinic hours, closed weekdays and holidays, doctor
availability and leave, and the appointments already pending or confirmed. A time is offered only if
at least one doctor is free. One query covers the whole booking window.

Each doctor's slots are their own length for the kind of visit (Dashboard → Doctors), else the clinic's.
In-clinic slots stay inside the clinic's opening hours and open days; online slots follow only the doctor's
online hours (user, 2026-10-31). Holidays and leave apply to both. A booking or hold blocks its whole length
for both kinds of visit (one diary per doctor).
"""

from datetime import date
from typing import Literal

import asyncpg

Mode = Literal["in_clinic", "online"]

# In-clinic: slot starts run from the later of clinic opening and the doctor's start, to the earlier of
# (doctor end - slot length) and (clinic closing - last slot gap). Online: from the doctor's start to
# (doctor end - slot length). Times are the clinic's local time; appointments are compared in real time
# (timestamptz) through the clinic's time zone.
FREE_SLOTS = """
with c as (
  select * from app.clinics where id = $1 and active
),
days as (
  select gs::date as day from c, generate_series($2::date, $3::date, interval '1 day') gs
  where ($4 = 'online' or not (extract(dow from gs)::smallint = any (c.closed_weekdays)))
    and not exists (select 1 from app.clinic_holidays h where h.clinic_id = $1 and h.day = gs::date)
),
d as (
  select days.day, da.doctor_id, da.start_time, da.end_time,
    make_interval(mins => coalesce(
      case when $4 = 'online' then doc.online_minutes else doc.in_clinic_minutes end,
      case when $4 = 'online' then c.online_slot_minutes else c.slot_minutes end)) as len
  from days, c
  join app.doctor_availability da
    on da.clinic_id = $1 and da.mode = $4
    and ($6::uuid is null or da.doctor_id = $6)  -- one doctor (CRM), or any
  join app.doctors doc on doc.id = da.doctor_id and doc.active
  where da.weekday = extract(dow from days.day)::smallint
    and not exists (
      select 1 from app.doctor_leave l
      where l.doctor_id = da.doctor_id and days.day between l.from_date and l.to_date
    )
),
s as (
  select d.day, d.doctor_id, d.len, gs::time as t
  from d, c,
  generate_series(
    d.day + case when $4 = 'online' then d.start_time else greatest(d.start_time, c.open_time) end,
    d.day + case when $4 = 'online' then d.end_time - d.len
                 else least(d.end_time - d.len,
                            c.close_time - make_interval(mins => c.last_slot_before_close_min)) end,
    d.len
  ) gs
)
select s.day, array_agg(distinct to_char(s.t, 'HH24:MI') order by to_char(s.t, 'HH24:MI')) as slots
from s, c
where not exists (
  select 1 from app.appointments a
  where a.doctor_id = s.doctor_id
    and a.status in ('pending', 'confirmed')
    and a.slot && tstzrange(
      (s.day + s.t) at time zone c.timezone,
      (s.day + s.t + s.len) at time zone c.timezone,
      '[)'
    )
)
and not exists (  -- held for another patient who is checking the summary
  select 1 from app.slot_holds h
  where h.doctor_id = s.doctor_id and h.expires_at > now() and h.session_id <> $5
    and h.slot && tstzrange(
      (s.day + s.t) at time zone c.timezone,
      (s.day + s.t + s.len) at time zone c.timezone,
      '[)'
    )
)
group by s.day
"""


async def free_slots_range(
    conn: asyncpg.Connection,
    clinic_id: str,
    first: date,
    last: date,
    mode: Mode,
    today: date,
    now_minutes: int,
    session_id: str = "",
    doctor_id: str | None = None,
) -> dict[str, list[str]]:
    """Free HH:MM slot starts per day (YYYY-MM-DD). Days without a free slot are left out; for today,
    past times are removed. The session's own hold does not hide its time."""
    out: dict[str, list[str]] = {}
    for r in await conn.fetch(FREE_SLOTS, clinic_id, first, last, mode, session_id, doctor_id):
        slots = list(r["slots"])
        if r["day"] == today:
            slots = [s for s in slots if int(s[:2]) * 60 + int(s[3:]) > now_minutes]
        if slots:
            out[r["day"].isoformat()] = slots
    return out


async def free_slots(
    conn: asyncpg.Connection, clinic_id: str, day: date, mode: Mode, today: date, now_minutes: int
) -> list[str]:
    return (await free_slots_range(conn, clinic_id, day, day, mode, today, now_minutes)).get(
        day.isoformat(), []
    )


async def doctors_today(
    conn: asyncpg.Connection, clinic_id: str, today: date, now_minutes: int, days: int = 14
) -> dict[str, dict[str, object]]:
    """Each active doctor's day today, by name, for the chat's doctor card: their in-clinic and online hours
    (in-clinic only when the clinic is open), on leave or not, today's free in-clinic starts (past times left
    out) and the next day with a free in-clinic time."""
    from datetime import timedelta

    c = await conn.fetchrow(
        "select closed_weekdays, exists (select 1 from app.clinic_holidays h where h.clinic_id = $1 "
        "and h.day = $2) holiday from app.clinics where id = $1",
        clinic_id,
        today,
    )
    if c is None:
        return {}
    dow = (today.weekday() + 1) % 7  # 0 = Sunday
    closed = c["holiday"] or dow in c["closed_weekdays"]
    out: dict[str, dict[str, object]] = {}
    for d in await conn.fetch(
        """select d.id::text id, d.name,
             exists (select 1 from app.doctor_leave l where l.doctor_id = d.id
                     and $2 between l.from_date and l.to_date) on_leave
           from app.doctors d where d.clinic_id = $1 and d.active""",
        clinic_id,
        today,
    ):
        hours = await conn.fetch(
            """select mode, to_char(start_time, 'HH24:MI') s, to_char(end_time, 'HH24:MI') e
               from app.doctor_availability where doctor_id = $1::uuid and weekday = $2
               order by start_time""",
            d["id"],
            dow,
        )
        free = await free_slots_range(
            conn, clinic_id, today, today + timedelta(days=days), "in_clinic", today, now_minutes, "", d["id"]
        )
        out[d["name"]] = {
            "in_clinic": []
            if closed or d["on_leave"]
            else [(h["s"], h["e"]) for h in hours if h["mode"] == "in_clinic"],
            "online": []
            if c["holiday"] or d["on_leave"]
            else [(h["s"], h["e"]) for h in hours if h["mode"] == "online"],
            "on_leave": d["on_leave"],
            "closed": closed,
            "times": free.get(today.isoformat(), []),
            "next": next((k for k in sorted(free) if k != today.isoformat()), None),
        }
    return out
