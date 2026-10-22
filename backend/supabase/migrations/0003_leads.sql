-- 0003 Leads and work: leads (one place for all clinics, codes like CL01-00001), patients, requests,
-- appointments (no double booking), tasks and the lead timeline.
-- Every child row references (id, clinic_id) of its parent, so nothing can point across clinics.
-- Row Level Security on everywhere; nothing granted to anon or authenticated (0001).

-- ---------------------------------------------------------------------------------------------
-- Patients: created when a lead reaches Visited.
-- ---------------------------------------------------------------------------------------------
create table app.patients (
  id             uuid primary key default gen_random_uuid(),
  clinic_id      text not null references app.clinics (id),
  full_name      text not null check (length(trim(full_name)) between 2 and 100),
  phone_e164     text check (phone_e164 ~ '^\+[1-9][0-9]{6,14}$'),
  email          text check (email = lower(email) and email ~ '^[^@\s]+@[^@\s]+\.[^@\s]{2,}$'),
  first_visit_at timestamptz,
  notes          text not null default '',
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  unique (id, clinic_id),
  check (phone_e164 is not null or email is not null)
);

create unique index patients_phone on app.patients (clinic_id, phone_e164) where phone_e164 is not null;

-- ---------------------------------------------------------------------------------------------
-- Leads: every clinic in one table, tagged by clinic_id, with a readable code CLxx-00001.
-- ---------------------------------------------------------------------------------------------
create table app.leads (
  id               uuid primary key default gen_random_uuid(),
  lead_code        text not null unique, -- set by trigger, never changes
  clinic_id        text not null references app.clinics (id),
  full_name        text not null check (length(trim(full_name)) between 2 and 100),
  phone_e164       text check (phone_e164 ~ '^\+[1-9][0-9]{6,14}$'),
  phone_cc         text check (phone_cc ~ '^\+[1-9][0-9]{0,3}$'),
  email            text check (email = lower(email) and email ~ '^[^@\s]+@[^@\s]+\.[^@\s]{2,}$'),
  source           text not null check (source in ('chatbot', 'meta_ads', 'google_ads', 'manual', 'whatsapp')),
  campaign         text,
  treatment        text,
  doctor_id        uuid,
  appointment_type text check (appointment_type in ('in_clinic', 'online')),
  stage            text not null default 'new'
                     check (stage in ('new', 'follow_up', 'booked', 'visited', 'lost', 'invalid')),
  stage_reason     text,
  assigned_to      uuid,
  contact_count    integer not null default 1 check (contact_count >= 1),
  first_contact_at timestamptz not null default now(),
  last_contact_at  timestamptz not null default now(),
  page_url         text,
  device           text check (device in ('mobile', 'desktop')),
  consent_at       timestamptz,
  verified         boolean not null default false,
  patient_id       uuid,
  notes            text not null default '',
  deleted_at       timestamptz,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  unique (id, clinic_id),
  check (phone_e164 is not null or email is not null),
  check (last_contact_at >= first_contact_at),
  -- Lost and Invalid need a reason from the fixed lists; other stages carry none.
  check (
    (stage = 'lost' and stage_reason in ('not_reachable', 'not_interested', 'price', 'chose_another_clinic', 'other'))
    or (stage = 'invalid' and stage_reason in ('wrong_number', 'spam', 'duplicate', 'test'))
    or (stage not in ('lost', 'invalid') and stage_reason is null)
  ),
  foreign key (doctor_id, clinic_id) references app.doctors (id, clinic_id) on delete set null (doctor_id),
  foreign key (assigned_to, clinic_id) references app.user_clinics (user_id, clinic_id) on delete set null (assigned_to),
  foreign key (patient_id, clinic_id) references app.patients (id, clinic_id) on delete set null (patient_id)
);

-- One lead per person per clinic: by phone, or by email when there is no phone.
create unique index leads_phone on app.leads (clinic_id, phone_e164)
  where deleted_at is null and phone_e164 is not null;
create unique index leads_email_only on app.leads (clinic_id, email)
  where deleted_at is null and phone_e164 is null;

create index leads_list on app.leads (clinic_id, stage, last_contact_at desc) where deleted_at is null;
create index leads_mine on app.leads (clinic_id, assigned_to, stage) where deleted_at is null;
create index leads_email on app.leads (clinic_id, email) where email is not null;
create index leads_name on app.leads using gin (full_name extensions.gin_trgm_ops);

