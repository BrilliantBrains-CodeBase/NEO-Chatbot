-- 0035 Slot lengths the clinic chooses (user, 2026-10-31): a clinic default for in-clinic visits (slot_minutes,
-- already there) and a NEW one for online consults; each doctor may use a different length, separately for
-- in-clinic and online (empty = the clinic's). 5 and 10 minutes are allowed. A booking keeps its own length
-- in appointments.slot, so a 30-minute online consult blocks all 30 minutes in both kinds of visit.

alter table app.clinics
  add column online_slot_minutes smallint not null default 30
    check (online_slot_minutes in (5, 10, 15, 20, 30, 45, 60));

alter table app.doctors
  add column in_clinic_minutes smallint check (in_clinic_minutes in (5, 10, 15, 20, 30, 45, 60)),
  add column online_minutes smallint check (online_minutes in (5, 10, 15, 20, 30, 45, 60));

-- Cal.com's event length follows the doctor's online length, so it takes the same choices.
alter table app.calcom_doctors drop constraint calcom_doctors_consult_minutes_check;
alter table app.calcom_doctors
  add constraint calcom_doctors_consult_minutes_check
    check (consult_minutes in (5, 10, 15, 20, 30, 45, 60));

-- Today's online length per doctor was the Cal.com event's: keep it.
update app.doctors d
   set online_minutes = c.consult_minutes
  from app.calcom_doctors c
 where c.doctor_id = d.id;

grant update (online_slot_minutes) on app.clinics to authenticated;
grant update (in_clinic_minutes, online_minutes) on app.doctors to authenticated;
