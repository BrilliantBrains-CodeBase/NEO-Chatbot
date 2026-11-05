-- 0036 Notifications: what the bell shows, kept apart from the Inbox's work queue. One row per event for the
-- whole clinic; each person's read and cleared state is their own, so one person reading does not hide it from
-- a colleague. A row holds links, never patient details, and goes with its lead in a patient data deletion.

create table app.notifications (
  id          uuid primary key default gen_random_uuid(),
  clinic_id   text not null references app.clinics (id) on delete cascade,
  kind        text not null check (kind in ('book', 'online', 'cancel', 'reschedule', 'callback', 'question', 'emergency')),
  severity    text not null default 'normal' check (severity in ('normal', 'urgent')),
  lead_id     uuid,
  request_id  uuid,
  -- Someone handled it: it stops counting as unread for everyone. No foreign key on the person: a request's
  -- approval must never fail because of the bell.
  resolved_at timestamptz,
  resolved_by uuid,
  dedupe_key  text not null unique check (length(dedupe_key) between 1 and 200),
  created_at  timestamptz not null default now(),
  foreign key (lead_id, clinic_id) references app.leads (id, clinic_id) on delete cascade,
  foreign key (request_id, clinic_id) references app.requests (id, clinic_id) on delete cascade
);
create index notifications_recent on app.notifications (clinic_id, created_at desc, id desc);
create index notifications_request on app.notifications (request_id);
create index notifications_lead on app.notifications (lead_id);

-- One person's state of one notification. No row: unread, unless "mark all read" has passed it.
create table app.notification_receipts (
  notification_id uuid not null references app.notifications (id) on delete cascade,
  user_id         uuid not null references app.profiles (id) on delete cascade,
  read_at         timestamptz,
  dismissed_at    timestamptz,
  primary key (notification_id, user_id)
);
create index notification_receipts_user on app.notification_receipts (user_id);

-- "Mark all read" for one person in one clinic: everything up to this moment, without a row per notification.
create table app.notification_state (
  user_id     uuid not null references app.profiles (id) on delete cascade,
  clinic_id   text not null references app.clinics (id) on delete cascade,
  read_all_at timestamptz not null default now(),
  primary key (user_id, clinic_id)
);

-- One person's choices, the same on every device. An emergency always shows, whatever is turned off here.
create table app.notification_prefs (
  user_id    uuid primary key references app.profiles (id) on delete cascade,
  off_kinds  text[] not null default '{}',
  sound      boolean not null default false,
  desktop    boolean not null default false,
  updated_at timestamptz not null default now()
);

-- Row Level Security: read your clinics' notifications and your own state. Changes go through the backend.
alter table app.notifications enable row level security;
alter table app.notification_receipts enable row level security;
alter table app.notification_state enable row level security;
alter table app.notification_prefs enable row level security;
grant select on app.notifications, app.notification_receipts, app.notification_state, app.notification_prefs
  to authenticated;
create policy notifications_read on app.notifications for select to authenticated
  using (app.my_role(clinic_id) is not null);
create policy notification_receipts_own on app.notification_receipts for select to authenticated
  using (user_id = auth.uid());
create policy notification_state_own on app.notification_state for select to authenticated
  using (user_id = auth.uid());
create policy notification_prefs_own on app.notification_prefs for select to authenticated
  using (user_id = auth.uid());

-- Requests are saved from several places, so the database makes their notifications. A problem here is only a
-- warning: a patient's booking or a staff approval must never fail because of the bell.
create function app.notify_request() returns trigger
language plpgsql
set search_path = ''
as $$
declare
  urgent boolean;
begin
  if tg_op = 'INSERT' then
    urgent := coalesce((new.data->>'urgent')::boolean, false);
    insert into app.notifications (clinic_id, kind, severity, lead_id, request_id, dedupe_key, created_at)
    values (new.clinic_id, case when urgent then 'emergency' else new.type end,
            case when urgent then 'urgent' else 'normal' end, new.lead_id, new.id,
            'request:' || new.id, new.created_at)
    on conflict (dedupe_key) do nothing;
  elsif old.status = 'pending' and new.status <> 'pending' then
    update app.notifications set resolved_at = now(), resolved_by = auth.uid()
    where request_id = new.id and resolved_at is null;
  end if;
  return null;
exception when others then
  raise warning 'notify_request: % %', sqlstate, sqlerrm;
  return null;
end;
$$;
revoke all on function app.notify_request() from public, anon, authenticated;
create trigger requests_notify after insert or update of status on app.requests
  for each row execute function app.notify_request();

-- Requests already waiting show in the bell from the start. Emergencies saved before the flag existed get it.
update app.requests set data = data || '{"urgent": true}'::jsonb
where status = 'pending' and data->>'reason' like 'EMERGENCY in chat%' and data->>'urgent' is null;

insert into app.notifications (clinic_id, kind, severity, lead_id, request_id, dedupe_key, created_at)
select clinic_id, case when data->>'urgent' = 'true' then 'emergency' else type end,
       case when data->>'urgent' = 'true' then 'urgent' else 'normal' end,
       lead_id, id, 'request:' || id, created_at
from app.requests where status = 'pending';

-- Kept 90 days. An emergency nobody has handled stays.
create function app.job_trim_notifications() returns integer
language plpgsql
set search_path = ''
as $$
declare
  n integer;
begin
  delete from app.notifications
  where created_at < now() - interval '90 days' and (severity <> 'urgent' or resolved_at is not null);
  get diagnostics n = row_count;
  return n;
end;
$$;
revoke all on function app.job_trim_notifications() from public, anon, authenticated;
select cron.schedule('neo_trim_notifications', '30 22 * * *', 'select app.job_trim_notifications()');
