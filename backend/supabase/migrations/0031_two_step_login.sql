-- 0031 Login & security → 2-step login: for the roles BB Admin chooses, a correct password is not enough. A
-- 6-digit code is emailed (the clinic's Gmail, the BB Gmail for BB Admin / as fallback) and must be typed; the
-- backend accepts that sign-in session only once its code is verified. Codes: 10 minutes, 5 tries, then
-- 15 minutes locked. Backend only (no browser access).
alter table app.platform add column two_step_roles text[] not null default '{}'
  check (two_step_roles <@ array['bb_admin', 'clinic_manager', 'front_desk', 'doctor']);

-- The person's current code (one at a time; only its hash is kept).
create table app.login_codes (
  user_id       uuid primary key references app.profiles (id) on delete cascade,
  code_hash     text not null,
  sent_at       timestamptz not null default now(),
  expires_at    timestamptz not null,
  tries         smallint not null default 0,
  locked_until  timestamptz
);

-- Sign-in sessions (Supabase's session id) whose code was verified.
create table app.login_sessions (
  session_id   uuid primary key,
  user_id      uuid not null references app.profiles (id) on delete cascade,
  verified_at  timestamptz not null default now()
);
create index login_sessions_user on app.login_sessions (user_id);

alter table app.login_codes enable row level security;
alter table app.login_sessions enable row level security;
