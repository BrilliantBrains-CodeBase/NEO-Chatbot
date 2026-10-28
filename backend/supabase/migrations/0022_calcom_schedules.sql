-- 0022 Cal.com setup from the Dashboard: for each doctor who does online consults we create, in the clinic's
-- Cal.com, a schedule (the doctor's online hours from the CRM, with holidays and leave blocked) and an event
-- (the consult, with Google Meet). Both ids are kept here; the consult length is the event's length.
alter table app.calcom_doctors
  add column schedule_id bigint check (schedule_id > 0),
  add column consult_minutes smallint not null default 30 check (consult_minutes in (15, 30, 45, 60)),
  add column synced_at timestamptz; -- the last time the hours and holidays were sent to Cal.com
