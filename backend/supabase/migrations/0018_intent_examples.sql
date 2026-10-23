-- 0018 Understanding without the LLM (T2, T3): example phrases per topic, and other wordings for facts.
-- Both are approved by clinic staff; the bot only uses approved rows and never adds any by itself.
-- Their meaning (bge-small, 384 numbers) is worked out by the backend and kept in memory: rows are short.

-- T2: phrases that mean a topic of the chat ("r u a bot" -> identity, "kab aa sakta hoon" -> book). intent
-- is a topic the clinic's chat has (identity, greeting, thanks, bye, book, cost, clinic, talk, about, intl,
-- results, treat, online, cancel, reschedule, callback); the backend ignores one the clinic does not have.
create table app.intent_examples (
  id          uuid primary key default gen_random_uuid(),
  clinic_id   text not null references app.clinics (id),
  intent      text not null check (intent ~ '^[a-z][a-z_]{1,29}$'),
  example     text not null check (length(trim(example)) between 2 and 200),
  status      text not null default 'draft' check (status in ('draft', 'approved', 'retired')),
  approved_by uuid references app.profiles (id) on delete set null,
  approved_at timestamptz,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  check (status <> 'approved' or approved_at is not null)
);
create index intent_examples_clinic on app.intent_examples (clinic_id, status);
-- One phrase means one topic in a clinic: "call me" cannot be both "talk" and "callback" (the bot could not
-- know which), and "R u a bot " is the same phrase as "r u a bot". Retired rows do not count.
create unique index intent_examples_one_topic on app.intent_examples
  (clinic_id, lower(regexp_replace(trim(example), '\s+', ' ', 'g'))) where status <> 'retired';

-- T3: other ways patients ask for a fact, one per line ("insta id", "instagram page" -> social).
alter table app.kb_facts
  add column variants text not null default '' check (length(variants) <= 4000);
grant update (variants) on app.kb_facts to authenticated;

-- CRM: managers of the clinic read, add, edit and approve; nobody deletes (retire instead). Same as 0014.
alter table app.intent_examples enable row level security;
grant select, insert on app.intent_examples to authenticated;
grant update (intent, example, status, approved_by, approved_at) on app.intent_examples to authenticated;
create policy intent_examples_read on app.intent_examples for select to authenticated
  using (app.can_manage(clinic_id));
create policy intent_examples_add on app.intent_examples for insert to authenticated
  with check (app.can_manage(clinic_id));
create policy intent_examples_edit on app.intent_examples for update to authenticated
  using (app.can_manage(clinic_id)) with check (app.can_manage(clinic_id));

create trigger intent_examples_audit after insert or update or delete on app.intent_examples
  for each row execute function app.audit_row();
create trigger intent_examples_touch before update on app.intent_examples
  for each row execute function app.touch_updated_at();
