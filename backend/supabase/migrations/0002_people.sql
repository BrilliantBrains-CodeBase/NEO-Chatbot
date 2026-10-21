-- 0002 People: staff profiles and roles per clinic, doctors, their weekly availability and leave.
-- Every table has Row Level Security on and nothing is granted to anon or authenticated (0001).
-- Access rules for signed-in CRM users come in the security migration.

-- ---------------------------------------------------------------------------------------------
-- Staff and doctors who sign in to NEO CRM. One profile per Supabase Auth user.
-- ---------------------------------------------------------------------------------------------
create table app.profiles (
  id           uuid primary key references auth.users (id) on delete cascade,
  full_name    text not null check (length(trim(full_name)) between 2 and 100),
  email        text not null unique check (email = lower(email) and email ~ '^[^@\s]+@[^@\s]+\.[^@\s]{2,}$'),
  phone        text check (phone ~ '^\+[1-9][0-9]{6,14}$'),
  active       boolean not null default true,
  last_seen_at timestamptz,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

-- A person's role in a clinic. BB Admin sees every clinic (security migration); the others only
-- the clinics they have a row for. Only front desk staff take part in the lead round robin.
create table app.user_clinics (
  user_id             uuid not null references app.profiles (id) on delete cascade,
  clinic_id           text not null references app.clinics (id),
  role                text not null check (role in ('bb_admin', 'clinic_manager', 'front_desk', 'doctor')),
  in_round_robin      boolean not null default false,
  rr_last_assigned_at timestamptz,
  active              boolean not null default true,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  primary key (user_id, clinic_id),
  check (not in_round_robin or role = 'front_desk')
);

create index user_clinics_clinic on app.user_clinics (clinic_id, role) where active;

-- ---------------------------------------------------------------------------------------------
-- Doctors. A doctor may exist without a login; when user_id is set it must be a doctor of the
-- same clinic (checked by trigger below).
-- ---------------------------------------------------------------------------------------------
create table app.doctors (
  id             uuid primary key default gen_random_uuid(),
  clinic_id      text not null references app.clinics (id),
  user_id        uuid,
  name           text not null check (length(trim(name)) between 2 and 100),
  role_title     text not null check (length(trim(role_title)) between 2 and 100),
  qualifications text not null default '',
  profile        jsonb not null default '{}'::jsonb check (jsonb_typeof(profile) = 'object'),
  sort_order     smallint not null default 0,
  active         boolean not null default true,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  -- Lets child tables reference (doctor, clinic) together, so no row can point across clinics.
  unique (id, clinic_id),
  unique (clinic_id, user_id),
  -- Deleting the sign-in keeps the doctor and clears the link.
  foreign key (user_id, clinic_id) references app.user_clinics (user_id, clinic_id) on delete set null (user_id)
);

create function app.check_doctor_login() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.user_id is not null and not exists (
    select 1 from app.user_clinics
    where user_id = new.user_id and clinic_id = new.clinic_id and role = 'doctor'
  ) then
    raise exception 'user % is not a doctor of clinic %', new.user_id, new.clinic_id
      using errcode = 'check_violation';
  end if;
  return new;
end;
$$;
revoke all on function app.check_doctor_login() from public, anon, authenticated;

create trigger doctors_login before insert or update of user_id, clinic_id on app.doctors
  for each row execute function app.check_doctor_login();

-- The other direction: a person linked to a doctor record keeps the doctor role until unlinked.
create function app.keep_doctor_role() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if old.role = 'doctor' and new.role <> 'doctor' and exists (
    select 1 from app.doctors where user_id = old.user_id and clinic_id = old.clinic_id
  ) then
    raise exception 'user % is linked to a doctor of clinic %; unlink first', old.user_id, old.clinic_id
      using errcode = 'check_violation';
  end if;
  return new;
end;
$$;
revoke all on function app.keep_doctor_role() from public, anon, authenticated;

create trigger user_clinics_doctor_role before update of role on app.user_clinics
  for each row execute function app.keep_doctor_role();

-- Weekly hours per doctor, separately for in-clinic and online consultations.
-- Overlapping hours for the same doctor, weekday and mode are rejected.
create table app.doctor_availability (
  id         uuid primary key default gen_random_uuid(),
  doctor_id  uuid not null,
  clinic_id  text not null,
  weekday    smallint not null check (weekday between 0 and 6), -- 0 = Sunday
  mode       text not null check (mode in ('in_clinic', 'online')),
  start_time time not null,
  end_time   time not null,
  minutes    int4range generated always as (
               int4range(extract(epoch from start_time)::int / 60, extract(epoch from end_time)::int / 60)
             ) stored,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (start_time < end_time),
  foreign key (doctor_id, clinic_id) references app.doctors (id, clinic_id) on delete cascade,
  exclude using gist (doctor_id with =, weekday with =, mode with =, minutes with &&)
);

create table app.doctor_leave (
  id         uuid primary key default gen_random_uuid(),
  doctor_id  uuid not null,
  clinic_id  text not null,
  from_date  date not null,
  to_date    date not null,
  reason     text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (from_date <= to_date),
  foreign key (doctor_id, clinic_id) references app.doctors (id, clinic_id) on delete cascade
);

create index doctor_leave_dates on app.doctor_leave (clinic_id, doctor_id, from_date, to_date);

-- updated_at on every table
create trigger profiles_touch before update on app.profiles for each row execute function app.touch_updated_at();
create trigger user_clinics_touch before update on app.user_clinics for each row execute function app.touch_updated_at();
create trigger doctors_touch before update on app.doctors for each row execute function app.touch_updated_at();
create trigger doctor_availability_touch before update on app.doctor_availability
  for each row execute function app.touch_updated_at();
create trigger doctor_leave_touch before update on app.doctor_leave for each row execute function app.touch_updated_at();

alter table app.profiles enable row level security;
alter table app.user_clinics enable row level security;
alter table app.doctors enable row level security;
alter table app.doctor_availability enable row level security;
alter table app.doctor_leave enable row level security;

-- ---------------------------------------------------------------------------------------------
-- Seed: Neo Follicle's doctor (approved mockup) and in-clinic hours, Wednesday to Monday 10:00-19:00.
-- Online hours are not seeded: clinic staff set them in NEO CRM (Doctors Availability).
-- ---------------------------------------------------------------------------------------------
with doc as (
  insert into app.doctors (clinic_id, name, role_title, qualifications, profile, sort_order)
  values (
    'CL01',
    'Dr. Sandeep Mahapatra',
    'Founder and Director, Neo Follicle',
    'MBBS, MD (Dermatology), ISHRS Gold Member, Certified DHI Specialist',
    '{"stats": [
        {"value": "20+", "label": "Years experience"},
        {"value": "10,000+", "label": "Transplants"},
        {"value": "60 lakh+", "label": "Follicles placed"},
        {"value": "500+", "label": "International patients"},
        {"value": "1 lakh+", "label": "PRP sessions"},
        {"value": "Gold", "label": "Medalist, MD"}
      ],
      "profile_url": "https://neofollicletransplant.com/dr-sandeep-mahapatra-hair-transplant-surgeon/"}'::jsonb,
    1
  )
  returning id, clinic_id
)
insert into app.doctor_availability (doctor_id, clinic_id, weekday, mode, start_time, end_time)
select doc.id, doc.clinic_id, d, 'in_clinic', '10:00', '19:00'
from doc, unnest(array[0, 1, 3, 4, 5, 6]) as d;
