-- 0007 Audit log: who changed what and when, written by the database itself (so nothing can skip it),
-- never edited, never deleted (except through a patient data deletion, which turns on a switch).
-- Readable by BB Admin, and by a clinic manager for their own clinic.

create table app.audit_log (
  id         bigint generated always as identity primary key,
  clinic_id  text,          -- the clinic the row belongs to
  table_name text not null,
  row_id     text not null,
  action     text not null check (action in ('insert', 'update', 'delete', 'export')),
  actor      uuid,          -- the signed-in CRM user; null when the chatbot or a system job did it
  changed    jsonb not null default '{}'::jsonb check (jsonb_typeof(changed) = 'object'), -- {"column": [old, new]}
  at         timestamptz not null default now()
);

create index audit_log_clinic on app.audit_log (clinic_id, at desc);
create index audit_log_row on app.audit_log (table_name, row_id);

-- One audit row per change. For updates only the changed columns are kept (updated_at is ignored);
-- an update that changes nothing writes nothing. security definer: it writes even though users cannot.
create function app.audit_row() returns trigger
language plpgsql security definer
set search_path = ''
as $$
declare
  r      jsonb := to_jsonb(coalesce(new, old));
  diff   jsonb := '{}'::jsonb;
  clinic text := case when tg_table_name = 'clinics' then r ->> 'id' else r ->> 'clinic_id' end;
begin
  if tg_op = 'UPDATE' then
    select coalesce(jsonb_object_agg(n.key, jsonb_build_array(o.value, n.value)), '{}'::jsonb) into diff
    from jsonb_each(to_jsonb(new)) n
    join jsonb_each(to_jsonb(old)) o using (key)
    where n.value is distinct from o.value and n.key <> 'updated_at';
    if diff = '{}'::jsonb then
      return null;
    end if;
  end if;
  insert into app.audit_log (clinic_id, table_name, row_id, action, actor, changed)
  values (
    clinic,
    tg_table_name,
    coalesce(r ->> 'id', (r ->> 'user_id') || ':' || (r ->> 'clinic_id')),
    lower(tg_op),
    auth.uid(),
    diff
  );
  return null;
end;
$$;

-- The log itself: never edited; deleted only during a patient data deletion (switch set in that transaction).
create function app.protect_audit_log() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'DELETE' and current_setting('app.privacy_delete', true) = 'on' then
    return old;
  end if;
  raise exception 'audit log rows cannot be changed or deleted' using errcode = 'insufficient_privilege';
end;
$$;

revoke all on function app.audit_row(), app.protect_audit_log() from public, anon, authenticated;

create trigger audit_log_protect before update or delete on app.audit_log
  for each row execute function app.protect_audit_log();

-- Audited tables: settings, team, doctors and their hours, patients and all lead work, KB approvals.
-- (lead_events is itself a log; chat and KB chunks are high volume and not staff decisions.)
do $$
declare
  t text;
begin
  foreach t in array array['clinics', 'user_clinics', 'doctors', 'doctor_availability', 'doctor_leave', 'patients',
                           'leads', 'requests', 'appointments', 'tasks', 'kb_documents'] loop
    execute format(
      'create trigger %I after insert or update or delete on app.%I for each row execute function app.audit_row()',
      t || '_audit', t);
  end loop;
end;
$$;

alter table app.audit_log enable row level security;
grant select on app.audit_log to authenticated;
create policy audit_read on app.audit_log for select to authenticated
  using (app.is_bb_admin() or (clinic_id is not null and app.can_manage(clinic_id)));
