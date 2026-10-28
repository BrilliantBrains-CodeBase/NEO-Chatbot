-- 0020 Dashboard → Website install: the websites a clinic's chatbot may run on. A site is added as pending
-- and only an approved one is copied into app.clinics.allowed_origins, which the chat already checks on every
-- message (any other site is refused). The pages rule says where on the site the bot shows.
-- New table only; allowed_origins keeps today's values until a site here is approved or removed.
create table app.clinic_websites (
  id           uuid primary key default gen_random_uuid(),
  clinic_id    text not null references app.clinics (id),
  origin       text not null check (origin ~ '^https://[a-z0-9.-]+(:[0-9]{2,5})?$'), -- e.g. https://neofollicle.com
  status       text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
  pages_mode   text not null default 'all' check (pages_mode in ('all', 'only', 'except')),
  pages        text[] not null default '{}' check (cardinality(pages) <= 50), -- paths, e.g. /hair-transplant/*
  added_by     uuid references app.profiles (id) on delete set null,
  decided_by   uuid references app.profiles (id) on delete set null,
  decided_at   timestamptz,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  unique (clinic_id, origin),
  check ((status = 'pending') = (decided_at is null))
);

-- CRM: managers of the clinic read; changes go through the backend (which also updates allowed_origins).
alter table app.clinic_websites enable row level security;
grant select on app.clinic_websites to authenticated;
create policy clinic_websites_read on app.clinic_websites for select to authenticated
  using (app.can_manage(clinic_id));

create trigger clinic_websites_audit after insert or update or delete on app.clinic_websites
  for each row execute function app.audit_row();
create trigger clinic_websites_touch before update on app.clinic_websites
  for each row execute function app.touch_updated_at();

-- The sites allowed today (e.g. CL01's) come in approved, so nothing stops working.
insert into app.clinic_websites (clinic_id, origin, status, decided_at)
select c.id, o, 'approved', now()
from app.clinics c, unnest(c.allowed_origins) as o
where o ~ '^https://[a-z0-9.-]+(:[0-9]{2,5})?$';
