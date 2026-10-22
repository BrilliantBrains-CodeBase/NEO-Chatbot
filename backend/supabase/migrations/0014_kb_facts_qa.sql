-- 0014 Knowledge base layers 1 and 2 (90%+ of answers): clinic facts and approved questions and answers,
-- in English (the chatbot answers in English only). Only approved rows are used by the bot. Chunks (0005)
-- stay the last resort. Doctors are not stored here: the bot reads app.doctors, which staff edit.

-- Layer 1: one fact per key (address, timings, phone, cost_per_graft, emi, ...).
create table app.kb_facts (
  id          uuid primary key default gen_random_uuid(),
  clinic_id   text not null references app.clinics (id),
  key         text not null check (key ~ '^[a-z][a-z0-9_]{1,49}$'),
  category    text not null default 'clinic_info'
                check (category in ('clinic_info', 'treatment', 'cost', 'doctor', 'policy', 'other')),
  value       text not null check (length(trim(value)) between 1 and 2000),
  status      text not null default 'draft' check (status in ('draft', 'approved', 'retired')),
  approved_by uuid references app.profiles (id) on delete set null,
  approved_at timestamptz,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (clinic_id, key),
  check (status <> 'approved' or approved_at is not null)
);

-- Layer 2: a question, other ways patients ask it (one per line, English or Hinglish), and the answer.
create table app.kb_qa (
  id          uuid primary key default gen_random_uuid(),
  clinic_id   text not null references app.clinics (id),
  question    text not null check (length(trim(question)) between 3 and 300),
  variants    text not null default '' check (length(variants) <= 4000),
  answer      text not null check (length(trim(answer)) between 1 and 2000),
  category    text not null default 'other'
                check (category in ('clinic_info', 'treatment', 'cost', 'doctor', 'policy', 'other')),
  treatment   text check (length(treatment) <= 100),
  status      text not null default 'draft' check (status in ('draft', 'approved', 'retired')),
  approved_by uuid references app.profiles (id) on delete set null,
  approved_at timestamptz,
  -- Filled by the backend once the embedding model is chosen (same 384 numbers as kb_chunks).
  embedding   extensions.vector(384),
  -- Keyword search: English stemming for the question, plain words for Hinglish and other variants.
  tsv         tsvector generated always as
                (to_tsvector('english', question) || to_tsvector('simple', variants)) stored,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  check (status <> 'approved' or approved_at is not null)
);
create index kb_qa_clinic on app.kb_qa (clinic_id, status);
create index kb_qa_keywords on app.kb_qa using gin (tsv);
create index kb_qa_vector on app.kb_qa using hnsw (embedding extensions.vector_cosine_ops);

-- CRM: managers of the clinic read, add, edit and approve; nobody deletes (retire instead).
alter table app.kb_facts enable row level security;
alter table app.kb_qa enable row level security;
grant select, insert on app.kb_facts, app.kb_qa to authenticated;
grant update (category, value, status, approved_by, approved_at) on app.kb_facts to authenticated;
grant update (question, variants, answer, category, treatment, status, approved_by, approved_at)
  on app.kb_qa to authenticated;
create policy kb_facts_read on app.kb_facts for select to authenticated using (app.can_manage(clinic_id));
create policy kb_facts_add on app.kb_facts for insert to authenticated with check (app.can_manage(clinic_id));
create policy kb_facts_edit on app.kb_facts for update to authenticated
  using (app.can_manage(clinic_id)) with check (app.can_manage(clinic_id));
create policy kb_qa_read on app.kb_qa for select to authenticated using (app.can_manage(clinic_id));
create policy kb_qa_add on app.kb_qa for insert to authenticated with check (app.can_manage(clinic_id));
create policy kb_qa_edit on app.kb_qa for update to authenticated
  using (app.can_manage(clinic_id)) with check (app.can_manage(clinic_id));

create trigger kb_facts_audit after insert or update or delete on app.kb_facts
  for each row execute function app.audit_row();
create trigger kb_qa_audit after insert or update or delete on app.kb_qa
  for each row execute function app.audit_row();
create trigger kb_facts_touch before update on app.kb_facts
  for each row execute function app.touch_updated_at();
create trigger kb_qa_touch before update on app.kb_qa
  for each row execute function app.touch_updated_at();
