-- 0034 Main template: CL01's canvas, Templates and Appearance are the main template. Other clinics FOLLOW it
-- (each part on its own) until they change that part, which then becomes their own ("Follow main again"
-- undoes it). CL01 publishes either for itself only, or for all: "shared" holds the main's for-all version
-- of those parts, which following clinics show (with their own clinic and bot name).
alter table app.clinic_settings
  add column follows text[] not null default '{}'
    check (follows <@ array['flow', 'template', 'appearance']),
  add column shared jsonb check (shared is null or jsonb_typeof(shared) = 'object');

-- Today: the main's current live version is the for-all version; BB Fertility follows all three parts.
update app.clinic_settings
   set shared = jsonb_build_object('flow', published->'flow', 'template', published->'template',
                                   'appearance', published->'appearance')
 where clinic_id = 'CL01';
update app.clinic_settings set follows = array['flow', 'template', 'appearance'] where clinic_id = 'CL02';
