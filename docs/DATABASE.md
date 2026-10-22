# Database plan (Supabase)

How the one Supabase database is set up, structured, protected and kept healthy. It serves the 3 chatbots, the backend and NEO CRM. Design context: [RAG-AND-LEADS.md](RAG-AND-LEADS.md).

---

## 1. Setup

| Item | Decision |
|---|---|
| Projects | **One** Supabase project for live data (created in Mumbai on 21 Oct 2026; the earlier Singapore project is to be deleted) |
| Region | **Mumbai (ap-south-1)**: patient data stays in India (DPDP Act 2023) and sits next to the Linode Mumbai server |
| Plan | **Free** while building, **Pro before go-live** (Free pauses after 7 idle days and has no backups) |
| Development and tests | The **same cloud project**, using the hidden test clinic **CL99** only. Tests create their rows under CL99 and delete them afterwards; CL99 is excluded from every report and from the CRM clinic switcher |
| Redis | **Phase 2.** Until then: chat session state in `chat_sessions.state` (jsonb), slot holds in a `slot_holds` table (`expires_at`, unique per doctor and start time), rate limits in memory per server process |
| Schema changes | Only through numbered migration files, applied by `backend/scripts/migrate.py` (dry run by default, `--apply` to apply; each file once, in one transaction, refused if edited after applying). Take a backup first |
| Extensions | `vector` (pgvector), `pg_trgm` (fuzzy name search), `btree_gist` (no double booking), `pg_cron` (scheduled clean-up), `pgcrypto` (UUIDs) |

Because there is only one project, test data lives only under clinic `CL99`. The test setup refuses to run unless every row it writes uses `CL99`, and removes those rows when it finishes.

## 2. Who connects, and how

| Client | Connects with | Can do |
|---|---|---|
| Widgets | Never connect to Supabase. They talk only to the backend | Nothing directly |
| Backend (FastAPI, workers) | Postgres **connection string** through the Supavisor pooler (transaction mode, port 6543), as a dedicated `app_backend` role | Read and write all app tables. The connection string lives only in `backend/.env` |
| NEO CRM | **Publishable key** (`sb_publishable_...`) with Supabase Auth (email and password) for sign-in and Realtime for live alerts; data reads and writes through the backend CRM API with the user's token | Only what Row Level Security allows for that user |
| Admin (BB) | Supabase dashboard, migrations | Everything; actions in the app are audited |

- The `anon` role gets **no** access to any app table.
- The `service_role` key is never sent to a browser.
- Every table has Row Level Security turned on, even tables the CRM reads only through the backend. If a key leaks, the database still blocks access.

## 3. Conventions

- **Names**: `snake_case`, plural table names (`leads`, `appointments`).
- **Primary keys**: `uuid` with `default gen_random_uuid()`. Exception: `clinics.id` is the readable code `CL01`, `CL02`, `CL03`.
- **Clinic**: every clinic-owned row has `clinic_id text not null references clinics(id)`, and every query filters by it.
- **Time**: `timestamptz`, stored in UTC, shown in India time (`Asia/Kolkata`). Dates without time (leave days, booked date) use `date`.
- **Audit columns**: `created_at`, `updated_at` (set by one shared trigger), `created_by`, `updated_by` (user ID or `system`).
- **Fixed lists** (stage, status, role, source): `text` with a `check` constraint, so the database rejects any other value. Changing a list is a migration, which keeps reports comparable.
- **Phone**: stored in E.164 (`+919876543210`), with the country code and number also kept for display. **Email**: stored in lower case.
- **Money**: never stored as float. Amounts in rupees as `integer`.
- **No hard delete** of leads or appointments by staff. Rows get `deleted_at`, and only BB Admin or Clinic Manager can do it. Patient deletion requests (section 9) are the exception: those are real deletes.

## 4. Tables

### 4.1 Clinic and people

