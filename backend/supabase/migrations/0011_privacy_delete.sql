-- 0011 Patient data deletion (DPDP Act 2023). One call removes a lead and everything about them,
-- including the personal details in the audit log, and records only that a deletion happened.
-- Allowed for a clinic manager of the lead's clinic or BB Admin (and the backend itself).

create function app.delete_patient_data(target uuid) returns text
language plpgsql security definer
set search_path = ''
as $$
declare
  l        app.leads%rowtype;
  ids      text[];
  patient  uuid;
begin
  select * into l from app.leads where id = target;
  if not found then
    raise exception 'lead % not found', target using errcode = 'no_data_found';
  end if;
  -- Signed-in users must manage this clinic; the backend (no signed-in user) may always do it.
  if auth.uid() is not null and not app.can_manage(l.clinic_id) then
    raise exception 'only a clinic manager can delete patient data' using errcode = 'insufficient_privilege';
  end if;

  -- Every row id about this person, to remove their audit history too.
  select array_agg(x) into ids from (
    select target::text as x
    union all select id::text from app.requests where lead_id = target
    union all select id::text from app.appointments where lead_id = target
    union all select id::text from app.tasks where lead_id = target
  ) s;

  -- Their patient record goes too, unless another lead still uses it.
  patient := l.patient_id;
  if patient is not null and exists (select 1 from app.leads where patient_id = patient and id <> target) then
    patient := null;
  end if;
  if patient is not null then
    ids := ids || patient::text;
  end if;

  -- The only way audit rows can be deleted: the switch, on for this transaction only.
  perform set_config('app.privacy_delete', 'on', true);
  delete from app.audit_log
  where table_name in ('leads', 'requests', 'appointments', 'tasks', 'patients') and row_id = any (ids);
  perform set_config('app.privacy_delete', '', true);

  -- Chat and questions are linked loosely (they survive a lead otherwise), so remove them first.
  delete from app.chat_sessions where lead_id = target;
  delete from app.unanswered_questions where lead_id = target;
  -- The lead; requests, appointments, tasks, timeline and outbox messages go with it.
  delete from app.leads where id = target;
  if patient is not null then
    delete from app.patients where id = patient;
  end if;

  -- What remains: that a deletion happened, by whom, for which lead code. No personal details.
  -- (Deleting the rows above added audit rows that hold only ids, no details.)
  insert into app.audit_log (clinic_id, table_name, row_id, action, actor, changed)
  values (l.clinic_id, 'privacy_request', l.lead_code, 'delete', auth.uid(),
          jsonb_build_object('reason', 'patient data deletion'));
  return l.lead_code;
end;
$$;

revoke all on function app.delete_patient_data(uuid) from public, anon;
grant execute on function app.delete_patient_data(uuid) to authenticated;