-- Lead code: clinic code + the clinic's next number. The UPDATE locks the clinic row, so two leads
-- created at the same moment wait for each other and never get the same number.
create function app.set_lead_code() returns trigger
language plpgsql
set search_path = ''
as $$
declare
  n integer;
begin
  update app.clinics set next_lead_no = next_lead_no + 1
  where id = new.clinic_id
  returning next_lead_no - 1 into n;
  if n is null then
    raise exception 'unknown clinic %', new.clinic_id using errcode = 'foreign_key_violation';
  end if;
  if n > 99999 then
    raise exception 'lead numbers for clinic % are used up', new.clinic_id using errcode = 'check_violation';
  end if;
  new.lead_code := new.clinic_id || '-' || lpad(n::text, 5, '0');
  return new;
end;
$$;

-- A lead never changes its code or its clinic.
create function app.keep_lead_identity() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.lead_code is distinct from old.lead_code or new.clinic_id is distinct from old.clinic_id then
    raise exception 'lead code and clinic cannot be changed' using errcode = 'check_violation';
  end if;
  return new;
end;
$$;

create trigger leads_code before insert on app.leads for each row execute function app.set_lead_code();
create trigger leads_identity before update on app.leads for each row execute function app.keep_lead_identity();

-- ---------------------------------------------------------------------------------------------
-- Requests: each chatbot or staff request (booking, online, cancel, reschedule, callback, question).
-- ---------------------------------------------------------------------------------------------
create table app.requests (
  id                     uuid primary key default gen_random_uuid(),
  clinic_id              text not null references app.clinics (id),
  lead_id                uuid not null,
  type                   text not null check (type in ('book', 'online', 'cancel', 'reschedule', 'callback', 'question')),
  status                 text not null default 'pending' check (status in ('pending', 'done', 'rejected')),
  data                   jsonb not null default '{}'::jsonb check (jsonb_typeof(data) = 'object'),
  match_status           text check (match_status in ('matched', 'no_match')),
  matched_appointment_id uuid,
  question_text          text,
  session_id             text,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),
  unique (id, clinic_id),
  -- Only cancel and reschedule are matched to an existing booking.
  check (type in ('cancel', 'reschedule') or (match_status is null and matched_appointment_id is null)),
  check (matched_appointment_id is null or match_status = 'matched'),
  foreign key (lead_id, clinic_id) references app.leads (id, clinic_id) on delete cascade
);

create index requests_inbox on app.requests (clinic_id, type, status, created_at desc);
create index requests_lead on app.requests (lead_id);

-- ---------------------------------------------------------------------------------------------
-- Appointments. The database refuses two pending or confirmed appointments for the same doctor at
-- overlapping times; cancelled, rejected or missed ones free the slot.
-- ---------------------------------------------------------------------------------------------
create table app.appointments (
  id                  uuid primary key default gen_random_uuid(),
  clinic_id           text not null references app.clinics (id),
  lead_id             uuid not null,
  request_id          uuid,
  doctor_id           uuid,
  type                text not null check (type in ('in_clinic', 'online')),
  slot                tstzrange, -- [start, end); null when the patient chose "Any time"
  preferred_date      date,      -- the day, when no exact slot was chosen
  status              text not null default 'pending'
                        check (status in ('pending', 'confirmed', 'rejected', 'cancelled', 'rescheduled',
                                          'visited', 'no_show', 'missed')),
  rescheduled_from_id uuid,
  meet_link           text check (meet_link ~ '^https://meet\.google\.com/'),
  calendar_event_id   text,
  confirmed_by        uuid references app.profiles (id) on delete set null,
  confirmed_at        timestamptz,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  unique (id, clinic_id),
  check (slot is not null or preferred_date is not null),
  check (slot is null or (not isempty(slot) and lower_inc(slot) and not upper_inc(slot)
                          and not lower_inf(slot) and not upper_inf(slot))),
  check (status not in ('confirmed', 'visited', 'no_show') or confirmed_at is not null),
  check (meet_link is null or type = 'online'),
  foreign key (lead_id, clinic_id) references app.leads (id, clinic_id) on delete cascade,
  foreign key (request_id, clinic_id) references app.requests (id, clinic_id) on delete set null (request_id),
  foreign key (doctor_id, clinic_id) references app.doctors (id, clinic_id),
  foreign key (rescheduled_from_id, clinic_id) references app.appointments (id, clinic_id)
    on delete set null (rescheduled_from_id),
  exclude using gist (doctor_id with =, slot with &&)
    where (status in ('pending', 'confirmed') and doctor_id is not null and slot is not null)
);

