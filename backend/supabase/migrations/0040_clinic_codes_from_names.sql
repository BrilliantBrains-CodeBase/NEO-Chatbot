-- 0040 Clinic codes come from the clinic's name: the first letter of each word (Neo Follicle Hair Transplant:
-- NFHT), with a number added when that code is taken (BF, BF2). The old CL01-style codes stay valid, so the
-- hidden test clinics (CL98, CL99) keep theirs.
--
-- app.rename_clinic(old, new) moves everything of a clinic to a new code at once: the clinic, every row of
-- every table that holds its clinic_id, its lead codes (CL01-00003 becomes NFHT-00003) and the audit log's
-- references to them. It checks that nothing is left under the old code and records the rename in the audit
-- log. The backend still accepts the old code where outside systems may send it (see app/core/codes.py).
--
-- Renamed here: Neo Follicle (CL01) becomes Neo Follicle Hair Transplant (NFHT), with its details from
-- neofollicletransplant.com; BB Fertility (CL02) becomes BF.

alter table app.clinics drop constraint clinics_id_check;
alter table app.clinics add constraint clinics_id_check check (id ~ '^[A-Z][A-Z0-9]{1,9}$');

create function app.rename_clinic(old_id text, new_id text) returns void
language plpgsql
set search_path = ''
as $$
declare
  t record;
  left_over bigint;
  links jsonb;
  triggers jsonb;
begin
  if not exists (select 1 from app.clinics where id = old_id) then
    raise exception 'Clinic % does not exist.', old_id;
  end if;
  if exists (select 1 from app.clinics where id = new_id) then
    raise exception 'Clinic code % is already taken.', new_id;
  end if;
  if new_id !~ '^[A-Z][A-Z0-9]{1,9}$' then
    raise exception 'Clinic code % is not valid (2 to 10 capital letters or digits, starting with a letter).', new_id;
  end if;

  -- One consistent move, inside this transaction. The links between tables that hold the clinic code are
  -- dropped and made again afterwards (which checks every row again); the tables' own triggers (the lead
  -- identity guard, the audit log's guard and its per-row records) are paused, each by name, and the ones that
  -- were on are switched on again.
  select coalesce(jsonb_agg(jsonb_build_object('t', conrelid::regclass::text, 'n', conname,
           'd', pg_get_constraintdef(oid))), '[]'::jsonb)
    into links
    from pg_constraint k
   where k.contype = 'f' and k.connamespace = 'app'::regnamespace
     and (k.confrelid = 'app.clinics'::regclass
          or exists (select 1 from unnest(k.conkey) a join pg_attribute p
                       on p.attrelid = k.conrelid and p.attnum = a where p.attname = 'clinic_id'));
  for t in select x->>'t' tab, x->>'n' con from jsonb_array_elements(links) x loop
    execute format('alter table %s drop constraint %I', t.tab, t.con);
  end loop;

  select coalesce(jsonb_agg(jsonb_build_object('t', g.tgrelid::regclass::text, 'n', g.tgname,
           'm', case g.tgenabled when 'A' then 'always ' when 'R' then 'replica ' else '' end)), '[]'::jsonb)
    into triggers
    from pg_trigger g
   where not g.tgisinternal and g.tgenabled <> 'D'
     and (g.tgrelid = 'app.clinics'::regclass
          or g.tgrelid in (select format('app.%I', c.table_name)::regclass from information_schema.columns c
                           join information_schema.tables b
                             on b.table_schema = c.table_schema and b.table_name = c.table_name
                           where c.table_schema = 'app' and c.column_name = 'clinic_id'
                             and b.table_type = 'BASE TABLE'));
  for t in select x->>'t' tab, x->>'n' trg from jsonb_array_elements(triggers) x loop
    execute format('alter table %s disable trigger %I', t.tab, t.trg);
  end loop;

  for t in
    select c.table_name from information_schema.columns c
    join information_schema.tables b on b.table_schema = c.table_schema and b.table_name = c.table_name
    where c.table_schema = 'app' and c.column_name = 'clinic_id' and b.table_type = 'BASE TABLE'
  loop
    execute format('update app.%I set clinic_id = $1 where clinic_id = $2', t.table_name) using new_id, old_id;
  end loop;
  update app.clinics set id = new_id where id = old_id;
  update app.leads set lead_code = new_id || substr(lead_code, length(old_id) + 1)
   where clinic_id = new_id and lead_code like old_id || '-%';
  update app.audit_log set row_id = new_id || substr(row_id, length(old_id) + 1)
   where row_id like old_id || '-%';

  for t in select x->>'t' tab, x->>'n' trg, x->>'m' mode from jsonb_array_elements(triggers) x loop
    execute format('alter table %s enable %strigger %I', t.tab, t.mode, t.trg);  -- as it was
  end loop;
  for t in select x->>'t' tab, x->>'n' con, x->>'d' def from jsonb_array_elements(links) x loop
    execute format('alter table %s add constraint %I %s', t.tab, t.con, t.def);
  end loop;

  -- Nothing may stay behind under the old code.
  for t in
    select c.table_name from information_schema.columns c
    join information_schema.tables b on b.table_schema = c.table_schema and b.table_name = c.table_name
    where c.table_schema = 'app' and c.column_name = 'clinic_id' and b.table_type = 'BASE TABLE'
  loop
    execute format('select count(*) from app.%I where clinic_id = $1', t.table_name) into left_over using old_id;
    if left_over > 0 then
      raise exception 'Rename % to %: % rows left in app.%.', old_id, new_id, left_over, t.table_name;
    end if;
  end loop;
  if exists (select 1 from app.leads where lead_code like old_id || '-%') then
    raise exception 'Rename % to %: lead codes left under the old code.', old_id, new_id;
  end if;

  insert into app.audit_log (clinic_id, table_name, row_id, action, actor, changed)
  values (new_id, 'clinics', new_id, 'update', auth.uid(), jsonb_build_object('id', jsonb_build_array(old_id, new_id)));
end;
$$;
revoke all on function app.rename_clinic(text, text) from public, anon, authenticated;

select app.rename_clinic('CL01', 'NFHT');
select app.rename_clinic('CL02', 'BF');

-- Neo Follicle Hair Transplant's details, as on neofollicletransplant.com (phone, WhatsApp, website and hours
-- were already right).
update app.clinics set
  name        = 'Neo Follicle Hair Transplant',
  email       = 'info@neofollicletransplant.com',
  address     = '1st floor, Scorpio House, Near Marathahalli Bridge, Munnekolala, Opposite Purvankara Apt, '
                || 'Marathahalli Bridge Service Road',
  city        = 'Bengaluru',
  state       = 'Karnataka',
  postal_code = '560037',
  country     = 'India'
where id = 'NFHT';
