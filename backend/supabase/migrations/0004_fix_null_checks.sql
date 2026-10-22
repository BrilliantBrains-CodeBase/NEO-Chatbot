-- 0004 Fix two CHECK rules from 0003 that a NULL could slip through.
-- A CHECK passes when its result is "unknown", and comparing NULL to a list gives "unknown".
-- So "stage = 'lost' and stage_reason in (...)" let a Lost lead through with no reason, and
-- "matched_appointment_id is null or match_status = 'matched'" let a linked request through with
-- no match status. Both are recreated so that a NULL can never satisfy them.

alter table app.leads drop constraint leads_check2;
alter table app.leads add constraint leads_stage_reason check (
  (stage = 'lost' and stage_reason is not null
     and stage_reason in ('not_reachable', 'not_interested', 'price', 'chose_another_clinic', 'other'))
  or (stage = 'invalid' and stage_reason is not null
     and stage_reason in ('wrong_number', 'spam', 'duplicate', 'test'))
  or (stage not in ('lost', 'invalid') and stage_reason is null)
);

alter table app.requests drop constraint requests_check1;
alter table app.requests add constraint requests_matched_needs_match check (
  matched_appointment_id is null or (match_status is not null and match_status = 'matched')
);
