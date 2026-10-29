-- 0029 Login & security → Main BB Admin: one email that always has full BB Admin power over every clinic (an
-- owner account). Nobody can disable, remove or demote it in Team & access; only the main BB Admin changes it
-- (any BB Admin sets the first one). One row; every change is logged.
create table app.platform (
  id             smallint primary key default 1 check (id = 1),
  main_bb_email  text check (main_bb_email = lower(main_bb_email) and main_bb_email ~ '^[^@\s]+@[^@\s]+\.[^@\s]{2,}$'),
  updated_by     uuid references app.profiles (id) on delete set null,
  updated_at     timestamptz not null default now()
);
insert into app.platform (id) values (1);

-- Not readable from the browser; the backend answers who the main BB Admin is.
alter table app.platform enable row level security;
create trigger platform_audit after insert or update or delete on app.platform
  for each row execute function app.audit_row();
create trigger platform_touch before update on app.platform
  for each row execute function app.touch_updated_at();
