-- 0010 Chat is kept 3 days instead of 21 (client decision, 22 Oct 2026), the same as the widget's
-- history on the patient's device. Leads keep their requests and the patient's question.
create or replace function app.job_delete_old_chat() returns integer
language plpgsql
set search_path = ''
as $$
declare
  n integer;
begin
  delete from app.chat_messages where created_at < now() - interval '3 days';
  get diagnostics n = row_count;
  delete from app.chat_sessions where last_at < now() - interval '3 days';
  return n;
end;
$$;
revoke all on function app.job_delete_old_chat() from public, anon, authenticated;
