# NEO Chatbot and NEO CRM

Website chatbots and a shared clinic CRM for the NEO Group clinics, built by **Brilliant Brains**.

| Clinic ID | Clinic | Website | Chatbot |
|---|---|---|---|
| NFHT | Neo Follicle | neofollicletransplant.com | Arya AI |
| CL02 | Neo Fertility | neofertility.co.in | Navya AI |
| CL03 | Derma Solutions | dermasolutions.co.in | Diya AI |
| CL04 | Clinic 4 | Placeholder | Added later by config |

One database and one server serve all clinics. Every lead and every knowledge base entry is stored with its clinic ID, and the widget sends the same ID as `client_id`.

Patients use the chatbot to book (in-clinic or online), cancel, reschedule, request a callback, explore treatments and reach the clinic. Every conversation becomes a lead in **NEO CRM**, where clinic staff approve bookings, manage doctor availability and track patients.

---

## How it works

```
Clinic websites (3 sites, one script tag each)
        |
   3 clinic widgets (Preact, Shadow DOM, 30 to 40 KB each)
        |  JSON over HTTPS
   FastAPI backend ---- Redis (sessions, cache, rate limits, job queue)
        |
   Supabase: Postgres + pgvector + Auth + Realtime + Storage
        |
   NEO CRM (Next.js, static export) for clinic staff

External: Gemini / Groq (LLM fallback only), Interakt (WhatsApp),
          Google Calendar (Meet links), Google Sheets (ads leads), HealthPlix (ready connector)
```

### Answering pipeline (LLM is the last resort)

1. **Active flow**: the message answers the current booking step. If the patient types a question instead, it goes through the steps below, then the bot asks the same booking step again and keeps everything entered so far.
2. **Emergency check**: emergency words open the Emergency flow.
3. **Intent router**: typed text triggers the same flows as buttons (keywords, typo tolerance, entities).
4. **Exact cache**: the same question answered before.
5. **FAQ match**: semantic match to clinic-approved FAQs, answer shown word for word, or "Did you mean?".
6. **Medical guard**: no healthcare or medicine question is answered, not even general treatment information. The question is saved as a lead and the bot says the team will contact them.
7. **LLM fallback**: Gemini or Groq answers only from retrieved FAQs, strict JSON, validated.
8. **Handoff**: anything unclear becomes a callback lead.

---

## Technology stack

| Layer | Technology |
|---|---|
| Chatbot widgets | **Preact + TypeScript**, one shared core plus a separate face per clinic, Vite library build, Shadow DOM, plain CSS |
| Widget configuration | Dynamic JSON per clinic, stored in Supabase |
| Widget distribution | 3 static JavaScript files, one per clinic (`neo-fertility.js`, `neo-follicle.js`, `derma-solutions.js`) |
| CRM dashboard | **Next.js + TypeScript**, Tailwind CSS, shadcn/ui, static export |
| Backend | **Python 3.12 + FastAPI**, LangGraph for the answer pipeline |
| Database | **Supabase Postgres**, pgvector, Row Level Security |
| Auth | Supabase Auth (CRM staff) |
| Cache and queue | **Redis** (sessions, caches, rate limits, slot holds), arq worker |
| Embeddings | fastembed with `bge-small-en-v1.5` (384 dimensions, runs on CPU) |
| LLM fallback | Gemini 3.5 Flash-Lite (primary), Groq (backup), paid tier for patient data |
| Messaging | Interakt (WhatsApp confirmations, reminders, alerts, optional OTP) |
| Online consults | Google Calendar API with Google Meet links |
| Hosting | Linode 2 GB, Mumbai region, Docker Compose, Caddy (HTTPS) |
| Testing | Playwright (widget and CRM), pytest (backend) |

## Languages

| Language | Used for |
|---|---|
| **TypeScript** | Chatbot widget and NEO CRM |
| **Python** | Backend API, flows, matching, integrations, workers |
| **SQL** | Supabase schema, migrations, RLS policies, report views |
| **CSS / HTML** | Widget and CRM styling |
| **Chat language** | English only in Phase 1. All widget text lives in `i18n/en.json`, so Hindi and Kannada can be added later |

---

## Repository structure

Frontend and backend are fully separate. Each clinic has its own chatbot face, built on a shared core, so a fix in the core reaches all three while each clinic keeps its own look and features.

