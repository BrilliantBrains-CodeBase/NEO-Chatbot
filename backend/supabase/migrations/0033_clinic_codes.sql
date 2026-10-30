-- 0033 More clinics: codes CL01–CL99 (today's) and CL100–CL999 (new ones get three digits).
alter table app.clinics drop constraint clinics_id_check;
alter table app.clinics add constraint clinics_id_check check (id ~ '^CL[0-9]{2,3}$');
