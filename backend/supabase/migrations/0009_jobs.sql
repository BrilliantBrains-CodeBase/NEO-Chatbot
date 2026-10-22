-- 0009 Scheduled jobs (pg_cron). Each job is a plain function, so it can be tested and run by hand;
-- pg_cron runs them on schedule. pg_cron uses UTC: 03:00 India time is 21:30 UTC the day before.
-- Only the owner runs them; nothing is granted to anon or authenticated.

create extension if not exists pg_cron;

-- Chat is short memory (client decision): messages older than 21 days go, and sessions with no
-- activity for 21 days go with their messages. Leads keep their requests and questions.
create function app.job_delete_old_chat() returns integer
language plpgsql
set search_path = ''
as $$
declare
  n integer;
begin
  delete from app.chat_messages where created_at < now() - interval '21 days';
  get diagnostics n = row_count;
  delete from app.chat_sessions where last_at < now() - interval '21 days';
  return n;
end;
$$;

-- A pending booking whose time has passed without staff confirming it becomes Missed. An "Any time"
-- request becomes Missed once its day is over in the clinic's time zone.
create function app.job_mark_missed() returns integer
language plpgsql
set search_path = ''
as $$
declare
  n integer;
begin
  update app.appointments a set status = 'missed'
  from app.clinics c
  where c.id = a.clinic_id
    and a.status = 'pending'
    and (
      (a.slot is not null and lower(a.slot) <= now())
      or (a.slot is null and a.preferred_date < (now() at time zone c.timezone)::date)
    );
  get diagnostics n = row_count;
  return n;
end;
$$;

-- Unanswered questions are kept 90 days with their lead, then unlinked so no one can be identified.
create function app.job_unlink_unanswered() returns integer
language plpgsql
set search_path = ''
as $$
declare
  n integer;
begin
  update app.unanswered_questions set lead_id = null, session_id = null
  where created_at < now() - interval '90 days' and (lead_id is not null or session_id is not null);
  get diagnostics n = row_count;
  return n;
end;
$$;

-- Sent and cancelled messages are removed after 30 days; failed ones stay for staff to see.
create function app.job_clear_outbox() returns integer
language plpgsql
set search_path = ''
as $$
declare
  n integer;
begin
  delete from app.outbox where status in ('sent', 'cancelled') and updated_at < now() - interval '30 days';
  get diagnostics n = row_count;
  return n;
end;
$$;

revoke all on function app.job_delete_old_chat(), app.job_mark_missed(), app.job_unlink_unanswered(),
  app.job_clear_outbox() from public, anon, authenticated;

-- Schedules (UTC). cron.schedule with a name replaces an existing job of that name.
select cron.schedule('neo_delete_old_chat', '30 21 * * *', 'select app.job_delete_old_chat()');
select cron.schedule('neo_mark_missed', '*/15 * * * *', 'select app.job_mark_missed()');
select cron.schedule('neo_unlink_unanswered', '45 21 * * *', 'select app.job_unlink_unanswered()');
select cron.schedule('neo_clear_outbox', '0 22 * * *', 'select app.job_clear_outbox()');
