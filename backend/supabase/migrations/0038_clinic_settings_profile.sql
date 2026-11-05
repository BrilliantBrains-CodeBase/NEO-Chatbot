-- 0038 Clinic settings and My profile.
-- Clinic settings is the clinic's own record for the CRM: its details, the logo and favicon the CRM shows while
-- that clinic is chosen, and clinic-wide alerts. The chatbot keeps its own copy (Dashboard → Clinic info), so
-- nothing here changes what patients see. My profile adds each person's phone (already a column) and photo.

-- ---------------------------------------------------------------------------------------------
-- The clinic's details. phone, whatsapp and website are already on app.clinics (0001).
-- ---------------------------------------------------------------------------------------------
alter table app.clinics
  add column email           text check (email = lower(email) and email ~ '^[^@\s]+@[^@\s]+\.[^@\s]{2,}$'),
  add column alt_phone       text check (alt_phone ~ '^\+[1-9][0-9]{6,14}$'),
  add column address         text check (length(trim(address)) between 1 and 300),
  add column city            text check (length(trim(city)) between 1 and 60),
  add column state           text check (length(trim(state)) between 1 and 60),
  add column postal_code     text check (postal_code ~ '^[A-Za-z0-9][A-Za-z0-9 -]{1,9}$'),
  add column country         text not null default 'India' check (length(trim(country)) between 2 and 60),
  add column registration_no text check (length(trim(registration_no)) between 1 and 60),
  add column gstin           text check (gstin ~ '^[0-9]{2}[A-Z0-9]{13}$');

-- ---------------------------------------------------------------------------------------------
-- The CRM's look for one clinic: small uploaded images (resized in the browser), kept out of app.clinics so
-- the clinic list and its audit rows stay light.
-- ---------------------------------------------------------------------------------------------
create table app.clinic_branding (
  clinic_id  text primary key references app.clinics (id) on delete cascade,
  logo       text check (logo like 'data:image/%' and length(logo) <= 400000),
  favicon    text check (favicon like 'data:image/%' and length(favicon) <= 100000),
  updated_by uuid references app.profiles (id) on delete set null,
  updated_at timestamptz not null default now()
);
create trigger clinic_branding_touch before update on app.clinic_branding
  for each row execute function app.touch_updated_at();

-- ---------------------------------------------------------------------------------------------
-- Clinic-wide alerts. Each person's bell choices stay their own (app.notification_prefs, 0036); these say who
-- is emailed for the whole clinic. No row: the behaviour before this migration (every active Admin, no one else).
-- ---------------------------------------------------------------------------------------------
create table app.clinic_alerts (
  id                uuid not null unique default gen_random_uuid(), -- the change log names rows by id
  clinic_id         text primary key references app.clinics (id) on delete cascade,
  emergency_admins  boolean not null default true,  -- email the clinic's active Admins on an emergency
  emergency_emails  text[] not null default '{}'    -- and these addresses too (e.g. the front desk inbox)
    check (cardinality(emergency_emails) <= 10),
  updated_by        uuid references app.profiles (id) on delete set null,
  updated_at        timestamptz not null default now()
);
create trigger clinic_alerts_touch before update on app.clinic_alerts
  for each row execute function app.touch_updated_at();
create trigger clinic_alerts_audit after insert or update or delete on app.clinic_alerts
  for each row execute function app.audit_row();

-- ---------------------------------------------------------------------------------------------
-- My profile photo: a small image resized in the browser (about 10 KB), its own table so profile reads stay light.
-- ---------------------------------------------------------------------------------------------
create table app.profile_photos (
  user_id    uuid primary key references app.profiles (id) on delete cascade,
  photo      text not null check (photo like 'data:image/%' and length(photo) <= 60000),
  updated_at timestamptz not null default now()
);
create trigger profile_photos_touch before update on app.profile_photos
  for each row execute function app.touch_updated_at();

-- Backend only, as for every app table: Row Level Security on and nothing granted.
alter table app.clinic_branding enable row level security;
alter table app.clinic_alerts enable row level security;
alter table app.profile_photos enable row level security;

-- ---------------------------------------------------------------------------------------------
-- A person changes their own email on My profile through Supabase Auth, which asks them to confirm it. Once
-- confirmed, the CRM profile follows, so Team, alerts and sign-in all show the same address.
-- ---------------------------------------------------------------------------------------------
create function app.follow_auth_email() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.email is distinct from old.email and new.email is not null then
    update app.profiles set email = lower(new.email) where id = new.id and email <> lower(new.email);
  end if;
  return new;
end;
$$;
revoke all on function app.follow_auth_email() from public, anon, authenticated;

create trigger profiles_follow_email after update of email on auth.users
  for each row execute function app.follow_auth_email();
