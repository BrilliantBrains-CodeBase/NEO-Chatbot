-- 0017 The 0016 trigger function was runnable by everyone (Postgres grants new functions to public).
-- Triggers fire without that right, so it is taken away like for every other function in app.
revoke all on function app.kb_qa_reset_embedding() from public, anon, authenticated;
