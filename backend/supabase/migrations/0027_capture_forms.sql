-- 0027 Website install → auto-capture: on an approved website with this on, the chatbot script already on the
-- page also sends the clinic's own form submissions (with a phone or email) to the CRM as leads. Off by default.
alter table app.clinic_websites add column capture_forms boolean not null default false;
