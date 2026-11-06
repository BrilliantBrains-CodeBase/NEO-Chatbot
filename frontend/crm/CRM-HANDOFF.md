# NEO CRM: handoff for the next developer or AI agent

Read this first, then `AGENTS.md` (Next.js rules) and `README.md`. Last updated 24 Oct 2026, after sub-step 2.

## 1. What this is

NEO CRM is the staff app for three clinics run by NEO Group (Bengaluru), built by Brilliant Brains:

| Clinic id | Clinic | Chatbot |
|---|---|---|
| NFHT | Neo Follicle (hair transplant) | Arya |
| CL02 | Neo Fertility | Navya |
| CL03 | Derma Solutions | Diya |

Leads come from the website chatbots (already built: `frontend/widgets` + `backend/`), Meta and Google ads (via
Google Sheets), WhatsApp and manual entry. Staff handle leads, approve chatbot booking requests, manage
appointments and doctors' availability. Only NFHT has live chatbot data today.

## 2. Rules from the client (do not break)

- **Work one by one.** Build one small sub-step, show what changed and how to see it, then stop and wait for
  the user's "next". Keep replies short; the user is saving credits.
- **Never `git commit` or push without the user's explicit OK** for that commit. Propose the message first.
- **Screens first, then connect.** Each screen is built to match the design, then wired to live data. The user
  now wants **live data, not sample data**, starting with the Dashboard.
- **All CRM <-> backend data is JSON only.**
- **No LLM** in the chatbot; it never trains itself (new answers only through staff approval).
- Patient-facing email for now (Gmail SMTP); WhatsApp (Interakt) later. No paid services for patient messages.
- Every export, delete and stage change is audit-logged. Each clinic's staff see only their clinic.

## 3. Stack and commands

`frontend/crm`: **Next.js 16.4.3, React 19.3, TypeScript**, App Router, `src/`, no UI framework.

```bash
cd frontend/crm
npm install
npm run dev        # http://localhost:3000  (sign-in: http://localhost:3000/sign-in)
npm run typecheck && npm run lint && npm run build
```

The repo pre-commit hook (`.githooks/pre-commit`) runs CRM typecheck, lint and build when `frontend/crm/`
changes. Backend: `cd backend && uv run uvicorn app.main:app --port 8000` (FastAPI, Python, `uv`).

**This Next.js is newer than most training data.** Read `node_modules/next/dist/docs/` before framework code:
- middleware is now **`proxy`** (`docs/01-app/01-getting-started/16-proxy.md`);
- `next.config.ts` has `cacheComponents` and `partialPrefetching` on, and dev **validates instant navigation**:
  - parts that depend on the current time (dates, "5m ago") go inside `<Live>` (`src/components/crm/Live.tsx`,
    uses React 19.3 `use(browser())` inside `<Suspense>`). Never call `new Date()` in a component that
    renders during prerender;
  - a screen that reads the address (`useSearchParams`, e.g. `?stage=`, `?doc=`) renders that part inside
    `<Suspense>` (see `src/app/(crm)/doctors/page.tsx` + `DoctorsView.tsx`);
  - lint forbids `setState` directly in `useEffect`; use `useSyncExternalStore` (see `CrmProvider.tsx`).
- Typed route props: `LayoutProps<"/">` etc. are global helpers.

