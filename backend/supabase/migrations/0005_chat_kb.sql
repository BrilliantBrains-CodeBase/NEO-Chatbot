-- 0005 Chat and knowledge base: chat sessions and messages (deleted after 21 days by the jobs
-- migration), knowledge base documents and chunks (vector + keyword search per clinic), and the
-- questions the bot could not answer. Row Level Security on; nothing granted to anon/authenticated.

-- ---------------------------------------------------------------------------------------------
-- Chat. The ids are the ones the widget creates (s_ / v_ + 32 hex characters).
-- state holds the open flow and step (Redis is Phase 2).
-- ---------------------------------------------------------------------------------------------
create table app.chat_sessions (
  id         text primary key check (id ~ '^s_[0-9a-f]{32}$'),
  clinic_id  text not null references app.clinics (id),
  visitor_id text not null check (visitor_id ~ '^v_[0-9a-f]{32}$'),
  lead_id    uuid,
  state      jsonb not null default '{}'::jsonb check (jsonb_typeof(state) = 'object'),
  lang       text not null default 'en' check (lang in ('en', 'hinglish')),
  device     text check (device in ('mobile', 'desktop')),
  page_url   text check (length(page_url) <= 2000),
  started_at timestamptz not null default now(),
  last_at    timestamptz not null default now(),
  unique (id, clinic_id),
  check (last_at >= started_at),
  foreign key (lead_id, clinic_id) references app.leads (id, clinic_id) on delete set null (lead_id)
);

create index chat_sessions_lead on app.chat_sessions (lead_id) where lead_id is not null;
create index chat_sessions_last on app.chat_sessions (last_at);

create table app.chat_messages (
  id          bigint generated always as identity primary key,
  session_id  text not null,
  clinic_id   text not null,
  role        text not null check (role in ('patient', 'bot')),
  text        text not null check (length(text) between 1 and 4000),
  event       text check (event in ('start', 'text', 'button', 'restart')),
  ui_type     text,
  answered_by text check (answered_by in ('flow', 'rule', 'kb', 'llm', 'lead', 'menu', 'error')),
  created_at  timestamptz not null default now(),
  -- Patients send events; the bot says how it answered.
  check ((role = 'patient') = (event is not null)),
  check (role = 'bot' or answered_by is null),
  foreign key (session_id, clinic_id) references app.chat_sessions (id, clinic_id) on delete cascade
);

create index chat_messages_session on app.chat_messages (session_id, created_at);
create index chat_messages_age on app.chat_messages (created_at);

-- ---------------------------------------------------------------------------------------------
-- Knowledge base: one PDF per clinic, in versions. Only approved chunks are searched.
-- ---------------------------------------------------------------------------------------------
create table app.kb_documents (
  id           uuid primary key default gen_random_uuid(),
  clinic_id    text not null references app.clinics (id),
  file_name    text not null check (length(trim(file_name)) between 1 and 200),
  storage_path text,
  version      integer not null check (version >= 1),
  status       text not null default 'draft' check (status in ('draft', 'approved', 'retired')),
  approved_by  uuid references app.profiles (id) on delete set null,
  approved_at  timestamptz,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  unique (id, clinic_id),
  unique (clinic_id, file_name, version),
  check (status <> 'approved' or approved_at is not null)
);

create table app.kb_chunks (
  id          uuid primary key default gen_random_uuid(),
  clinic_id   text not null,
  document_id uuid not null,
  title       text not null default '',
  text        text not null check (length(trim(text)) between 1 and 8000),
  category    text not null default 'other'
                check (category in ('clinic_info', 'treatment', 'cost', 'doctor', 'policy', 'other')),
  page        integer check (page >= 1),
  status      text not null default 'draft' check (status in ('draft', 'approved', 'retired')),
  -- bge-small-en-v1.5: exactly 384 numbers; any other size is rejected.
  embedding   extensions.vector(384) not null,
  -- Keyword search (the BM25-style half of hybrid search), kept up to date by Postgres.
  tsv         tsvector generated always as (to_tsvector('english', title || ' ' || text)) stored,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  foreign key (document_id, clinic_id) references app.kb_documents (id, clinic_id) on delete cascade
);

create index kb_chunks_vector on app.kb_chunks using hnsw (embedding extensions.vector_cosine_ops);
create index kb_chunks_keywords on app.kb_chunks using gin (tsv);
create index kb_chunks_clinic on app.kb_chunks (clinic_id, status);

-- ---------------------------------------------------------------------------------------------
-- Questions the bot could not answer (medical, no match, LLM answer rejected), for KB review.
-- ---------------------------------------------------------------------------------------------
create table app.unanswered_questions (
  id            bigint generated always as identity primary key,
  clinic_id     text not null references app.clinics (id),
  question_text text not null check (length(trim(question_text)) between 1 and 1000),
  lang          text not null default 'en' check (lang in ('en', 'hinglish')),
  reason        text not null check (reason in ('medical', 'no_match', 'llm_rejected')),
  lead_id       uuid,
  session_id    text,
  reviewed      boolean not null default false,
  created_at    timestamptz not null default now(),
  foreign key (lead_id, clinic_id) references app.leads (id, clinic_id) on delete set null (lead_id)
);

create index unanswered_review on app.unanswered_questions (clinic_id, reviewed, created_at desc);

create trigger kb_documents_touch before update on app.kb_documents for each row execute function app.touch_updated_at();
create trigger kb_chunks_touch before update on app.kb_chunks for each row execute function app.touch_updated_at();

alter table app.chat_sessions enable row level security;
alter table app.chat_messages enable row level security;
alter table app.kb_documents enable row level security;
alter table app.kb_chunks enable row level security;
alter table app.unanswered_questions enable row level security;
