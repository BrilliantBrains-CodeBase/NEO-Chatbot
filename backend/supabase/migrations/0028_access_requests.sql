-- 0028 Team & access: "Create an account" requests. The backend creates the person's login (Supabase Auth) and
-- profile with no clinic role, so they cannot use the CRM yet (sign-in says it is waiting), and a pending
-- request here. Approve: the role (it may be changed) becomes active for that clinic. Reject: the login is
-- removed. Only BB Admin approves Clinic Managers; a Clinic Manager or BB Admin approves Front Desk and Doctors.
create table app.access_requests (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid references app.profiles (id) on delete set null, -- null once a rejected login is removed
  clinic_id   text not null references app.clinics (id),
  role        text not null check (role in ('clinic_manager', 'front_desk', 'doctor')),
  full_name   text not null check (length(trim(full_name)) between 2 and 100),
  email       text not null check (email = lower(email)),
  phone       text check (phone ~ '^\+[1-9][0-9]{6,14}$'),
  status      text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
  decided_by  uuid references app.profiles (id) on delete set null,
  decided_at  timestamptz,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  check ((status = 'pending') = (decided_at is null))
);
create unique index access_requests_one_pending on app.access_requests (email, clinic_id) where status = 'pending';
create index access_requests_clinic on app.access_requests (clinic_id, status, created_at desc);

-- CRM: managers of the clinic read; changes go through the backend.
alter table app.access_requests enable row level security;
grant select on app.access_requests to authenticated;
create policy access_requests_read on app.access_requests for select to authenticated
  using (app.can_manage(clinic_id));
create trigger access_requests_audit after insert or update or delete on app.access_requests
  for each row execute function app.audit_row();
create trigger access_requests_touch before update on app.access_requests
  for each row execute function app.touch_updated_at();