```
neo-chatbot/
├── frontend/
│   ├── widgets/                    # Chatbot widgets (Preact + TypeScript)
│   │   ├── core/                   # shared by all clinics
│   │   │   ├── loader.ts           # tiny launcher (under 5 KB), loads <clinic>.app.js on first open
│   │   │   ├── api.ts              # config fetch, send message, retries
│   │   │   ├── session.ts          # visitor_id and session_id (no personal data)
│   │   │   ├── renderer.tsx        # maps ui.type from the backend to components
│   │   │   ├── shadow.ts           # Shadow DOM mount and style injection
│   │   │   ├── components/         # bubble, typing dots, header, footer, launcher,
│   │   │   │                       # text bar, phone input, chips, time grid,
│   │   │   │                       # month calendar, summary, emergency
│   │   │   ├── i18n/en.json
│   │   │   └── styles/base.css
│   │   ├── neo-fertility/          # Navya AI face
│   │   │   ├── main.ts             # entry, builds dist/neo-fertility.js
│   │   │   ├── theme.css           # plum colours
│   │   │   ├── Menu.tsx            # 2-column tiles, 6 buttons
│   │   │   └── components/         # clinic-only pieces
│   │   ├── neo-follicle/           # Arya AI face
│   │   │   ├── main.ts             # builds dist/neo-follicle.js
│   │   │   ├── theme.css           # blue colours
│   │   │   ├── Menu.tsx            # 3-column cards, Emergency full row
│   │   │   └── components/         # International Patients card
│   │   ├── derma-solutions/        # Diya AI face
│   │   │   ├── main.ts             # builds dist/derma-solutions.js
│   │   │   ├── theme.css           # brown colours
│   │   │   ├── Menu.tsx            # pill quick replies
│   │   │   └── components/         # status line, quick pills, typing suggestions,
│   │   │                           # doctor carousel, week strip, month picker
│   │   ├── playground/             # dev page to open each clinic face
│   │   ├── tests/                  # Playwright flows per clinic
│   │   ├── package.json
│   │   └── vite.config.ts          # builds the 3 bundles, fails if any is over 40 KB
│   │
│   └── crm/                        # NEO CRM (Next.js + TypeScript, static export)
│       ├── app/                    # login, dashboard, leads, inbox, doctors,
│       │                           # appointments, tasks, patients, reports,
│       │                           # team, settings, profile
│       ├── components/
│       ├── lib/supabase.ts
│       └── package.json
│
├── backend/                        # FastAPI (Python)
│   ├── app/
│   │   ├── main.py
│   │   ├── core/                   # config, logging, security
│   │   ├── api/v1/                 # widget, chat, crm, admin, webhooks, health
│   │   ├── pipeline/               # LangGraph nodes: router, cache, faq, guard, llm, validate
│   │   ├── flows/                  # book, online, cancel, reschedule, callback
│   │   ├── clinics/                # per-clinic rules: menus, doctor step, extras
│   │   ├── kb/                     # embedder and in-memory FAQ index
│   │   ├── llm/                    # gemini.py, groq.py, prompts/
│   │   ├── cache/                  # versioned keys, memory and Redis caches
│   │   ├── integrations/           # sheets, interakt, google_calendar, healthplix, outbox
│   │   └── workers/                # embedding job, outbox job
│   ├── supabase/
│   │   └── migrations/             # 001_core.sql, 002_kb_pages_and_lead_fields.sql, 003_seed.sql
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
│
├── deploy/                         # docker-compose.yml, Caddyfile
└── docs/                           # chatbot guides and CRM guide (PDF)
```

### Why a shared core plus three faces

| Point | Result |
|---|---|
| Different look per clinic | Each face has its own colours, menu layout and extras |
| Light widgets | Each bundle includes only what that clinic uses, so Neo Fertility ships without the doctor carousel or week strip |
| One fix for all | Booking, phone input, time grid and the backend contract live in `core/` |
| Clinic 4 | Copy a face folder, change theme and menu, add one build entry |

Each clinic website loads only its own file. That file is the small loader (launcher only); it fetches the full widget (`neo-fertility.app.js` and so on, from the same folder) the first time the patient opens the chat:

