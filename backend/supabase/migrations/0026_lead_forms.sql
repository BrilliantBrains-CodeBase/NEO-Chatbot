-- 0026 Dashboard → Integrations → Website forms: the clinic's own forms on its website and landing pages
-- (Unbounce, Elementor, WPForms, Wix, Google Forms, Typeform ...) send each submission to a private address
-- (its own secret in Supabase Vault, only the id here). The first submission shows the form's fields; staff
-- map them to ours and turn the form on; then each submission becomes a lead (source "Website form").
alter table app.leads drop constraint leads_source_check;
alter table app.leads add constraint leads_source_check check (
  source in ('chatbot', 'meta_ads', 'google_ads', 'manual', 'whatsapp', 'walk_in', 'phone_call', 'referral',
             'website_form')
);

create table app.lead_forms (
  id            uuid primary key default gen_random_uuid(),
  clinic_id     text not null references app.clinics (id),
  name          text not null check (length(trim(name)) between 1 and 80),
  secret        uuid not null,                 -- vault.secrets id of this form's key
  active        boolean not null default false, -- on: submissions become leads
  fields        text[] not null default '{}' check (cardinality(fields) <= 100), -- as the form sends them
  sample        text[] not null default '{}' check (cardinality(sample) <= 100), -- one example submission
  mapping       jsonb not null default '{}'::jsonb check (jsonb_typeof(mapping) = 'object'), -- form field -> ours
  last_seen_at  timestamptz,                   -- the last submission
  created_by    uuid references app.profiles (id) on delete set null,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (clinic_id, name)
);

-- Every submission (made a lead or not), for staff.
create table app.lead_form_log (
  id        bigint generated always as identity primary key,
  form_id   uuid not null references app.lead_forms (id) on delete cascade,
  clinic_id text not null references app.clinics (id),
  ok        boolean not null,
  result    text not null check (length(result) <= 300), -- the lead code, or why not
  at        timestamptz not null default now()
);
create index lead_form_log_recent on app.lead_form_log (form_id, at desc);

-- CRM: managers of the clinic read; changes go through the backend. Vault stays closed to the browser.
alter table app.lead_forms enable row level security;
alter table app.lead_form_log enable row level security;
grant select on app.lead_forms, app.lead_form_log to authenticated;
create policy lead_forms_read on app.lead_forms for select to authenticated using (app.can_manage(clinic_id));
create policy lead_form_log_read on app.lead_form_log for select to authenticated using (app.can_manage(clinic_id));
create trigger lead_forms_audit after insert or update or delete on app.lead_forms
  for each row execute function app.audit_row();
create trigger lead_forms_touch before update on app.lead_forms
  for each row execute function app.touch_updated_at();
