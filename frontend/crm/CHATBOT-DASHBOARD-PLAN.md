# Dashboard (chatbot console) in the CRM: plan

The **Dashboard** is the chatbot's console inside the CRM: a **CRM | Dashboard** toggle in the top bar (BB Admin
and clinic managers) switches the left menu from the CRM screens to these. It follows the approved design
"Patient Assistant Console" (https://claude.ai/artifact/N9C2o6GrN2YCymzjJPSgfz) plus the screens added below.

Work happens on the **`saas` branch** with its own test data, so `main` (the demo) is never disturbed.
Build one screen at a time, show it, wait for "next" (see CRM-HANDOFF.md). The menu itself is in
`src/lib/assistant.ts`.

## Rules that apply to every screen

- **No LLM in answers.** The bot answers with rules and meaning matching only.
- **No self-training.** Every new answer, phrase or button is suggested, **approved by staff**, then published.
- **Buttons are trained.** Typing "book appointment" works like tapping it (CL01: 72/72 buttons). Adding or
  renaming a button asks for example phrases; the test sets must still pass (buttons 72/72, big set 313/313,
  small set 80/80) before it goes live.
- **Settings live in the database**, one record per clinic (today `backend/app/clinics/CL01.json`), so the bot
  uses changes without a redeploy.
- **JSON only** between the CRM and the backend; the backend checks every value; every change is logged.
- **Draft → publish:** changes are saved as a draft, previewed, then published; each publish is a version.

## Screens (menu order) and what each covers

| Group | Screen | What it covers | Stage |
|---|---|---|---|
| — | **Overview** | How the assistant is doing (chats, leads, bookings, how replies were made) and what needs a decision. Per clinic: status, websites, **Draft vs Live version**, **Publish**. | 1 |
| Widget | **Appearance** (4 tabs, one live preview) | **Look:** assistant name, **Enabled / Disabled**, logo (launcher and avatar, upload or URL). **Colours:** primary colour (patient bubbles, send button, links). **Widget style:** size, corner radius, border, shadow, "Powered by" footer text and link, header text. **Launcher:** position, offsets, shape, size, background and icon colour, icon, border, open on load, unread badge, label. **Also:** status line under the name, avatar letter when no logo, **main + highlight colour**, launcher label text (under 32 characters), show label after N seconds, notification dot, "chat opens as", open automatically on first visit. | 1 |
| Widget | **Templates** | One of three widget layouts: Tiles, Pills, Cards (today: Tiles, 7 cards in 3 columns) | 1 |
| Widget | **Menu buttons** | The chat's opening: **welcome message and trust figures**, then main buttons and sub-buttons, ON/OFF, create, delete, reorder, what each does (booking, online consult, cancel, reschedule, callback, answer, treatments, link, WhatsApp, call), **typed example phrases** per button. **Also:** three figures under the greeting, fallback message with a call-back button when no answer is found, icon per button, message above sub-buttons, cards (title, text, button text and link), Emergency button on/off. | 1 |
| Widget | **Clinic info** (4 tabs, one live preview) | **Lead questions:** The booking, callback and "talk to a person" questions, **editable**: order, wording, the check on each answer, where each lead goes. **Services:** Every treatment: name, description, website page, price, Book button; cost options; services not offered. **Contact & hours:** Phone, WhatsApp, email, address and map, opening hours, closed days (used by every button). **Reviews:** Google rating and count, selected patient quotes, the reviews link, celebrity answers. **Also, Lead questions:** question types, flow name, CRM tag per flow, opening line, read the answers back to confirm, final message, save to Lead CRM, email alert to the front desk, WhatsApp confirmation, HealthPlix slot request (to decide). **Services:** category, photo, duration, starting price with a "From ₹" switch (off: price shared at consultation), page on the website, Read more, which flow the Book button runs, show in chat; renaming updates every button. **Contact & hours:** emergency number, WhatsApp pre-filled message, landmark, parking, Google Maps link, closed message. | 2 |
| Widget | **Emergency & medical** | The emergency (108) reply and the wording used when a question needs the doctor (medical guard) | 2 |
| Widget | **Knowledge base** | Typed questions answered from **approved content only**: facts, Q&A and their wordings (knowledge base), with approval | 5 |
| Widget | **Legal & consent** | Consent wording and policy links shown in the chat | 5 |
| Bot quality | **Unanswered questions** | What patients asked that the bot could not answer; staff write an answer or add it as a new wording of an existing one; used only after approval | 3 |
| Bot quality | **Chat transcripts** | Every conversation, its patient and lead, and **why** the bot gave each reply (from the answer traces) | 3 |
| Bot quality | **Test & quality** | Run the test sets from the dashboard and see the score; a **test link** to try changes before patients see them | 3 |
| Connect | **Website install** | The widget is connected **only from the Dashboard**: staff add the clinic's website address, it is **approved there** (manager / BB Admin), and only then the Dashboard gives the embed code; the widget loads only on approved websites (others are refused); which pages the bot shows on | 3 |
| Connect | **Integrations** | Cal.com (online consults, Google Meet), WhatsApp, Google Sheet leads (Meta lead ads) | 3 |
| Security | **Login & security** | Sign-in rules and limits that protect the console and the widget | 4 |
| Security | **Privacy & data** | How patient data is collected, stored (chats 3 days), masked, exported and deleted on request | 4 |
| Security | **Team & access** | Who can sign in, which clinics they open, what each role can change (front desk suggests, manager approves, BB Admin publishes); invites; email domain policy. **Also:** invite with role; access requests ("why they need manager access") with status. | 2 |
| Security | **Activity log** | Every change, with who made it and when | 4 |
| Security | **Staff alerts** | Who is told about emergency or medical questions and unanswered questions piling up | 4 |
| Admin | **Versions** | Each publish saved; roll back in one click | 5 |

## Where today's work already exists (backend) and what is new

| Already built (connect it) | New backend work |
|---|---|
| Booking, callback and consult flows (Lead questions) | Widget settings per clinic in the database (look, welcome, template, buttons, reviews, safety wording) |
| Treatment list and cost options (Services) | Draft → publish with versions and roll back |
| Clinic hours, closed days, slots (Contact & hours) | One widget script for all clinics that reads its settings |
| Approved facts and Q&A, no LLM (Knowledge base) | Editable lead questions with answer checks |
| Unanswered questions table, answer traces (Bot quality) | Approval queue for answers, phrases and buttons |
| Consent on leads, patient data deletion (Privacy) | Test sets runnable from the dashboard; test link |
| Audit log (Activity log), roles per clinic (Team) | Invites, email domain policy, staff alerts |
| Cal.com, Google Sheet webhook (Integrations) | Website approval and embed code per clinic; per-clinic integration keys |
| Allowed website list per clinic (`clinics.allowed_origins`, checked on every chat request) | |

## Pending

- **Menu buttons → Workflow canvas:** the one-level screen is replaced by an n8n-style canvas of ready-made blocks
  (triggers, appointments with Form / Step by step, treatments, information, logic), working with taps and typed
  text, saving into the CRM pipeline. Full plan: **WORKFLOW-CANVAS-PLAN.md** (build steps W1-W11).

## Not decided yet

- **HealthPlix** (Lead questions → request the slot in HealthPlix): is NEO using it?

- **Languages:** English today (the database also allows Hinglish); Hindi, Kannada or others.
- **WhatsApp as a channel:** the same bot answering on WhatsApp (needs a provider; an Interakt key exists).
- Whether the CRM's own "Dashboard" menu item is renamed (e.g. "Home") to avoid two things named Dashboard.

## Build order (stages)

1. **Stage 1:** Overview, Appearance (Look, Colours, Widget style, Launcher), Templates, Menu buttons (+ settings in the
   database, one widget reading them)
2. **Stage 2:** Clinic info (Lead questions, Services, Contact & hours, Reviews), Emergency & medical, Team & access
3. **Stage 3:** Unanswered questions, Chat transcripts, Test & quality, Website install, Integrations
4. **Stage 4:** Login & security, Privacy & data, Activity log, Staff alerts
5. **Stage 5:** Knowledge base, Legal & consent, Versions
