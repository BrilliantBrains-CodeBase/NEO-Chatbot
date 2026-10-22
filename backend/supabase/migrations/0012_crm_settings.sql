-- 0012 From the approved CRM design: clinic holidays, more lead sources, how new leads are assigned,
-- notification settings, the CRM's lost reason wording, and the audit log kept for 1 year.

-- Holidays: the clinic is closed on these dates (no slots in the chatbot or the CRM).
create table app.clinic_holidays (
  id         uuid primary key default gen_random_uuid(),
  clinic_id  text not null references app.clinics (id),
  day        date not null,
  reason     text not null default '' check (length(reason) <= 200),
  created_at timestamptz not null default now(),
  unique (clinic_id, day)
);
alter table app.clinic_holidays enable row level security;
grant select, insert, delete on app.clinic_holidays to authenticated;
create policy holidays_read on app.clinic_holidays for select to authenticated using (app.my_role(clinic_id) is not null);
create policy holidays_add on app.clinic_holidays for insert to authenticated with check (app.can_manage(clinic_id));
create policy holidays_remove on app.clinic_holidays for delete to authenticated using (app.can_manage(clinic_id));
create trigger clinic_holidays_audit after insert or update or delete on app.clinic_holidays
  for each row execute function app.audit_row();

-- Lead sources from the CRM's Add lead form.
alter table app.leads drop constraint leads_source_check;
alter table app.leads add constraint leads_source_check check (
  source in ('chatbot', 'meta_ads', 'google_ads', 'manual', 'whatsapp', 'walk_in', 'phone_call', 'referral')
);

-- Lost reasons as the CRM words them ("No response after 3 tries" instead of "not reachable").
alter table app.leads drop constraint leads_stage_reason;
alter table app.leads add constraint leads_stage_reason check (
  (stage = 'lost' and stage_reason is not null
     and stage_reason in ('price', 'chose_another_clinic', 'not_interested', 'no_response', 'other'))
  or (stage = 'invalid' and stage_reason is not null
     and stage_reason in ('wrong_number', 'duplicate', 'spam', 'test'))
  or (stage not in ('lost', 'invalid') and stage_reason is null)
);

-- Per clinic: how new leads are assigned, and which notifications are on.
alter table app.clinics
  add column lead_assignment text not null default 'round_robin'
    check (lead_assignment in ('round_robin', 'manual', 'manager')),
  add column notifications jsonb not null default
    '{"new_lead_whatsapp": true, "callback_wait_alert": true, "daily_summary": true, "inbox_digest": true}'::jsonb
    check (jsonb_typeof(notifications) = 'object');
grant update (lead_assignment, notifications) on app.clinics to authenticated;

-- The audit log is kept for 1 year (CRM design). The only other way rows leave is a patient data deletion.
create function app.job_trim_audit_log() returns integer
language plpgsql
set search_path = ''
as $$
declare
  n integer;
begin
  perform set_config('app.privacy_delete', 'on', true);
  delete from app.audit_log where at < now() - interval '1 year';
  get diagnostics n = row_count;
  perform set_config('app.privacy_delete', '', true);
  return n;
end;
$$;
revoke all on function app.job_trim_audit_log() from public, anon, authenticated;
select cron.schedule('neo_trim_audit_log', '15 22 * * *', 'select app.job_trim_audit_log()');