create index appointments_calendar on app.appointments (clinic_id, doctor_id, lower(slot));
create index appointments_queue on app.appointments (clinic_id, status, lower(slot));
create index appointments_lead on app.appointments (lead_id);

-- A cancel or reschedule request matched to a booking points to it (same clinic).
alter table app.requests
  add foreign key (matched_appointment_id, clinic_id) references app.appointments (id, clinic_id)
    on delete set null (matched_appointment_id);

-- ---------------------------------------------------------------------------------------------
-- Tasks: call deadlines and retries (up to 3 tries), booking confirmation, custom tasks.
-- ---------------------------------------------------------------------------------------------
create table app.tasks (
  id             uuid primary key default gen_random_uuid(),
  clinic_id      text not null references app.clinics (id),
  lead_id        uuid not null,
  appointment_id uuid,
  type           text not null check (type in ('call_new_lead', 'retry_call', 'confirm_booking', 'custom')),
  title          text not null default '',
  due_at         timestamptz not null,
  assigned_to    uuid,
  status         text not null default 'open' check (status in ('open', 'done', 'cancelled')),
  attempt        smallint not null default 1 check (attempt between 1 and 3),
  outcome        text check (outcome in ('answered', 'no_answer', 'busy', 'wrong_number')),
  escalated_at   timestamptz,
  completed_at   timestamptz,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  check (attempt = 1 or type = 'retry_call'),
  check (outcome is null or type in ('call_new_lead', 'retry_call')),
  check ((status = 'done') = (completed_at is not null)),
  check (status <> 'done' or type not in ('call_new_lead', 'retry_call') or outcome is not null),
  check (type <> 'custom' or length(trim(title)) > 0),
  foreign key (lead_id, clinic_id) references app.leads (id, clinic_id) on delete cascade,
  foreign key (appointment_id, clinic_id) references app.appointments (id, clinic_id) on delete cascade,
  foreign key (assigned_to, clinic_id) references app.user_clinics (user_id, clinic_id) on delete set null (assigned_to)
);

create index tasks_mine on app.tasks (clinic_id, assigned_to, status, due_at);
create index tasks_due on app.tasks (status, due_at) where status = 'open';

-- ---------------------------------------------------------------------------------------------
-- Lead timeline. Rows are only added; they are never edited. Deleting is allowed only for a
-- patient data deletion request (with the lead).
-- ---------------------------------------------------------------------------------------------
create table app.lead_events (
  id         bigint generated always as identity primary key,
  clinic_id  text not null references app.clinics (id),
  lead_id    uuid not null,
  kind       text not null check (kind in ('contact', 'stage_change', 'assigned', 'call', 'note', 'request', 'appointment')),
  data       jsonb not null default '{}'::jsonb check (jsonb_typeof(data) = 'object'),
  actor      uuid references app.profiles (id) on delete set null, -- null: the chatbot or the system
  created_at timestamptz not null default now(),
  foreign key (lead_id, clinic_id) references app.leads (id, clinic_id) on delete cascade
);

create index lead_events_lead on app.lead_events (lead_id, created_at);

create function app.no_update() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception '% rows cannot be changed', tg_table_name using errcode = 'check_violation';
end;
$$;

create trigger lead_events_append_only before update on app.lead_events
  for each row execute function app.no_update();

revoke all on function app.set_lead_code() from public, anon, authenticated;
revoke all on function app.keep_lead_identity() from public, anon, authenticated;
revoke all on function app.no_update() from public, anon, authenticated;

-- updated_at
create trigger patients_touch before update on app.patients for each row execute function app.touch_updated_at();
create trigger leads_touch before update on app.leads for each row execute function app.touch_updated_at();
create trigger requests_touch before update on app.requests for each row execute function app.touch_updated_at();
create trigger appointments_touch before update on app.appointments for each row execute function app.touch_updated_at();
create trigger tasks_touch before update on app.tasks for each row execute function app.touch_updated_at();

alter table app.patients enable row level security;
alter table app.leads enable row level security;
alter table app.requests enable row level security;
alter table app.appointments enable row level security;
alter table app.tasks enable row level security;
alter table app.lead_events enable row level security;
