-- 0030 Email through Gmail: each clinic connects its own Gmail (Integrations → Email), and BB connects one Gmail
-- (Login & security) for BB Admin login codes and as the fallback. Gmail address + Google App password; the
-- password is kept in Supabase Vault (only its id here). Every email sent (or refused) is logged.
create table app.email_senders (
  id            uuid primary key default gen_random_uuid(),
  clinic_id     text references app.clinics (id), -- null: the BB Gmail
  address       text not null check (address = lower(address) and address ~ '^[^@\s]+@[^@\s]+\.[^@\s]{2,}$'),
  from_name     text not null default '' check (length(from_name) <= 80), -- e.g. "Neo Follicle"
  secret        uuid not null,                     -- vault.secrets id of the App password
  connected_by  uuid references app.profiles (id) on delete set null,
  connected_at  timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create unique index email_senders_one on app.email_senders (coalesce(clinic_id, 'BB'));

create table app.email_log (
  id         bigint generated always as identity primary key,
  clinic_id  text references app.clinics (id),  -- null: sent from the BB Gmail
  to_email   text not null,
  kind       text not null,                     -- test, login_code, ...
  ok         boolean not null,
  error      text check (length(error) <= 500),
  at         timestamptz not null default now()
);
create index email_log_recent on app.email_log (clinic_id, at desc);

-- CRM: managers read their clinic's rows, BB Admin also the BB Gmail's; changes go through the backend.
alter table app.email_senders enable row level security;
alter table app.email_log enable row level security;
grant select on app.email_senders, app.email_log to authenticated;
create policy email_senders_read on app.email_senders for select to authenticated
  using (case when clinic_id is null then app.is_bb_admin() else app.can_manage(clinic_id) end);
create policy email_log_read on app.email_log for select to authenticated
  using (case when clinic_id is null then app.is_bb_admin() else app.can_manage(clinic_id) end);
create trigger email_senders_audit after insert or update or delete on app.email_senders
  for each row execute function app.audit_row();
create trigger email_senders_touch before update on app.email_senders
  for each row execute function app.touch_updated_at();
