-- 0025 Dashboard → Integrations → WhatsApp (Interakt): each clinic's own Interakt account (its API key in Supabase
-- Vault, only the id here) and, for each message the CRM sends, the clinic's approved WhatsApp template.
create table app.whatsapp_accounts (
  id            uuid not null unique default gen_random_uuid(), -- the change log names rows by id
  clinic_id     text primary key references app.clinics (id),
  key_secret    uuid not null,  -- vault.secrets id of the Interakt API key
  -- purpose -> {"name": approved template name, "language": e.g. "en"}; purposes: request_received,
  -- appointment_confirmed, reminder, otp
  templates     jsonb not null default '{}'::jsonb check (jsonb_typeof(templates) = 'object'),
  connected_by  uuid references app.profiles (id) on delete set null,
  connected_at  timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

-- Every WhatsApp message sent (or refused), for staff.
create table app.whatsapp_log (
  id          bigint generated always as identity primary key,
  clinic_id   text not null references app.clinics (id),
  purpose     text not null,
  to_phone    text not null,
  ok          boolean not null,
  error       text check (length(error) <= 500),
  lead_id     uuid,
  at          timestamptz not null default now()
);
create index whatsapp_log_recent on app.whatsapp_log (clinic_id, at desc);

alter table app.whatsapp_accounts enable row level security;
alter table app.whatsapp_log enable row level security;
grant select on app.whatsapp_accounts, app.whatsapp_log to authenticated;
create policy whatsapp_accounts_read on app.whatsapp_accounts for select to authenticated
  using (app.can_manage(clinic_id));
create policy whatsapp_log_read on app.whatsapp_log for select to authenticated using (app.can_manage(clinic_id));
create trigger whatsapp_accounts_audit after insert or update or delete on app.whatsapp_accounts
  for each row execute function app.audit_row();
create trigger whatsapp_accounts_touch before update on app.whatsapp_accounts
  for each row execute function app.touch_updated_at();
