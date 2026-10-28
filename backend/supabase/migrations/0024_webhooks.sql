-- 0024 Dashboard → Integrations → Webhooks. "send": CRM events (new lead, booking request ...) POSTed as JSON to an
-- address the clinic sets, signed with the webhook's secret, retried up to 3 times, every attempt logged.
-- "receive": a private address an outside system POSTs leads to. Secrets are in Supabase Vault (the id here).
create table app.webhooks (
  id          uuid primary key default gen_random_uuid(),
  clinic_id   text not null references app.clinics (id),
  direction   text not null check (direction in ('send', 'receive')),
  name        text not null check (length(trim(name)) between 1 and 80),
  url         text check (url ~ '^https://\S+$' and length(url) <= 600), -- send only
  events      text[] not null default '{}' check (events <@ array['lead_new', 'booking_request',
                'callback_request', 'appointment_confirmed']::text[]),
  secret      uuid not null,        -- vault.secrets id
  active      boolean not null default true,
  created_by  uuid references app.profiles (id) on delete set null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  check ((direction = 'send') = (url is not null))
);

create table app.webhook_log (
  id          bigint generated always as identity primary key,
  webhook_id  uuid not null references app.webhooks (id) on delete cascade,
  clinic_id   text not null references app.clinics (id),
  event       text not null,
  attempt     smallint not null default 1 check (attempt between 1 and 4),
  ok          boolean not null,
  status_code integer,
  error       text check (length(error) <= 500),
  at          timestamptz not null default now()
);
create index webhook_log_recent on app.webhook_log (webhook_id, at desc);

alter table app.webhooks enable row level security;
alter table app.webhook_log enable row level security;
grant select on app.webhooks, app.webhook_log to authenticated;
create policy webhooks_read on app.webhooks for select to authenticated using (app.can_manage(clinic_id));
create policy webhook_log_read on app.webhook_log for select to authenticated using (app.can_manage(clinic_id));
create trigger webhooks_audit after insert or update or delete on app.webhooks
  for each row execute function app.audit_row();
create trigger webhooks_touch before update on app.webhooks
  for each row execute function app.touch_updated_at();
