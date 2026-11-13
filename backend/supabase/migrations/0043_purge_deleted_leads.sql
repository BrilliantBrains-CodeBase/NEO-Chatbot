-- 0043 Deleted leads are removed for good after 30 days (user, 2026-11-11). Until then a Clinic Manager or
-- Super Admin can restore them (CRM → Leads → Recently deleted). Each goes through app.delete_patient_data
-- (0011), so its appointments, requests, tasks, timeline, chats, questions and the personal details in the
-- audit log go too, exactly as for a patient's own erasure request.

create function app.job_purge_deleted_leads() returns integer
language plpgsql
set search_path = ''
as $$
declare
  n integer := 0;
  target uuid;
begin
  for target in select id from app.leads where deleted_at < now() - interval '30 days' loop
    perform app.delete_patient_data(target);
    n := n + 1;
  end loop;
  return n;
end;
$$;

revoke all on function app.job_purge_deleted_leads() from public, anon, authenticated;

-- 02:45 India time (21:15 UTC), before the other night jobs.
select cron.schedule('neo_purge_deleted_leads', '15 21 * * *', 'select app.job_purge_deleted_leads()');
