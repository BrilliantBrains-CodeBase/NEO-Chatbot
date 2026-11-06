-- 0039 The Inbox is the intake queue.
-- New leads from every source (chatbot, website forms, Google Sheets, integrations, imports) arrive without an
-- owner and wait in the Inbox, where the clinic manager or a front desk member assigns them. Once assigned, a
-- lead works from Leads: its owner confirms bookings and moves the stages there.
--
-- lead_assignment:
--   inbox        new leads wait in the Inbox for someone to assign them (the default; replaces 'manual')
--   round_robin  shared among Front Desk members taking part in lead sharing (the Inbox is skipped)
--   manager      every new lead goes to the clinic's first Admin (the Inbox is skipped)
--
-- Every clinic moves to the Inbox flow; a clinic can switch back in Clinic settings.

alter table app.clinics drop constraint if exists clinics_lead_assignment_check;

update app.clinics set lead_assignment = 'inbox' where lead_assignment <> 'inbox';

alter table app.clinics
  alter column lead_assignment set default 'inbox',
  add constraint clinics_lead_assignment_check
    check (lead_assignment in ('inbox', 'round_robin', 'manager'));

-- The Inbox list: unassigned leads of a clinic, newest first.
create index if not exists leads_inbox_idx on app.leads (clinic_id, created_at desc)
  where assigned_to is null and deleted_at is null;