| Table | Key columns |
|---|---|
| `clinics` | `id` (CL01), `name`, `bot_name`, `timezone` (Asia/Kolkata), `hours` jsonb (per weekday open and close), `closed_weekdays` int[], `slot_minutes` (15), `booking_window_days` (14), `booked_date_back_days` (60), `last_slot_before_close_min` (30), `next_lead_no` (counter for lead codes), `phone`, `whatsapp`, `allowed_origins` text[], `widget_config` jsonb, `active` |
| `profiles` | `id` = `auth.users.id`, `full_name`, `email`, `phone`, `active`, `last_seen_at` |
| `user_clinics` | `user_id`, `clinic_id`, `role` (`bb_admin`, `clinic_manager`, `front_desk`, `doctor`), `in_round_robin` bool, `rr_last_assigned_at`. Unique `(user_id, clinic_id)` |
| `doctors` | `clinic_id`, `user_id` (nullable, set when the doctor has a login), `name`, `role_title`, `qualifications`, `profile` jsonb (stats, links), `sort_order`, `active` |
| `doctor_availability` | `doctor_id`, `clinic_id`, `weekday` (0 to 6), `mode` (`in_clinic`, `online`), `start_time`, `end_time`. Check: start before end |
| `doctor_leave` | `doctor_id`, `clinic_id`, `from_date`, `to_date`, `reason`. Check: from not after to |

### 4.2 Leads and work

All leads from all clinics are kept **in one place, the `leads` table**. Each lead is tagged with its clinic code (`CL01` Neo Follicle, `CL02` Neo Fertility, `CL03` Derma Solutions) and gets a readable lead code made from it: `CL01-00001`, `CL01-00002`, `CL02-00001` and so on. Staff use this code on calls and in notes; the database still links rows by `id`.

| Table | Key columns |
|---|---|
| `leads` | `lead_code` (readable, for example `CL01-00001`), `clinic_id`, `full_name`, `phone_e164`, `phone_cc`, `email`, `source` (`chatbot`, `meta_ads`, `google_ads`, `manual`, `whatsapp`), `campaign`, `treatment`, `doctor_id`, `appointment_type`, `stage` (`new`, `follow_up`, `booked`, `visited`, `lost`, `invalid`), `stage_reason`, `assigned_to`, `contact_count`, `first_contact_at`, `last_contact_at`, `page_url`, `device`, `consent_at`, `verified` (OTP, later), `patient_id`, `notes`, `deleted_at` |
| `requests` | `clinic_id`, `lead_id`, `type` (`book`, `online`, `cancel`, `reschedule`, `callback`, `question`), `status` (`pending`, `done`, `rejected`), `data` jsonb (everything the patient entered), `match_status` (`matched`, `no_match`, for cancel and reschedule), `matched_appointment_id`, `question_text`, `session_id` |
| `appointments` | `clinic_id`, `lead_id`, `request_id`, `doctor_id`, `type` (`in_clinic`, `online`), `slot` tstzrange (start and end), `preferred_window` (for "Any time"), `status` (`pending`, `confirmed`, `rejected`, `cancelled`, `rescheduled`, `visited`, `no_show`, `missed`), `rescheduled_from_id`, `meet_link`, `calendar_event_id`, `confirmed_by`, `confirmed_at` |
| `patients` | `clinic_id`, `full_name`, `phone_e164`, `email`, `first_visit_at`, `notes`. Created when a lead reaches `visited` |
| `tasks` | `clinic_id`, `lead_id`, `appointment_id`, `type` (`call_new_lead`, `retry_call`, `confirm_booking`, `custom`), `due_at`, `assigned_to`, `status` (`open`, `done`, `cancelled`), `attempt` (1 to 3), `outcome` (`answered`, `no_answer`, `busy`, `wrong_number`), `escalated_at` |
| `lead_events` | `clinic_id`, `lead_id`, `kind` (`contact`, `stage_change`, `assigned`, `call`, `note`, `request`), `data` jsonb, `actor`. The lead's timeline in the CRM |

### 4.3 Chatbot and knowledge base

