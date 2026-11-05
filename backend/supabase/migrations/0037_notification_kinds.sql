-- 0037 More in the bell: requests left waiting too long, new leads (arrivals close together become one
-- notification), a lead given to you, access requests and integrations that failed. Each kind needs a screen,
-- so a person sees only what their role allows. Rows hold links and counts, never patient details.

alter table app.notifications drop constraint notifications_kind_check;
alter table app.notifications add constraint notifications_kind_check check (kind in (
  'book', 'online', 'cancel', 'reschedule', 'callback', 'question', 'emergency',
  'callback_late', 'booking_late', 'lead_new', 'lead_assigned', 'access_request', 'integration_failed'
));
alter table app.notifications
  -- The screen a person must be able to see for this to show (Who sees what).
  add column screen text not null default 'inbox'
    check (screen in ('inbox', 'leads', 'team', 'dash_integrations')),
  -- For one person only ("assigned to you"); empty: everyone in the clinic who can see the screen.
  add column user_id uuid references app.profiles (id) on delete cascade,
  add column count integer not null default 1 check (count >= 1),   -- leads grouped into this one
  add column detail text check (length(detail) <= 100);             -- the integration's name
create index notifications_user on app.notifications (user_id) where user_id is not null;

drop policy notifications_read on app.notifications;
create policy notifications_read on app.notifications for select to authenticated
  using (app.my_role(clinic_id) is not null and (user_id is null or user_id = auth.uid()));

-- Minutes the clinic was open between two moments: its hours in its own timezone, without closed days and holidays.
create function app.open_minutes(clinic text, from_at timestamptz, to_at timestamptz) returns integer
language plpgsql
stable
set search_path = ''
as $$
declare
  c record;
  d date;
  day_from timestamptz;
  day_to timestamptz;
  total numeric := 0;
begin
  select timezone, open_time, close_time, closed_weekdays into c from app.clinics where id = clinic;
  if not found or to_at <= from_at then
    return 0;
  end if;
  d := (from_at at time zone c.timezone)::date;
  while d <= (to_at at time zone c.timezone)::date loop
    if not (extract(dow from d)::smallint = any (c.closed_weekdays))
       and not exists (select 1 from app.clinic_holidays h where h.clinic_id = clinic and h.day = d) then
      day_from := greatest(from_at, (d + c.open_time) at time zone c.timezone);
      day_to := least(to_at, (d + c.close_time) at time zone c.timezone);
      if day_to > day_from then
        total := total + extract(epoch from day_to - day_from) / 60;
      end if;
    end if;
    d := d + 1;
  end loop;
  return floor(total)::integer;
end;
$$;
revoke all on function app.open_minutes(text, timestamptz, timestamptz) from public, anon, authenticated;

-- Left waiting (agreed in the CRM design): a call back or question after 1 open hour, a booking after 2. An
-- emergency is already at the top. Only requests of the last 7 days: older ones would all alert at once.
create function app.job_flag_late_requests() returns integer
language plpgsql
set search_path = ''
as $$
declare
  n integer;
begin
  insert into app.notifications (clinic_id, kind, lead_id, request_id, dedupe_key)
  select r.clinic_id, case when r.type in ('callback', 'question') then 'callback_late' else 'booking_late' end,
         r.lead_id, r.id, 'late:' || r.id
  from app.requests r
  where r.status = 'pending' and r.type in ('book', 'online', 'callback', 'question')
    and r.data->>'urgent' is distinct from 'true'
    and r.created_at > now() - interval '7 days' and r.created_at < now() - interval '1 hour'
    and app.open_minutes(r.clinic_id, r.created_at, now())
        >= case when r.type in ('callback', 'question') then 60 else 120 end
  on conflict (dedupe_key) do nothing;
  get diagnostics n = row_count;
  return n;
end;
$$;
revoke all on function app.job_flag_late_requests() from public, anon, authenticated;
select cron.schedule('neo_flag_late_requests', '*/5 * * * *', 'select app.job_flag_late_requests()');

-- New leads from anywhere but the chatbot (its leads already arrive as a request). Those of the same hour are
-- one notification that counts up and shows as new again, so an import of 240 is one line, not 240.
create function app.notify_lead() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'INSERT' then
    if new.source <> 'chatbot' then
      with up as (
        insert into app.notifications (clinic_id, kind, screen, lead_id, dedupe_key)
        values (new.clinic_id, 'lead_new', 'leads', new.id,
                'leads:' || new.clinic_id || ':' || to_char(now() at time zone 'UTC', 'YYYY-MM-DD-HH24'))
        on conflict (dedupe_key) do update
          set count = app.notifications.count + 1, lead_id = null, created_at = now()
        returning id
      )
      delete from app.notification_receipts r using up where r.notification_id = up.id;
    end if;
  elsif new.assigned_to is distinct from old.assigned_to and new.assigned_to is not null
        and new.assigned_to is distinct from auth.uid() then  -- not when you take it yourself
    insert into app.notifications (clinic_id, kind, screen, user_id, lead_id, dedupe_key)
    values (new.clinic_id, 'lead_assigned', 'leads', new.assigned_to, new.id,
            'assigned:' || new.id || ':' || new.assigned_to || ':' || extract(epoch from now())::bigint)
    on conflict (dedupe_key) do nothing;
  end if;
  return null;
exception when others then
  raise warning 'notify_lead: % %', sqlstate, sqlerrm;
  return null;
end;
$$;
revoke all on function app.notify_lead() from public, anon, authenticated;
create trigger leads_notify after insert or update of assigned_to on app.leads
  for each row execute function app.notify_lead();

-- Someone asked for access: those who can see Team hear about it, until it is decided.
create function app.notify_access_request() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'INSERT' then
    insert into app.notifications (clinic_id, kind, screen, dedupe_key)
    values (new.clinic_id, 'access_request', 'team', 'access:' || new.id)
    on conflict (dedupe_key) do nothing;
  elsif old.status = 'pending' and new.status <> 'pending' then
    update app.notifications set resolved_at = now(), resolved_by = new.decided_by
    where dedupe_key = 'access:' || new.id and resolved_at is null;
  end if;
  return null;
exception when others then
  raise warning 'notify_access_request: % %', sqlstate, sqlerrm;
  return null;
end;
$$;
revoke all on function app.notify_access_request() from public, anon, authenticated;
create trigger access_requests_notify after insert or update of status on app.access_requests
  for each row execute function app.notify_access_request();
