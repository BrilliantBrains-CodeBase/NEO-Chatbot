-- 0001 Foundation: private schema, locked-down privileges, shared trigger, clinics.
-- See docs/DATABASE.md. Applied by backend/scripts/migrate.py inside one transaction.

-- Extensions used by later migrations (Supabase keeps extensions in the "extensions" schema).
create extension if not exists pgcrypto with schema extensions;   -- gen_random_uuid()
create extension if not exists btree_gist with schema extensions; -- no double booking (0003)
create extension if not exists pg_trgm with schema extensions;    -- name search (0003)
create extension if not exists vector with schema extensions;     -- knowledge base (0004)

-- ---------------------------------------------------------------------------------------------
-- Security baseline
-- Supabase grants anon and authenticated full rights on new objects in "public" by default.
-- All app tables live in the private schema "app", which the Supabase Data API does not expose,
-- and nothing in it is granted to anon or authenticated unless a migration does so on purpose.
-- ---------------------------------------------------------------------------------------------
create schema if not exists app;
revoke all on schema app from public, anon, authenticated;

alter default privileges in schema app revoke all on tables from public, anon, authenticated;
alter default privileges in schema app revoke all on sequences from public, anon, authenticated;
alter default privileges in schema app revoke all on functions from public, anon, authenticated;

-- The migration runner creates its bookkeeping table before this file runs, so lock it down here.
revoke all on table app.schema_migrations from public, anon, authenticated;
alter table app.schema_migrations enable row level security;

-- Close the same default in "public" too, in case anything is ever created there by mistake.
alter default privileges in schema public revoke all on tables from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;
alter default privileges in schema public revoke all on functions from anon, authenticated;

-- Shared trigger: keeps updated_at current on every table that has it.
create or replace function app.touch_updated_at() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;
revoke all on function app.touch_updated_at() from public, anon, authenticated;

-- ---------------------------------------------------------------------------------------------
-- Clinics. One row per clinic; the id is the readable clinic code used everywhere (CL01, CL02...).
-- CL99 is the hidden test clinic: tests write only there and it is excluded from reports.
-- ---------------------------------------------------------------------------------------------
create table app.clinics (
  id                         text primary key check (id ~ '^CL[0-9]{2}$'),
  name                       text not null check (length(trim(name)) between 2 and 100),
  bot_name                   text not null check (length(trim(bot_name)) between 2 and 50),
  timezone                   text not null default 'Asia/Kolkata',
  open_time                  time not null,
  close_time                 time not null,
  closed_weekdays            smallint[] not null default '{}'
                               check (closed_weekdays <@ array[0, 1, 2, 3, 4, 5, 6]::smallint[]),
  slot_minutes               smallint not null default 15 check (slot_minutes between 5 and 120),
  last_slot_before_close_min smallint not null default 30 check (last_slot_before_close_min between 0 and 240),
  booking_window_days        smallint not null default 14 check (booking_window_days between 1 and 180),
  booked_date_back_days      smallint not null default 60 check (booked_date_back_days between 0 and 365),
  next_lead_no               integer not null default 1 check (next_lead_no >= 1),
  phone                      text check (phone ~ '^\+[1-9][0-9]{6,14}$'),
  whatsapp                   text check (whatsapp ~ '^\+[1-9][0-9]{6,14}$'),
  website                    text check (website ~ '^https://'),
  allowed_origins            text[] not null default '{}',
  widget_config              jsonb not null default '{}'::jsonb check (jsonb_typeof(widget_config) = 'object'),
  is_test                    boolean not null default false,
  active                     boolean not null default true,
  created_at                 timestamptz not null default now(),
  updated_at                 timestamptz not null default now(),
  check (open_time < close_time)
);

create trigger clinics_touch before update on app.clinics
  for each row execute function app.touch_updated_at();

-- Row Level Security on from the start: no access for anyone except the table owner (the backend)
-- until a later migration adds explicit policies.
alter table app.clinics enable row level security;

insert into app.clinics
  (id, name, bot_name, open_time, close_time, closed_weekdays, phone, whatsapp, website, allowed_origins, is_test)
values
  ('CL01', 'Neo Follicle', 'Arya AI', '10:00', '19:00', '{2}', '+919731207940', '+919731207940',
   'https://neofollicletransplant.com', '{https://neofollicletransplant.com}', false),
  ('CL99', 'Test Clinic', 'Test AI', '10:00', '19:00', '{2}', null, null, null, '{}', true);
