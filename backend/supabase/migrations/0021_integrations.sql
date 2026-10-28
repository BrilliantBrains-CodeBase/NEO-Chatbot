-- 0021 Dashboard → Integrations: each clinic's own Cal.com account (online consults, one event per doctor) and
-- its Google Sheets of leads (tabs, column mapping). Secrets (the Cal.com API key, the Cal.com webhook secret,
-- each sheet's secret) are never in these tables: they are in Supabase Vault (vault.secrets), encrypted with a
-- key Supabase keeps outside the database; the tables hold only the Vault id. Only the backend reads them.
-- New tables only: nothing existing changes (today's Cal.com key in .env keeps working until a clinic connects).

create table app.calcom_accounts (
  id                uuid not null unique default gen_random_uuid(), -- the change log names rows by id
  clinic_id         text primary key references app.clinics (id),
  key_secret        uuid not null,       -- vault.secrets id of the API key
  webhook_id        text,                -- the webhook we created in the clinic's Cal.com
  webhook_secret    uuid,                -- vault.secrets id of that webhook's signing secret
  account_name      text not null default '' check (length(account_name) <= 120), -- shown to staff
  connected_by      uuid references app.profiles (id) on delete set null,
  connected_at      timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

-- One Cal.com event = one doctor (online consults).
create table app.calcom_doctors (
  id             uuid primary key default gen_random_uuid(),
  clinic_id      text not null references app.calcom_accounts (clinic_id) on delete cascade,
  doctor_id      uuid not null,
  event_type_id  bigint not null check (event_type_id > 0),
  event_title    text not null default '' check (length(event_title) <= 200),
  created_at     timestamptz not null default now(),
  foreign key (doctor_id, clinic_id) references app.doctors (id, clinic_id) on delete cascade,
  unique (clinic_id, doctor_id),
  unique (clinic_id, event_type_id)
);

-- A Google Sheet of leads: its own secret (in Vault) and link; the tabs the Apps Script reported.
create table app.lead_sheets (
  id            uuid primary key default gen_random_uuid(),
  clinic_id     text not null references app.clinics (id),
  name          text not null check (length(trim(name)) between 1 and 80),
  secret        uuid not null,          -- vault.secrets id of this sheet's secret
  last_seen_at  timestamptz,            -- the Apps Script last reported in
  created_by    uuid references app.profiles (id) on delete set null,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (clinic_id, name)
);

-- Each tab: its column headers (as the sheet has them), whether it is on, and sheet column -> our field.
create table app.lead_sheet_tabs (
  id          uuid primary key default gen_random_uuid(),
  sheet_id    uuid not null references app.lead_sheets (id) on delete cascade,
  clinic_id   text not null references app.clinics (id),
  tab         text not null check (length(tab) between 1 and 100),
  headers     text[] not null default '{}' check (cardinality(headers) <= 100),
  active      boolean not null default false,
  mapping     jsonb not null default '{}'::jsonb check (jsonb_typeof(mapping) = 'object'),
  date_order  text check (date_order in ('dmy', 'mdy')), -- how this tab writes dates (null: worked out)
  updated_at  timestamptz not null default now(),
  unique (sheet_id, tab)
);

-- CRM: managers of the clinic read; changes go through the backend. Vault stays closed to the browser.
alter table app.calcom_accounts enable row level security;
alter table app.calcom_doctors enable row level security;
alter table app.lead_sheets enable row level security;
alter table app.lead_sheet_tabs enable row level security;
grant select on app.calcom_accounts, app.calcom_doctors, app.lead_sheets, app.lead_sheet_tabs to authenticated;
create policy calcom_accounts_read on app.calcom_accounts for select to authenticated
  using (app.can_manage(clinic_id));
create policy calcom_doctors_read on app.calcom_doctors for select to authenticated
  using (app.can_manage(clinic_id));
create policy lead_sheets_read on app.lead_sheets for select to authenticated
  using (app.can_manage(clinic_id));
create policy lead_sheet_tabs_read on app.lead_sheet_tabs for select to authenticated
  using (app.can_manage(clinic_id));

create trigger calcom_accounts_audit after insert or update or delete on app.calcom_accounts
  for each row execute function app.audit_row();
create trigger calcom_doctors_audit after insert or update or delete on app.calcom_doctors
  for each row execute function app.audit_row();
create trigger lead_sheets_audit after insert or update or delete on app.lead_sheets
  for each row execute function app.audit_row();
create trigger lead_sheet_tabs_audit after insert or update or delete on app.lead_sheet_tabs
  for each row execute function app.audit_row();
create trigger calcom_accounts_touch before update on app.calcom_accounts
  for each row execute function app.touch_updated_at();
create trigger lead_sheets_touch before update on app.lead_sheets
  for each row execute function app.touch_updated_at();
create trigger lead_sheet_tabs_touch before update on app.lead_sheet_tabs
  for each row execute function app.touch_updated_at();
