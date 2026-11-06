-- 0042 Chatbot → Integrations → Lead & Booking API: an outside system (a website, a landing page, Zapier, a
-- partner app) POSTs JSON to an endpoint's address with its key in the X-API-Key header. Staff paste a sample
-- of that JSON and match its fields to ours; each call then makes a lead, or a lead and a booking request in the
-- Inbox. Fields not matched can be kept on the lead as "More information" (leads.extra).

alter table app.leads drop constraint leads_source_check;
alter table app.leads add constraint leads_source_check check (
  source in ('chatbot', 'meta_ads', 'google_ads', 'manual', 'whatsapp', 'walk_in', 'phone_call', 'referral',
             'website_form', 'api')
);

-- More information: label -> value, from an outside system (shown in the Lead drawer).
alter table app.leads add column extra jsonb not null default '{}'::jsonb
  check (jsonb_typeof(extra) = 'object');

create table app.api_endpoints (
  id          uuid primary key default gen_random_uuid(),
  clinic_id   text not null references app.clinics (id),
  name        text not null check (length(trim(name)) between 1 and 80),
  creates     text not null default 'lead' check (creates in ('lead', 'booking')),
  secret      uuid not null,                  -- vault.secrets id of its API key
  active      boolean not null default false, -- on: calls are taken
  sample      jsonb,                          -- the sample payload staff pasted
  mapping     jsonb not null default '{}'::jsonb check (jsonb_typeof(mapping) = 'object'), -- our field -> path
  keep_extra  boolean not null default true,  -- fields not matched go to the lead's More information
  created_by  uuid references app.profiles (id) on delete set null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (clinic_id, name)
);

-- Every call (taken or not), for staff; a call repeated with the same external id answers the first result.
create table app.api_log (
  id           bigint generated always as identity primary key,
  endpoint_id  uuid not null references app.api_endpoints (id) on delete cascade,
  clinic_id    text not null references app.clinics (id),
  ok           boolean not null,
  status_code  smallint not null,
  result       text not null check (length(result) <= 300), -- the lead code, or why not
  lead_code    text,
  request_id   uuid,
  external_id  text check (length(external_id) <= 200),
  at           timestamptz not null default now()
);
create index api_log_recent on app.api_log (endpoint_id, at desc);
create index api_log_external on app.api_log (endpoint_id, external_id) where ok and external_id is not null;

-- CRM: managers of the clinic read; changes go through the backend. Vault stays closed to the browser.
alter table app.api_endpoints enable row level security;
alter table app.api_log enable row level security;
grant select on app.api_endpoints, app.api_log to authenticated;
create policy api_endpoints_read on app.api_endpoints for select to authenticated using (app.can_manage(clinic_id));
create policy api_log_read on app.api_log for select to authenticated using (app.can_manage(clinic_id));
create trigger api_endpoints_audit after insert or update or delete on app.api_endpoints
  for each row execute function app.audit_row();
create trigger api_endpoints_touch before update on app.api_endpoints
  for each row execute function app.touch_updated_at();
