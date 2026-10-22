-- 0016 Semantic matching: kb_qa.embedding holds the meaning of a question and its wordings (bge-small-en-v1.5,
-- 384 numbers), filled by the backend. When staff change the question or wordings, the old meaning is
-- cleared here so the backend recalculates it; the bot never matches on outdated wording.
create function app.kb_qa_reset_embedding() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.question is distinct from old.question or new.variants is distinct from old.variants then
    new.embedding := null;
  end if;
  return new;
end;
$$;
create trigger kb_qa_reset_embedding before update on app.kb_qa
  for each row execute function app.kb_qa_reset_embedding();