```html
<!-- neofertility.co.in -->
<script src="https://chat.brilliantbrains.ai/neo-fertility.js" defer></script>
<!-- neofollicletransplant.com -->
<script src="https://chat.brilliantbrains.ai/neo-follicle.js" defer></script>
<!-- dermasolutions.co.in -->
<script src="https://chat.brilliantbrains.ai/derma-solutions.js" defer></script>
```

---

## Widget and backend contract

All traffic between the widget and the backend is JSON, in both directions (`Content-Type: application/json`). The widget sends every patient action to `POST /v1/chat/message`:

```json
{
  "client_id": "CL03",
  "session_id": "s_8f2a91c4",
  "visitor_id": "v_31bd77e0",
  "event": "button",
  "payload": { "action": "pick_date", "value": "2026-10-09" },
  "context": { "page_url": "https://dermasolutions.co.in/hydrafacial/", "device": "mobile", "lang": "en" }
}
```

The backend replies with what to show:

```json
{
  "messages": [{ "type": "text", "text": "What time would you prefer?" }],
  "ui": { "type": "time_grid", "slots": ["10:00", "10:30", "11:00"], "more": true, "allow_any_time": true },
  "input": { "mode": "none" },
  "quick": ["main_menu", "whatsapp"]
}
```

Events: `start`, `text`, `button`, `input`, `restart`.
UI blocks: `menu`, `chips`, `phone`, `email`, `month_calendar`, `week_strip`, `time_grid`, `doctor_carousel`, `doctor_card`, `treatment_card`, `summary`, `link_buttons`, `emergency`, `status_line`.
Input modes: `text`, `phone` (country code selector inside the bar, IN +91 by default, patient can change it), `email`, `none`.

- `doctor_card`: About Doctor profile (name, role, qualifications, stats grid, Book with / Read full profile buttons).
- `treatment_card`: treatment name, short description, "Book for <treatment>" and "Read more on our website".

---

## Clinic details (from the approved mockups)

| Clinic | Open | Closed | Clinic phone and WhatsApp | Doctors |
|---|---|---|---|---|
| Neo Fertility | Monday to Sunday, 09:30 to 18:30 | None | +91 73377 61236 | Dr. Payal Mahapatra |
| Neo Follicle | Wednesday to Monday, 10 AM to 7 PM | Tuesday | +91 97312 07940 | Dr. Sandeep Mahapatra |
| Derma Solutions | Monday and Wednesday to Sunday, 10 AM to 8 PM | Tuesday | +91 97412 23217 | Dr Sandeep Mahapatra, Dr Sumedha Tirthani, Dr Thyagaraj, Dr Chandhana Vishal N |

## Booking rules

- **Time slots are 15 minutes** inside clinic hours. Clinic staff can change the slot length later in NEO CRM.
- **Booking window is 2 weeks**: a new booking or a new reschedule date can be today up to 14 days ahead. Staff can change this later in NEO CRM.
- Past dates and the clinic's closed days are disabled in the date picker. Past times are hidden for today.
- **Last slot starts 30 minutes before closing**: Neo Fertility 9:30 AM to 6:00 PM, Neo Follicle 10:00 AM to 6:30 PM, Derma Solutions 10:00 AM to 7:30 PM. After the last slot, the calendar starts from tomorrow.
- **Phone number**: the country code is changeable. India (+91) needs 10 digits starting with 6 to 9; other countries need 6 to 12 digits.
- **Cancel and reschedule, no OTP**: the patient gives name and contact number (or email). The backend checks these against existing bookings. If they match, the request is linked to that booking. If they do not match, the request is still sent to clinic staff, marked "No matching booking", for manual approval. In both cases the patient sees the same confirmation message and staff confirm by phone.
- **Booked date picker** (cancel and reschedule, "Which date is your appointment booked for?"): allows both previous and future dates, from 2 months back up to 2 weeks ahead. Closed days stay disabled.
- Every booking, cancel, reschedule and callback becomes a lead in NEO CRM.

## Widget layout (from the approved mockups)

| Item | Desktop | Mobile |
|---|---|---|
| Panel | Floating, 380 x 580, radius 20, bottom right | Bottom sheet at 88% height with backdrop, can expand to full screen |
| Launcher | 60 px circle with unread dot, plus "Chat with us" label | 60 px circle only, sits above the site's sticky bar |
| Tap targets | Pills 40 px high | Pills 44 px high, input text 16 px so iPhone does not zoom |
| Auto open | Never auto opens the panel | Never auto opens the panel |

