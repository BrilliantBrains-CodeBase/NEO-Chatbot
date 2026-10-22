"""Free appointment slots, from the database: clinic hours, closed weekdays and holidays, doctor
availability and leave, and the appointments already pending or confirmed. A time is offered only if
at least one doctor is free. One query covers the whole booking window.
"""

from datetime import date
from typing import Literal

import asyncpg

Mode = Literal["in_clinic", "online"]

# Slot starts run from the later of clinic opening and the doctor's start, to the earlier of
# (doctor end - slot length) and (clinic closing - last slot gap). Times are the clinic's local time;
# appointments are compared in real time (timestamptz) through the clinic's time zone.
FREE_SLOTS = """
with c as (
  select * from app.clinics where id = $1 and active
),
days as (
  select gs::date as day from c, generate_series($2::date, $3::date, interval '1 day') gs
  where not (extract(dow from gs)::smallint = any (c.closed_weekdays))
    and not exists (select 1 from app.clinic_holidays h where h.clinic_id = $1 and h.day = gs::date)
),
d as (
  select days.day, da.doctor_id, da.start_time, da.end_time
  from days
  join app.doctor_availability da
    on da.clinic_id = $1 and da.mode = $4 and da.weekday = extract(dow from days.day)::smallint
  join app.doctors doc on doc.id = da.doctor_id and doc.active
  where not exists (
    select 1 from app.doctor_leave l
    where l.doctor_id = da.doctor_id and days.day between l.from_date and l.to_date
  )
),
s as (
  select d.day, d.doctor_id, gs::time as t
  from d, c,
  generate_series(
    d.day + greatest(d.start_time, c.open_time),
    d.day + least(d.end_time - make_interval(mins => c.slot_minutes),
                  c.close_time - make_interval(mins => c.last_slot_before_close_min)),
    make_interval(mins => c.slot_minutes)
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
      (s.day + s.t + make_interval(mins => c.slot_minutes)) at time zone c.timezone,
      '[)'
    )
)
and not exists (  -- held for another patient who is checking the summary
  select 1 from app.slot_holds h
  where h.doctor_id = s.doctor_id and h.expires_at > now() and h.session_id <> $5
    and h.slot && tstzrange(
      (s.day + s.t) at time zone c.timezone,
      (s.day + s.t + make_interval(mins => c.slot_minutes)) at time zone c.timezone,
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
) -> dict[str, list[str]]:
    """Free HH:MM slot starts per day (YYYY-MM-DD). Days without a free slot are left out; for today,
    past times are removed. The session's own hold does not hide its time."""
    out: dict[str, list[str]] = {}
    for r in await conn.fetch(FREE_SLOTS, clinic_id, first, last, mode, session_id):
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
