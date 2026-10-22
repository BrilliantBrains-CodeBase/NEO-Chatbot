-- 0013 A short hold on a time while the patient checks the booking summary, so another patient
-- cannot take it in those minutes. Backend only (no grants); expired holds are ignored and cleared
-- by the backend on the next hold.
create table app.slot_holds (
  id          uuid primary key default gen_random_uuid(),
  clinic_id   text not null references app.clinics (id),
  doctor_id   uuid not null references app.doctors (id) on delete cascade,
  session_id  text not null check (session_id ~ '^s_[0-9a-f]{32}$'),
  slot        tstzrange not null check (not isempty(slot)),
  expires_at  timestamptz not null,
  created_at  timestamptz not null default now(),
  check (expires_at > created_at)
);
create index slot_holds_doctor on app.slot_holds (doctor_id, expires_at);
create index slot_holds_session on app.slot_holds (session_id);
alter table app.slot_holds enable row level security;
