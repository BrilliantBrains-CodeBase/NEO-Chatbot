-- 0008 Outbox: WhatsApp, email and calendar messages waiting to be sent. A worker sends them and
-- retries failures, so a message is never lost when a provider is down. Written by the backend only;
-- readable by managers and BB Admin. Row Level Security on.

create table app.outbox (
  id             bigint generated always as identity primary key,
  clinic_id      text not null references app.clinics (id),
  channel        text not null check (channel in ('whatsapp', 'email', 'calendar')),
  kind           text not null check (kind ~ '^[a-z][a-z0-9_]{0,49}$'), -- e.g. booking_confirmed, reminder_24h
  lead_id        uuid,
  appointment_id uuid,
  payload        jsonb not null default '{}'::jsonb check (jsonb_typeof(payload) = 'object'),
  status         text not null default 'queued'
                   check (status in ('queued', 'sending', 'sent', 'failed', 'cancelled')),
  attempts       smallint not null default 0 check (attempts between 0 and 10),
  next_try_at    timestamptz not null default now(),
  last_error     text,
  sent_at        timestamptz,
  -- The same message is never queued twice (e.g. 'reminder_24h:<appointment id>').
  dedupe_key     text unique check (length(dedupe_key) between 1 and 200),
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  check ((status = 'sent') = (sent_at is not null)),
  check (status <> 'failed' or last_error is not null),
  foreign key (lead_id, clinic_id) references app.leads (id, clinic_id) on delete cascade,
  foreign key (appointment_id, clinic_id) references app.appointments (id, clinic_id) on delete cascade
);

-- The worker's queue: due messages first.
create index outbox_due on app.outbox (next_try_at) where status = 'queued';
create index outbox_clinic on app.outbox (clinic_id, created_at desc);

create trigger outbox_touch before update on app.outbox for each row execute function app.touch_updated_at();

alter table app.outbox enable row level security;
grant select on app.outbox to authenticated;
create policy outbox_read on app.outbox for select to authenticated using (app.can_manage(clinic_id));
