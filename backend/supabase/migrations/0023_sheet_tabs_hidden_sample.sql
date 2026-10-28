-- 0023 Google Sheet leads: a tab staff do not want can be hidden from the list, and each tab keeps one example
-- row (as the sheet has it) so the mapping shows what each column holds, shown the CRM's way (the sheet's
-- values are never changed).
alter table app.lead_sheet_tabs
  add column hidden boolean not null default false,
  add column sample text[] not null default '{}' check (cardinality(sample) <= 100);
