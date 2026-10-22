-- 0015 How every typed question was answered, step by step, for the CRM "Bot quality" screen:
-- which layer answered (emergency, medical, rule, knowledge base, LLM, lead), the knowledge base match
-- and its score, and how long each step took. Deleted with its chat session (3 days, or a patient data
-- deletion). Written by the backend only; clinic managers read.
create table app.rag_traces (
  id          bigint generated always as identity primary key,
  clinic_id   text not null references app.clinics (id),
  session_id  text not null references app.chat_sessions (id) on delete cascade,
  question    text not null check (length(question) between 1 and 500),
  answered_by text not null check (answered_by in ('emergency', 'medical', 'rule', 'kb', 'llm', 'lead', 'flow')),
  kb_qa_id    uuid references app.kb_qa (id) on delete set null,
  kb_score    real check (kb_score between 0 and 100),
  -- [{"step": "rules", "result": "no match", "ms": 1}, {"step": "kb_regular", "result": "...", "score": 92}]
  steps       jsonb not null default '[]'::jsonb check (jsonb_typeof(steps) = 'array'),
  total_ms    integer not null check (total_ms >= 0),
  created_at  timestamptz not null default now()
);
create index rag_traces_clinic on app.rag_traces (clinic_id, created_at desc);
create index rag_traces_answered on app.rag_traces (clinic_id, answered_by, created_at desc);
create index rag_traces_session on app.rag_traces (session_id);

alter table app.rag_traces enable row level security;
grant select on app.rag_traces to authenticated;
create policy rag_traces_read on app.rag_traces for select to authenticated using (app.can_manage(clinic_id));
