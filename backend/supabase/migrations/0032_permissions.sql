-- 0032 Who sees what: for each screen (CRM screens and Dashboard tabs) and role (Clinic Manager, Front Desk,
-- Doctor): hidden, view or edit. BB Admin always has everything. The rules stack: built-in defaults (today's
-- behaviour, in the backend) ← BB's defaults for all clinics (app.platform) ← one clinic's own changes (set by
-- BB Admin or that clinic's manager, never above the manager's own access). Only what was changed is stored:
-- {"front_desk": {"reports": "hidden"}, ...}.
alter table app.platform add column permissions jsonb not null default '{}'::jsonb
  check (jsonb_typeof(permissions) = 'object');

create table app.clinic_permissions (
  id          uuid not null unique default gen_random_uuid(), -- the change log names rows by id
  clinic_id   text primary key references app.clinics (id),
  rules       jsonb not null default '{}'::jsonb check (jsonb_typeof(rules) = 'object'),
  updated_by  uuid references app.profiles (id) on delete set null,
  updated_at  timestamptz not null default now()
);

alter table app.clinic_permissions enable row level security;
grant select on app.clinic_permissions to authenticated;
create policy clinic_permissions_read on app.clinic_permissions for select to authenticated
  using (app.can_manage(clinic_id));
create trigger clinic_permissions_audit after insert or update or delete on app.clinic_permissions
  for each row execute function app.audit_row();
create trigger clinic_permissions_touch before update on app.clinic_permissions
  for each row execute function app.touch_updated_at();

-- Access for a limited time: one person gets a screen at view or edit until a moment, then it ends by itself
-- (their role's rule applies again). Given by BB Admin, or a Clinic Manager never above their own access.
create table app.access_grants (
  id          uuid primary key default gen_random_uuid(),
  clinic_id   text not null references app.clinics (id),
  user_id     uuid not null references app.profiles (id) on delete cascade,
  screen      text not null check (length(screen) between 1 and 40),
  level       text not null check (level in ('view', 'edit')),
  until       timestamptz not null,
  given_by    uuid references app.profiles (id) on delete set null,
  created_at  timestamptz not null default now()
);
create index access_grants_person on app.access_grants (user_id, clinic_id, until);

alter table app.access_grants enable row level security;
grant select on app.access_grants to authenticated;
create policy access_grants_read on app.access_grants for select to authenticated using (app.can_manage(clinic_id));
create trigger access_grants_audit after insert or update or delete on app.access_grants
  for each row execute function app.audit_row();