| Table | Key columns |
|---|---|
| `chat_sessions` | `id` (the widget's `session_id`), `clinic_id`, `visitor_id`, `lead_id`, `started_at`, `last_at`, `device`, `page_url` |
| `chat_messages` | `session_id`, `clinic_id`, `role` (`patient`, `bot`), `text`, `event`, `ui_type`, `answered_by` (`flow`, `rule`, `kb`, `llm`, `lead`), `created_at`. **Deleted after 3 days** |
| `kb_documents` | `clinic_id`, `file_name`, `storage_path`, `version`, `status` (`draft`, `approved`, `retired`), `approved_by`, `approved_at` |
| `kb_chunks` | `clinic_id`, `document_id`, `title`, `text`, `category`, `page`, `embedding` vector(384), `tsv` tsvector (generated from title and text), `status` |
| `unanswered_questions` | `clinic_id`, `question_text`, `lang`, `reason` (`medical`, `no_match`, `llm_rejected`), `lead_id`, `reviewed` |

### 4.4 System

| Table | Key columns |
|---|---|
| `outbox` | `clinic_id`, `channel` (`whatsapp`, `email`, `calendar`), `payload` jsonb, `status` (`queued`, `sent`, `failed`), `attempts`, `next_try_at`, `last_error` |
| `audit_log` | `clinic_id`, `table_name`, `row_id`, `action` (`insert`, `update`, `delete`, `export`), `actor`, `before` jsonb, `after` jsonb, `at`. Insert only: no one can update or delete it |
| `settings_history` | Changes to clinic settings (slot length, window, hours), with who and when |

## 5. Rules the database enforces

These hold even if the application has a bug.

| Rule | How |
|---|---|
| One lead per person per clinic | Unique index on `leads (clinic_id, phone_e164) where deleted_at is null` |
| Readable lead code | A trigger sets `lead_code` = clinic code + `-` + the clinic's next number (5 digits), taken from `clinics.next_lead_no` with a row lock, so two leads arriving at once never get the same code. Unique index on `lead_code`; the code never changes |
| No double booking | Exclusion constraint on `appointments`: same `doctor_id` and overlapping `slot` are rejected while status is `pending` or `confirmed` (`btree_gist`) |
| A slot belongs to its clinic's doctor | Composite foreign key `(doctor_id, clinic_id)` references `doctors (id, clinic_id)`. The same pattern applies to every child table, so no row can point across clinics |
| Valid values only | `check` constraints on every stage, status, role, source and type column |
| Valid phone | `check (phone_e164 ~ '^\+[1-9][0-9]{6,14}$')` |
| Lost and Invalid need a reason | `check (stage not in ('lost','invalid') or stage_reason is not null)` |
| Tries limit | `check (attempt between 1 and 3)` |
| Audit log cannot change | No update or delete grant on `audit_log` for any app role |

## 6. Indexes

| Table | Index | Used by |
|---|---|---|
| leads | `(clinic_id, stage, last_contact_at desc)` | Leads list and dashboard |
| leads | `(clinic_id, assigned_to, stage)` | "My leads" |
| leads | `(clinic_id, lower(email))` | Lead matching by email |
| leads | GIN trigram on `full_name` | Search by name |
| leads | unique `lead_code` | Search by lead code |
| appointments | `(clinic_id, doctor_id, lower(slot))` | Free slot lookup and calendar |
| appointments | `(clinic_id, status, lower(slot))` | Pending queue, Missed job |
| tasks | `(clinic_id, assigned_to, status, due_at)` | Task list and overdue check |
| requests | `(clinic_id, type, status, created_at desc)` | Inbox tabs |
| chat_messages | `(session_id, created_at)` and `(created_at)` | Transcript view and the 3-day clean-up |
| kb_chunks | HNSW on `embedding vector_cosine_ops`, GIN on `tsv`, btree `(clinic_id, status)` | Hybrid search |
| outbox | `(status, next_try_at)` | Worker queue |

No extra indexes until a slow query shows the need. Each index slows writes and uses space on the Free plan's 500 MB.

## 7. Row Level Security

Two helper functions (`security definer`, `stable`, fixed `search_path`), used by every policy:
- `app.my_clinics()` returns the clinic IDs of the signed-in user (all clinics for `bb_admin`).
- `app.my_role(clinic_id)` returns the user's role in that clinic.

| Table | Read | Write |
|---|---|---|
| clinics | Own clinics | BB Admin; Clinic Manager for own clinic settings |
| leads, requests, tasks, lead_events, patients | Own clinics, roles other than doctor | Own clinics, roles other than doctor |
| appointments | Own clinics; a doctor only their own rows | Front Desk, Clinic Manager, BB Admin |
| doctor_availability, doctor_leave | Own clinics | Front Desk and above; a doctor only their own rows |
| chat_sessions, chat_messages | Own clinics, roles other than doctor | Backend only |
| kb_documents, kb_chunks | Own clinics, Clinic Manager and above | Backend only (upload); approve by Clinic Manager and above |
| user_clinics, profiles | Own row; managers see their clinic's team | BB Admin; Clinic Manager for own clinic (not `bb_admin` rows) |
| audit_log | BB Admin; Clinic Manager for own clinic | Triggers only |
| outbox, unanswered_questions | BB Admin, Clinic Manager | Backend only |

Realtime alerts use the same policies, so a Front Desk user at Derma never receives a Neo Fertility alert.

Every policy has a test: each role signs in to the local database and tries to read and write rows of its own clinic and of another clinic.

## 8. Automatic jobs

| Job | Where | Schedule |
|---|---|---|
| Delete `chat_messages` older than 3 days, then empty `chat_sessions` | `pg_cron` | Daily 03:00 IST |
| Mark `pending` appointments whose slot has started as `missed` | `pg_cron` | Every 15 minutes |
| Escalate pending bookings older than 2 working hours | Backend worker (needs clinic hours logic) | Every 5 minutes |
| Create retry call tasks, close leads after 3 failed tries | Backend worker | On call outcome, plus every 15 minutes |
| Send outbox (WhatsApp, email, calendar) | Backend worker | Continuous |
| Nightly backup (section 10) | Linode cron | Daily 02:00 IST |

## 9. Retention and patient requests

| Data | Kept |
|---|---|
| Leads, requests, appointments, patients, tasks, lead timeline | Kept (no automatic deletion) |
| Chat transcripts | **3 days** (client decision, 22 Oct 2026), then deleted. The lead keeps the request and the patient's question |
| Unanswered questions | 90 days (for improving the knowledge base), with name and phone removed |
| Audit log | Kept |
| Outbox | Sent items removed after 30 days |

**Patient deletion request** (DPDP Act): BB Admin or Clinic Manager runs "Delete patient data" on the lead. One database function deletes the lead's chats, requests, tasks and timeline. It also removes name, phone and email from appointments, which are kept as anonymous counts for reports. The action is written to the audit log without the deleted details.

**Export**: only BB Admin and Clinic Manager. Every export is written to the audit log (who, which filters, how many rows).

## 10. Backups and recovery

| Stage | Backup |
|---|---|
| Free plan (now) | Supabase has none, so a Linode cron job runs `pg_dump` every night. It encrypts the file, stores it off the server (Linode Object Storage, Mumbai) and keeps 14 days |
| Pro plan (go-live) | Supabase daily backups (7 days) **plus** the same nightly dump. Point-in-time recovery is an optional add-on |
| Restore test | Once a month, restore the latest dump into a temporary Postgres and check the row counts |

Before any migration on live: take a fresh dump first.

## 11. Migrations

```
backend/supabase/migrations/
  0001_extensions.sql        vector, pg_trgm, btree_gist, pg_cron, pgcrypto
  0002_core.sql              clinics, profiles, user_clinics, doctors, availability, leave
  0003_leads.sql             leads, requests, appointments, patients, tasks, lead_events
  0004_chat_kb.sql           chat tables, knowledge base, unanswered questions
  0005_system.sql            outbox, audit_log, settings_history, triggers
  0006_rls.sql               helper functions and every policy
  0007_jobs.sql              pg_cron jobs
backend/supabase/seed.sql    CL01 to CL03 settings and doctors only. No fake patients
```

- A migration file is never edited after it reaches live. A fix is a new file.
- Each migration runs on a fresh local database in CI, together with the RLS tests.
- README and the design docs mention `001_core.sql`. These names replace them when the backend is built.

## 12. Space on the Free plan

| Item | Estimate |
|---|---|
| Knowledge base | About 3,000 chunks × (384-number vector + text) ≈ 10 MB |
| Leads and appointments | About 2 KB a row; 50,000 leads ≈ 100 MB |
| Chats | Only 3 days kept ≈ under 10 MB |
| Total | Well under the 500 MB Free limit; Pro gives 8 GB |

## 13. Still to confirm

- Upgrade date to Pro (it must happen before the first real patient lead).
- Linode Object Storage for backups (comes with the Linode account).
- Whether the clinics want automatic deletion of old leads in future (for example after 3 years of no contact). It is not switched on now.