**Env:** all keys live in **`backend/.env`** (user's choice, one file). `next.config.ts` reads ONLY the
`NEXT_PUBLIC_` lines from it (`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, both set and
verified). Never let the CRM load the database URL or other backend secrets. Never print key values.

## 4. Designs (match them exactly)

- **CRM screens:** https://claude.ai/artifact/BHvewwn4fbDkVWC14z2Lhe (font Inter)
- **Sign-in pages:** https://claude.ai/artifact/YQfCYReoHxYCUwtVgn8MWW (font Figtree)

They are single HTML pages rendered by JavaScript, so a summary misses most of it. Read the saved raw HTML and
the app script (`(function(){ ... })()`, about 512 lines): screen functions `dash`, `appt` (Leads), `reqView`
+ `approval` (Inbox), `docsView`/`docPage`, `calView` (Appointments), `patView` + `openExport`, `repView`,
`teamView` + `memberForm`, `setView`, `profView`, `openLead` (lead panel), `openAdd` (Add lead form). Port the
markup and rules from there. The whole design stylesheet is already ported to `src/app/(crm)/crm.css` (scoped
under `.crm`); the sign-in styles to `src/app/(auth)/auth.css` (scoped under `.auth`). Reuse their classes.

## 5. What exists (committed on `main`)

```
src/app/layout.tsx              fonts (Figtree, Inter), base
src/app/(auth)/                 sign-in, create-account, reset-password  (sub-step 1)
src/app/(crm)/layout.tsx        the frame for every CRM screen          (sub-step 2)
src/app/(crm)/<screen>/page.tsx dashboard, leads, inbox, doctors, appointments, tasks, patients,
                                reports, team, settings, profile: placeholders with the design's header
src/components/auth/            forms, icons, password field
src/components/crm/             Shell (frame, panel, pop-up, toast), Sidebar, Topbar, CrmProvider
                                (clinic, data, counts, openDrawer/openModal/toast), Icon, Live, Placeholder
src/lib/validation.ts           form rules and messages from the sign-in design
src/lib/sample-data.ts          SAMPLE data ported from the design's generator (to be replaced)
src/lib/auth-demo.ts            TEMPORARY demo sign-in (password < 8 chars = "incorrect"); remove in 3a
```

Sidebar items are routes: `/leads?stage=new|fu|bk|vi|lo`, `/inbox?tab=appt|online|cancel|resch|cb|chat`,
`/doctors?doc=<name>`. Use `useCrm()` for the panel (`openDrawer`), pop-up (`openModal`) and `toast`.

## 6. Next steps (in order)

**3a. Real sign-in (next).** The user is asked to choose A or B; **A is recommended**:
- A: sign in with Supabase Auth in the browser (`@supabase/ssr`, session in cookies, publishable key); the
  Next `proxy` sends signed-out users to `/sign-in`; every CRM call to the backend sends the token; the backend
  verifies it with Supabase's JWKS (`<SUPABASE_URL>/auth/v1/.well-known/jwks.json`) and checks an approved,
  active profile with a role for that clinic.
- New backend endpoint `GET /v1/crm/me` -> JSON `{ name, email, role(s), clinics }`. Clinic switcher shows only
  the user's clinics. Remove `auth-demo.ts`.
- **Waiting on the user:** create their login in Supabase (Authentication -> Users -> Add user, Auto Confirm)
  and tell the email; then give it the BB Admin role for NFHT-CL03 (rows in `app.profiles` + `app.user_clinics`
  with role `bb_admin`). Supabase had 0 users on 24 Oct. Ask the user to turn public sign-ups OFF.

**3b. Live Dashboard.** `GET /v1/crm/dashboard?clinic=NFHT&days=7` -> JSON for: new leads, pending Inbox
(booking, online, cancel, reschedule), callbacks waiting (+ oldest wait), follow-ups due today, today's
appointments, doctors today, leads by source, funnel (new, contacted, booked, visited), chatbot numbers
(chats, leads captured, KB answers; no "AI answers"), top treatments. Then the Dashboard screen as designed.

Then, one by one: Leads (+ lead panel, Add lead with duplicate-phone check), Inbox (+ approval with slot grid),
Appointments, Doctors Availability, Patients (+ export), Reports, Team (+ access requests), Settings, Profile.
Tasks and a "Bot quality" screen are **not designed yet**: propose a design in the same style first.

## 7. Backend and database facts

- Supabase project (Mumbai, ap-south-1). Schema `app`, row security on every table. Migrations in
  `backend/supabase/migrations` (0001-0018), run with `cd backend && uv run python -m scripts.migrate`
  (dry run) and `--apply` only after the user says yes.
- Tables: `clinics, profiles, user_clinics (role: bb_admin|clinic_manager|front_desk|doctor, in_round_robin),
  doctors, doctor_availability, doctor_leave, clinic_holidays, leads, lead_events, patients, requests,
  appointments, slot_holds, tasks, chat_sessions, chat_messages, rag_traces, kb_facts, kb_qa, intent_examples,
  unanswered_questions, outbox, audit_log`. Live NFHT data exists (leads, requests, appointments, 1 doctor).
- Existing API: `POST /v1/chat/message` (chatbot) and `/v1/health`. CRM endpoints go under `/v1/crm/...`.
  `ALLOWED_ORIGINS` in `backend/.env` must include the CRM origin (http://localhost:3000 in dev).
- Lead stages (fixed): New, Follow Up, Booked, Visited, Lost, Invalid. Lead code like `NFHT-00001`.
- Slots are 15 minutes by default (the design's 30 is wrong for this client).

## 8. Agreed flows

- **Access requests ("Create an account"):** backend creates the Supabase login + a Pending row in a new
  `access_requests` table; no CRM access until approved. Shown in Team -> Access requests to that clinic's
  Clinic Manager and BB Admin. **Only BB Admin approves Clinic Manager requests**; Manager or BB Admin approve
  Front Desk. Approve as a role (may change it) -> active + email; Reject -> login removed + email. Audit-logged.
  No manager email alert for new requests yet.
- **Chatbot booking request:** pending in Inbox, its slot hidden from the chatbot; staff approve (lead ->
  Booked), approve with change (other slot/doctor/length) or reject with reason (patient offered a callback).
  Online consult approval creates a Google Meet link (later).
- **Callbacks:** oldest first, red after 60 min; Answered (New -> Follow Up), No answer/Busy (attempt +1, stays),
  Wrong number (Invalid); after 3 unanswered tries suggest Lost.
- **Appointments:** Confirmed -> Visited (lead Visited) / No-show (lead Follow Up, call tomorrow) / Cancelled.
- **Lead assignment:** round robin among active Front Desk; Clinic Manager can reassign.
- **Roles (design's permission table):** Front Desk cannot export, see Reports, manage Team or Settings;
  Doctors see only their own appointments and schedule; Settings and switching clinics are BB Admin only.

## 9. Design points still to confirm with the user

"AI answered" stats in the design (there is no LLM: rename or drop); WhatsApp confirmations (send email for
now); Tasks and Bot quality screens (not designed).
