-- 0006 Access rules for signed-in NEO CRM users (Postgres role "authenticated").
-- The backend runs every CRM query as the signed-in user (set local role authenticated + the user's id),
-- so these rules hold even if the API had a bug. The chatbot and system jobs run as the table owner.
-- anon (the publishable key without sign-in) still gets nothing. The "app" schema stays out of the
-- public Data API; Row Level Security limits every row.

-- ---------------------------------------------------------------------------------------------
-- Who am I? Helpers used by the policies. security definer so they can read roles without
-- depending on the caller's own row access; they only ever answer about auth.uid().
-- An inactive profile or an inactive role counts as no access.
-- ---------------------------------------------------------------------------------------------
create function app.is_bb_admin() returns boolean
language sql stable security definer
set search_path = ''
as $$
  select exists (
    select 1 from app.user_clinics uc join app.profiles p on p.id = uc.user_id
    where uc.user_id = auth.uid() and uc.role = 'bb_admin' and uc.active and p.active
  );
$$;

-- The caller's role in a clinic: 'bb_admin' everywhere for BB Admin, else their active role there, else null.
create function app.my_role(clinic text) returns text
language sql stable security definer
set search_path = ''
as $$
  select case
    when app.is_bb_admin() then 'bb_admin'
    else (
      select uc.role from app.user_clinics uc join app.profiles p on p.id = uc.user_id
      where uc.user_id = auth.uid() and uc.clinic_id = clinic and uc.active and p.active
    )
  end;
$$;

-- Clinic staff: everyone with a role there except doctors.
create function app.is_staff(clinic text) returns boolean
language sql stable security definer
set search_path = ''
as $$
  select coalesce(app.my_role(clinic) in ('bb_admin', 'clinic_manager', 'front_desk'), false);
$$;

create function app.can_manage(clinic text) returns boolean
language sql stable security definer
set search_path = ''
as $$
  select coalesce(app.my_role(clinic) in ('bb_admin', 'clinic_manager'), false);
$$;

-- The doctor records the caller is linked to, in clinics where they are an active doctor.
create function app.my_doctor_ids() returns setof uuid
language sql stable security definer
set search_path = ''
as $$
  select d.id from app.doctors d
  where d.user_id = auth.uid() and app.my_role(d.clinic_id) = 'doctor';
$$;

revoke all on function app.is_bb_admin(), app.my_role(text), app.is_staff(text), app.can_manage(text),
  app.my_doctor_ids() from public, anon;
grant execute on function app.is_bb_admin(), app.my_role(text), app.is_staff(text), app.can_manage(text),
  app.my_doctor_ids() to authenticated;

-- Triggers from earlier migrations that must see or change rows the signed-in user cannot:
-- the lead code counter (a clinic setting) and the doctor-login checks (all roles of the clinic).
-- They act only on the row being written, which the policies already allow.
alter function app.set_lead_code() security definer;
alter function app.check_doctor_login() security definer;
alter function app.keep_doctor_role() security definer;

-- Only managers and BB Admin may delete (soft-delete) a lead. Applies to signed-in users only;
-- the backend's own jobs (no signed-in user) are not limited by this.
create function app.guard_lead_delete() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.deleted_at is distinct from old.deleted_at and auth.uid() is not null
     and not app.can_manage(new.clinic_id) then
    raise exception 'only a clinic manager can delete or restore a lead' using errcode = 'insufficient_privilege';
  end if;
  return new;
end;
$$;
revoke all on function app.guard_lead_delete() from public, anon, authenticated;
create trigger leads_delete_guard before update of deleted_at on app.leads
  for each row execute function app.guard_lead_delete();

-- ---------------------------------------------------------------------------------------------
-- Grants: what signed-in users may do at all. Updates are limited to listed columns, so codes,
-- counters, sources and ids can never be changed from the CRM. Rows are then limited by the policies.
-- ---------------------------------------------------------------------------------------------
grant usage on schema app to authenticated;

grant select on app.clinics to authenticated;
grant update (name, bot_name, open_time, close_time, closed_weekdays, slot_minutes, last_slot_before_close_min,
  booking_window_days, booked_date_back_days, phone, whatsapp, website, allowed_origins, widget_config, active)
  on app.clinics to authenticated;

grant select on app.profiles to authenticated;
grant update (full_name, phone, last_seen_at) on app.profiles to authenticated;

grant select, insert, delete on app.user_clinics to authenticated;
grant update (role, in_round_robin, active) on app.user_clinics to authenticated;

grant select, insert on app.doctors to authenticated;
grant update (user_id, name, role_title, qualifications, profile, sort_order, active) on app.doctors to authenticated;

grant select, insert, delete on app.doctor_availability, app.doctor_leave to authenticated;
grant update (weekday, mode, start_time, end_time) on app.doctor_availability to authenticated;
grant update (from_date, to_date, reason) on app.doctor_leave to authenticated;

grant select, insert on app.patients to authenticated;
grant update (full_name, phone_e164, email, first_visit_at, notes) on app.patients to authenticated;

grant select, insert on app.leads to authenticated;
grant update (full_name, phone_e164, phone_cc, email, treatment, doctor_id, appointment_type, stage, stage_reason,
  assigned_to, verified, patient_id, notes, deleted_at) on app.leads to authenticated;

grant select, insert on app.requests to authenticated;
grant update (status) on app.requests to authenticated;

grant select, insert on app.appointments to authenticated;
grant update (doctor_id, type, slot, preferred_date, status, rescheduled_from_id, meet_link, confirmed_by, confirmed_at)
  on app.appointments to authenticated;

grant select, insert on app.tasks to authenticated;
grant update (title, due_at, assigned_to, status, outcome, completed_at) on app.tasks to authenticated;

grant select, insert on app.lead_events to authenticated;
grant usage on sequence app.lead_events_id_seq to authenticated;

grant select on app.chat_sessions, app.chat_messages to authenticated;

grant select on app.kb_documents, app.kb_chunks, app.unanswered_questions to authenticated;
grant update (status, approved_by, approved_at) on app.kb_documents to authenticated;
grant update (status) on app.kb_chunks to authenticated;
grant update (reviewed) on app.unanswered_questions to authenticated;

-- ---------------------------------------------------------------------------------------------
-- Policies: which rows. Each table: who may see, add, change or remove.
-- ---------------------------------------------------------------------------------------------
create policy clinics_read on app.clinics for select to authenticated using (app.my_role(id) is not null);
create policy clinics_edit on app.clinics for update to authenticated
  using (app.can_manage(id)) with check (app.can_manage(id));

-- Own profile, and the people of the clinics one works in (for assigning leads).
create policy profiles_read on app.profiles for select to authenticated using (
  id = auth.uid()
  or exists (select 1 from app.user_clinics uc where uc.user_id = profiles.id and app.my_role(uc.clinic_id) is not null)
);
create policy profiles_edit_own on app.profiles for update to authenticated
  using (id = auth.uid()) with check (id = auth.uid());

-- Team: managers manage their clinic's team; only BB Admin can create or change a BB Admin.
create policy team_read on app.user_clinics for select to authenticated using (app.my_role(clinic_id) is not null);
create policy team_add on app.user_clinics for insert to authenticated
  with check (app.can_manage(clinic_id) and (role <> 'bb_admin' or app.is_bb_admin()));
create policy team_edit on app.user_clinics for update to authenticated
  using (app.can_manage(clinic_id) and (role <> 'bb_admin' or app.is_bb_admin()))
  with check (app.can_manage(clinic_id) and (role <> 'bb_admin' or app.is_bb_admin()));
create policy team_remove on app.user_clinics for delete to authenticated
  using (app.can_manage(clinic_id) and (role <> 'bb_admin' or app.is_bb_admin()));

create policy doctors_read on app.doctors for select to authenticated using (app.my_role(clinic_id) is not null);
create policy doctors_add on app.doctors for insert to authenticated with check (app.can_manage(clinic_id));
create policy doctors_edit on app.doctors for update to authenticated
  using (app.can_manage(clinic_id)) with check (app.can_manage(clinic_id));

-- Doctor hours and leave: clinic staff, or the doctor for their own record.
create policy availability_read on app.doctor_availability for select to authenticated
  using (app.my_role(clinic_id) is not null);
create policy availability_add on app.doctor_availability for insert to authenticated
  with check (app.is_staff(clinic_id) or doctor_id in (select app.my_doctor_ids()));
create policy availability_edit on app.doctor_availability for update to authenticated
  using (app.is_staff(clinic_id) or doctor_id in (select app.my_doctor_ids()))
  with check (app.is_staff(clinic_id) or doctor_id in (select app.my_doctor_ids()));
create policy availability_remove on app.doctor_availability for delete to authenticated
  using (app.is_staff(clinic_id) or doctor_id in (select app.my_doctor_ids()));

create policy leave_read on app.doctor_leave for select to authenticated using (app.my_role(clinic_id) is not null);
create policy leave_add on app.doctor_leave for insert to authenticated
  with check (app.is_staff(clinic_id) or doctor_id in (select app.my_doctor_ids()));
create policy leave_edit on app.doctor_leave for update to authenticated
  using (app.is_staff(clinic_id) or doctor_id in (select app.my_doctor_ids()))
  with check (app.is_staff(clinic_id) or doctor_id in (select app.my_doctor_ids()));
create policy leave_remove on app.doctor_leave for delete to authenticated
  using (app.is_staff(clinic_id) or doctor_id in (select app.my_doctor_ids()));

-- Patient work: clinic staff only (not doctors).
create policy patients_all on app.patients for all to authenticated
  using (app.is_staff(clinic_id)) with check (app.is_staff(clinic_id));
create policy leads_all on app.leads for all to authenticated
  using (app.is_staff(clinic_id)) with check (app.is_staff(clinic_id));
create policy requests_all on app.requests for all to authenticated
  using (app.is_staff(clinic_id)) with check (app.is_staff(clinic_id));
create policy tasks_all on app.tasks for all to authenticated
  using (app.is_staff(clinic_id)) with check (app.is_staff(clinic_id));

-- Timeline: staff read it; a new entry must carry the writer's own id.
create policy events_read on app.lead_events for select to authenticated using (app.is_staff(clinic_id));
create policy events_add on app.lead_events for insert to authenticated
  with check (app.is_staff(clinic_id) and actor = auth.uid());

-- Appointments: staff; a doctor sees their own.
create policy appointments_read on app.appointments for select to authenticated
  using (app.is_staff(clinic_id) or doctor_id in (select app.my_doctor_ids()));
create policy appointments_add on app.appointments for insert to authenticated with check (app.is_staff(clinic_id));
create policy appointments_edit on app.appointments for update to authenticated
  using (app.is_staff(clinic_id)) with check (app.is_staff(clinic_id));

create policy chat_sessions_read on app.chat_sessions for select to authenticated using (app.is_staff(clinic_id));
create policy chat_messages_read on app.chat_messages for select to authenticated using (app.is_staff(clinic_id));

-- Knowledge base and unanswered questions: managers and BB Admin.
create policy kb_documents_read on app.kb_documents for select to authenticated using (app.can_manage(clinic_id));
create policy kb_documents_edit on app.kb_documents for update to authenticated
  using (app.can_manage(clinic_id)) with check (app.can_manage(clinic_id));
create policy kb_chunks_read on app.kb_chunks for select to authenticated using (app.can_manage(clinic_id));
create policy kb_chunks_edit on app.kb_chunks for update to authenticated
  using (app.can_manage(clinic_id)) with check (app.can_manage(clinic_id));
create policy unanswered_read on app.unanswered_questions for select to authenticated
  using (app.can_manage(clinic_id));
create policy unanswered_edit on app.unanswered_questions for update to authenticated
  using (app.can_manage(clinic_id)) with check (app.can_manage(clinic_id));