---

## Project plan

| Week | Work |
|---|---|
| **1** | Chatbot widgets in Preact: shared core, then the 3 clinic faces (Fertility tiles, Follicle cards, Derma pills with doctor carousel and week strip), mobile sheet, session restore, size check under 40 KB each. Step-by-step list in [WIDGET-STEPS.md](WIDGET-STEPS.md) |
| **2** | NEO CRM frontend in Next.js from the approved mockups: auth, dashboard, leads, inbox, doctors availability, appointments, patients, reports, team, settings, profile, tasks |
| **3** | Backend part 1: Supabase migrations and seed, widget config API, sessions, flows (book, online, cancel, reschedule, callback), leads and outbox |
| **4** | Backend part 2: intent router, emergency and medical guard, FAQ embeddings and matching, caching, LLM fallback with validation, CRM API |
| **5** | Integrations and testing: Google Sheets sync, Interakt messages, Google Meet links, Playwright and pytest suites, threshold tuning |
| **6** | Deploy to Linode Mumbai, load test, clinic UAT and sign-off, staff training, go live on all 3 websites |

### Phase 2 (after go-live)

- Chatbot dashboard in the CRM: bot settings, FAQ editor, unanswered questions review
- Hindi and Kannada chat
- WhatsApp OTP verification (optional, about Rs 0.115 to Rs 0.30 per OTP)
- HealthPlix sync when API access is provided
- Payment link before online consults (for example Razorpay)

---

## Documentation

- [Widget behaviour spec](frontend.md): exact bot wording, buttons and inputs for every flow on all 3 clinics
- [Widget build steps](WIDGET-STEPS.md): step-by-step checklist for the chatbot widgets
- [Backend design](docs/RAG-AND-LEADS.md): answer pipeline (LangGraph), knowledge base, slots, leads, CRM roles and tasks, integrations, database tables. Where it differs from this README, the design file wins
- Chatbot guides (PDF) for each clinic in [docs/](docs/)
- Migrations: `001_core.sql` (core schema, constraints, RLS), `002_kb_pages_and_lead_fields.sql` (treatment page knowledge, lead consent and tracking)

## Targets

| Item | Target |
|---|---|
| Widget loader | under 5 KB |
| Each clinic widget | 30 to 40 KB compressed, loaded only when opened |
| Chat reply without LLM | under 150 ms |
| LLM share of messages | under 5% |
| Server RAM | about 1.2 GB of 2 GB |

## Security and privacy

- The widget holds no API keys. On the patient's device it stores `visitor_id`, `session_id` and the visible chat of the last 3 days (dropped 3 days after the last message, cleared by Restart), so the chat survives a reload or a move to another page of the site.
- The backend checks each request origin against the clinic's allowed domains, and rate limits visitors.
- Row Level Security limits CRM users to their own clinics and roles.
- Patient data stays in India-region hosting; consent is collected in every flow (DPDP Act 2023).
- LLM providers are used on the paid tier only.

## Local setup

```bash
# backend
cd backend                                    # needs uv (docs.astral.sh/uv)
uv sync --extra dev                           # Python 3.12 and all libraries
cp .env.example .env                          # then set DATABASE_URL and SUPABASE_URL (cloud project)
uv run uvicorn app.main:app --reload          # http://localhost:8000/v1/health/ready and /docs
uv run pytest                                 # tests

# chatbot widgets
cd frontend/widgets && npm install
npm run dev                                   # playground at localhost:5173, switch clinic faces
npm run build                                 # dist/neo-fertility.js, neo-follicle.js, derma-solutions.js

# crm
cd frontend/crm && npm install && npm run dev # localhost:3000

# database (cloud project; asks for the database password)
cd backend && supabase link --project-ref <project-ref> && supabase db push
```

## Conventions

- Once per clone, turn on the commit checks: `git config core.hooksPath .githooks` (lint, format, types, build, and no secrets in commits). Full tests run on GitHub Actions; add the repository secret `DATABASE_URL` for the database tests
- Branches: `main` (live), `dev`, feature branches `feat/...`
- Database changes only through numbered migrations in `backend/supabase/migrations`
- Shared widget code goes in `frontend/widgets/core`; clinic-only code stays in that clinic's folder
- All SQL uses parameters and filters by `clinic_id`
- Every release runs the widget, CRM and backend test suites first
