-- 0019 Dashboard (chatbot console): each clinic's widget settings, edited as a draft and then published.
-- One row per clinic. draft is what staff are editing; published is what the widget shows. Both are JSON
-- objects checked by the backend (appearance, template, menu buttons ...); the database only checks shape.
-- Every publish is also kept in clinic_setting_versions, so a clinic can roll back.
-- New tables only: nothing existing changes, and the live chatbot does not read them until it is switched.
create table app.clinic_settings (
  id           uuid primary key default gen_random_uuid(), -- the change log names rows by id
  clinic_id    text not null unique references app.clinics (id),
  draft        jsonb not null default '{}'::jsonb check (jsonb_typeof(draft) = 'object'),
  published    jsonb not null default '{}'::jsonb check (jsonb_typeof(published) = 'object'),
  version      integer not null default 0 check (version >= 0), -- the published version (0: never published)
  updated_by   uuid references app.profiles (id) on delete set null,
  published_by uuid references app.profiles (id) on delete set null,
  published_at timestamptz,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  check (version = 0 or published_at is not null)
);

create table app.clinic_setting_versions (
  id           bigint generated always as identity primary key,
  clinic_id    text not null references app.clinics (id),
  version      integer not null check (version >= 1),
  settings     jsonb not null check (jsonb_typeof(settings) = 'object'),
  published_by uuid references app.profiles (id) on delete set null,
  published_at timestamptz not null default now(),
  unique (clinic_id, version)
);

-- CRM: managers of the clinic read; changes go through the backend (which checks every value), not straight
-- from the browser. Versions are a record: never edited or deleted.
alter table app.clinic_settings enable row level security;
alter table app.clinic_setting_versions enable row level security;
grant select on app.clinic_settings, app.clinic_setting_versions to authenticated;
create policy clinic_settings_read on app.clinic_settings for select to authenticated
  using (app.can_manage(clinic_id));
create policy clinic_setting_versions_read on app.clinic_setting_versions for select to authenticated
  using (app.can_manage(clinic_id));
create trigger clinic_setting_versions_no_update before update or delete on app.clinic_setting_versions
  for each row execute function app.no_update();

create trigger clinic_settings_audit after insert or update or delete on app.clinic_settings
  for each row execute function app.audit_row();
create trigger clinic_settings_touch before update on app.clinic_settings
  for each row execute function app.touch_updated_at();
