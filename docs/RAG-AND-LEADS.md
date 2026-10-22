# Backend design: chatbot pipeline, knowledge base, leads and CRM

This is the design for everything behind the 3 widgets: how a message is answered, how the knowledge base works, how leads and bookings reach clinic staff, and how the CRM is managed. Clinic staff work mainly in the CRM, so the CRM rules here are as important as the chatbot rules.

Diagrams of this design: [DIAGRAMS.md](DIAGRAMS.md).

Sources: [README.md](../README.md), [frontend.md](../frontend.md), the 3 chatbot guides in this folder, the approved mockups and the client decisions of 15 and 21 Oct 2026. Where they disagree, this file wins.

---

## 1. Principles

1. **The chatbot never guesses.** It answers only from the clinic's own knowledge base. If the answer is not there, it takes a lead and says the team will contact the patient.
2. **No healthcare or medicine answers.** Symptoms, diagnosis, medicines, doses, suitability ("is it right for me"), side effects and promised results are never answered. The question becomes a lead.
3. **Cost and timing of a treatment** are answered only if the knowledge base states them, word for word.
4. **One clinic per bot.** A bot never mentions or suggests another NEO clinic.
5. **Every conversation can end in a lead**, and every lead reaches a person in the CRM with a deadline.
6. **Never show a slot that may be taken.** A slot that is held, requested or booked is hidden.
7. **All traffic is JSON**, both directions (`Content-Type: application/json`).
8. **The LLM is last.** Rules and search answer first. The LLM is used only when they find nothing certain, and its output is checked before it is shown.

## 2. Clinics

| Clinic ID | Clinic | Bot | Hours | Closed | Slots (15 min) |
|---|---|---|---|---|---|
| CL01 | Neo Follicle | Arya AI | Wed to Mon, 10:00 to 19:00 | Tuesday | 10:00 to 18:30 |
| CL02 | Neo Fertility | Navya AI | Mon to Sun, 09:30 to 18:30 | None | 09:30 to 18:00 |
| CL03 | Derma Solutions | Diya AI | Mon and Wed to Sun, 10:00 to 20:00 | Tuesday | 10:00 to 19:30 |

All times are India time (Asia/Kolkata). Every table row that holds clinic data has `clinic_id`, and every query filters by it.

---

## 3. Answer pipeline (LangGraph)

### 3.1 State

```
clinic_id, session_id, visitor_id, event, payload, page_url, device
lang            'en' | 'hinglish'
flow            null | { name, step, data{...}, resume_step }
intent          detected intent or null
is_medical      bool
matches         [{chunk_id, score, text}]
reply           { messages[], ui, input, quick }
lead_needed     bool
```

Session state lives in Redis (key `sess:{clinic_id}:{session_id}`, 30 minutes idle expiry, the same rule as the widget).

### 3.2 Graph

```
load_session
  -> check_input        rate limit, max 500 characters, strip markup, injection patterns
  -> detect_language    English or Hinglish (word list + script check)
  -> emergency_check    emergency words -> EMERGENCY reply, end
  -> route
       event = button                         -> flow_engine
       typed text that answers the open step  -> flow_engine
       typed text otherwise                   -> classify
  -> classify
       medical                                -> lead_capture (question saved as reason)
       intent: book / online / cancel / reschedule / callback / whatsapp / talk / doctors / treatments
                                              -> start that flow (or show that menu)
       clinic question                        -> kb_answer
  -> kb_answer
       exact cache hit                        -> answer
       hybrid search, score >= HIGH           -> answer word for word
       HIGH > score >= LOW                    -> "Did you mean?" chips (top 3 questions)
       score < LOW                            -> llm_fallback
  -> llm_fallback       Groq, then Gemini; only the retrieved KB text; strict JSON
       valid and grounded                     -> answer
       anything else                          -> lead_capture
  -> localise           Hinglish only: LLM rewrites the final text, numbers and names unchanged
  -> resume             a flow was open: ask the same step again, data kept
  -> respond            build the JSON reply, save transcript, save session
```

`HIGH` and `LOW` start at 0.82 and 0.70 (cosine, after fusion) and are tuned on the test set in section 12.

### 3.3 Nodes

| Node | How it works |
|---|---|
| check_input | Redis rate limit per visitor (20 messages a minute) and per IP. Text over 500 characters is cut. Known injection phrases ("ignore previous", "system prompt") skip the LLM and go to lead capture. |
| detect_language | Devanagari script or 2+ common Hinglish words ("kya", "hai", "kitna", "kab", "mujhe") means Hinglish. Default English. |
| emergency_check | Keyword list per clinic (bleeding, fainting, breathing, severe swelling, allergic reaction, burn and so on). Always runs before anything else after the input checks. Never routes to a form. |
| route | A button event carries `action` and `value` and goes straight to the flow engine. Typed text is first tried as the answer to the open step (name, phone, email, date, reason). |
| classify | 1) rules and fuzzy match (rapidfuzz, typo tolerant) for intents and medical words; 2) if rules are unsure, an embedding classifier (logistic regression on bge-small vectors) trained on labelled examples per clinic. Medical wins over every other intent except emergency. |
| kb_answer | Exact cache (Redis, key = clinic + normalised question + KB version). Hybrid search: Postgres full-text (BM25 style) and pgvector cosine, merged with reciprocal rank fusion, filtered by `clinic_id`. The answer shown is the stored KB answer, word for word. |
| llm_fallback | Prompt contains only the top KB chunks for this clinic. The model must return `{"answer": str, "chunk_ids": [..], "confident": bool}`. Rejected if: not valid JSON, `confident` false, a chunk id not in the given list, a number or price not present in those chunks, another clinic's name, or the medical check flags the answer. 8 second timeout. |
| localise | Hinglish replies only. The LLM rewrites the final English text in Hinglish. Rejected and English used instead if any number, price, name or phone changes. Buttons stay English. |
| resume | If a flow was open, the reply ends with the same step question and the same input mode, so nothing the patient entered is lost. |
| respond | Builds `messages`, `ui`, `input`, `quick` as in the README contract. Saves both messages to `chat_messages`. |

Target: under 150 ms per reply without the LLM; LLM in under 5% of messages.

### 3.4 Lead capture (when the bot cannot answer)

Name -> contact number -> email -> "Thanks, <name>. Our team will contact you on <number>." The typed question is saved as the reason, so the reason step is skipped. Request type `Question`, source `Chatbot`. Same validation rules as booking.

---

## 4. Knowledge base

### 4.1 Source and ingestion

- One PDF per clinic in `docs/source/kb/` (named by clinic). Loaded by an admin command: `python -m app.kb.ingest --clinic CL01 path.pdf`.
- Text is extracted per page, split by headings into sections of about 300 to 500 words, with 50 words of overlap. Question and answer pairs, if present, are stored as single chunks.
- Each chunk gets: `clinic_id`, `title`, `text`, `source_file`, `page`, `category` (clinic info, treatment, cost, doctor, policy), `embedding` (bge-small-en-v1.5, 384 dimensions), `tsv` (Postgres full-text vector).
- A new upload creates a new `kb_version`. Chunks are switched over in one transaction and the answer cache for that clinic is cleared.
- Staff review: new chunks start as `draft`. Only `approved` chunks are searched. Clinic Manager or BB Admin approves in CRM Settings.

### 4.2 What the bot can answer from it

Clinic information, doctors, treatments as described, and cost or timing only where the PDF states them. Arya's cost guide (Rs 60 to Rs 100 per graft by hair loss pattern) is stored as approved KB text. Everything medical still goes to a lead even if the PDF mentions it.

---

## 5. Flow engine

Flows are fixed code (not the LLM). Wording comes from [frontend.md](../frontend.md).

| Flow | Steps | Creates |
|---|---|---|
| Book (in-clinic) | name, phone, email, treatment (reason if Other), doctor (Derma only), date, time, summary, confirm | Appointment `Pending`, lead |
| Online consultation | same, with online slots only; summary offers Switch to in-clinic | Appointment `Pending` type Online, lead |
| Cancel | name, phone or email, booked date | Request `Cancel`, matched or "No matching booking" |
| Reschedule | name, phone or email, booked date, new date, new time | Request `Reschedule` with old and new slot |
| Call back | name, phone, reason | Request `Callback`, lead |
| Lead capture | name, phone, email (question is the reason) | Request `Question`, lead |
| Emergency, WhatsApp, Talk to us, Explore, Doctors, International | one or two messages with buttons | nothing until a form is used |

Validation:
- Name: at least 2 letters.
- Phone: country code changeable (15 codes). India: 10 digits starting 6 to 9. Others: 6 to 12 digits. Stored as E.164.
- Email: standard format check.
- Reason: at least 3 characters.

Rules:
- Tapping another main button stops the open flow and starts the new one.
- Typed text in the middle of a flow is answered (or taken as a lead), then the same step is asked again.
- A lead is written to the CRM only at the final confirm step, never halfway.

---

## 6. Slots and availability

- **Availability** is set per doctor in the CRM: weekly hours, separate in-clinic and online hours, and leave days. Clinic hours and closed days cap it.
- **Slot length** 15 minutes (a clinic setting). Last slot starts 30 minutes before closing.
- **Booking window**: today up to 14 days ahead (a clinic setting). The booked-date picker for cancel and reschedule allows 2 months back up to 14 days ahead.
- **Today**: past times are hidden. After the last slot, the calendar starts from tomorrow.
- **Free slot** = inside availability, not on leave, and not held, pending or confirmed.
- **Hold**: when the patient picks a time, the slot is held in Redis for 5 minutes (`hold:{clinic}:{doctor}:{start}`), so nobody else sees it while they confirm.
- **Pending**: on confirm, an appointment row is written with status `Pending`. It stays hidden from the chatbot until staff reject it or the patient cancels.
- **Staff bookings** are written with status `Confirmed` and are also hidden at once.
- **Double booking** is prevented in the database: a unique index on `(clinic_id, doctor_id, start_at)` for active statuses. "Any time" or "No preference" stores a preferred window, not a slot, and staff choose the slot.

Appointment statuses: `Pending`, `Confirmed`, `Rejected`, `Cancelled`, `Rescheduled`, `Visited`, `No show`, `Missed` (the slot time passed while still Pending).

---

## 7. Leads

### 7.1 One lead per person per clinic

On every confirmed chatbot form, ads row or manual entry:
1. Normalise the phone (E.164) and email (lower case).
2. Look for a lead in the same clinic with the same phone, else the same email.
3. Found: increase `contact_count`, update `last_contact_at`, add the new request to its timeline. The stage does not move backwards (a Booked lead stays Booked).
4. Not found: create the lead with stage `New`, `contact_count` 1.
5. Link the chat transcript, then assign the lead, create its task and send the live alert.

### 7.2 Fields

Name, phone, email, source (Chatbot, Meta Ads, Google Ads, Manual, WhatsApp), campaign, treatment, doctor, appointment type, stage, assigned to, contact count, first and last contact, page URL, device, consent time, verified (OTP, later), notes, lost or invalid reason.

### 7.3 Stages (fixed, so reports compare across clinics)

`New` -> `Follow Up` -> `Booked` -> `Visited`, plus `Lost` and `Invalid` with a reason.
- `Booked` is set when an appointment is confirmed.
- `Visited` creates or links a **Patient** record.
- `Lost` needs a reason (Not reachable, Not interested, Price, Chose another clinic, Other). `Invalid` needs a reason (Wrong number, Spam, Duplicate, Test).

### 7.4 Assignment and tasks

- **Round robin** among the clinic's active Front Desk users, in turn. Clinic Manager can reassign.
- **New lead** -> task "Call patient", due 30 minutes later if within clinic hours, otherwise within the first hour of the next working day.
- **Call outcome** buttons: Answered, No answer, Busy, Wrong number. No answer or Busy -> retry task the next working day. After 3 failed tries -> stage `Lost`, reason Not reachable. Wrong number -> stage `Invalid`.
- **Overdue** tasks show red on the dashboard and in Tasks.
- **Pending booking not confirmed within 2 working hours** -> alert to the Clinic Manager. The slot stays hidden. If the slot time passes while still Pending -> status `Missed`.

---

## 8. CRM roles

| Action | BB Admin | Clinic Manager | Front Desk | Doctor |
|---|---|---|---|---|
| Clinics visible | All | Own | Own | Own |
| Leads: view, edit, call, stage | Yes | Yes | Yes | No |
| Reassign leads | Yes | Yes | No | No |
| Appointments: confirm, reject, reschedule | Yes | Yes | Yes | No |
| Own appointments | Yes | Yes | Yes | Yes |
| Doctor availability and leave | All | All | All | Own only |
| Knowledge base approve | Yes | Yes | No | No |
| Team, settings | Yes | Own clinic | No | No |
| Export, delete patient data | Yes | Yes | No | No |

Enforced twice: in the API, and with Row Level Security in Postgres. Sign-in is email and password (Supabase Auth). Users are invited by email, and passwords are reset by email.

Every stage change, assignment, export and delete is written to `audit_log` (who, what, when, before and after).

## 9. Notifications

- **CRM live alerts** (Supabase Realtime), per clinic: new lead, new booking request, cancel, reschedule, callback, overdue task, Pending escalation.
- **WhatsApp (Interakt)**: mocked until the account is ready. Then: patient confirmation after staff confirm, reminders 24 hours and 1 hour before, Meet link for online consults.
- All outgoing messages go through an **outbox** table and a worker, so a failed send is retried and never lost.

---

## 10. Integrations

| Integration | Status | Design |
|---|---|---|
| Groq (LLM) | Key later | Primary. Behind one `LLMClient` interface. |
| Gemini (LLM) | Key later | Backup when Groq fails or times out. |
| Supabase | Ready | Postgres, pgvector, Auth, Realtime, Storage. |
| Google Sheets (ads leads) | Later, one by one | Worker reads new rows every 5 minutes, maps the columns, runs the lead upsert with source Meta Ads or Google Ads. |
| Interakt (WhatsApp) | Later | Through the outbox. Optional OTP stays Phase 2. |
| Google Calendar (Meet) | Later | Staff approve -> event with Meet link -> invite sent. Reschedule updates the event; cancel deletes it. |
| HealthPlix | Phase 2 | Connector stub only. |

Until a key exists, each integration runs as a mock with the same interface, so the rest of the system is built and tested now.

---

## 11. Database tables

All tables have `id`, `clinic_id` (except `clinics` and `users`), `created_at`, `updated_at`. Full column list, indexes, Row Level Security, backups and retention: [DATABASE.md](DATABASE.md).

| Table | Purpose |
|---|---|
| clinics | ID (CL01...), name, bot name, hours, closed days, slot length, booking window, phones, WhatsApp, allowed origins, widget config JSON |
| users, user_clinics | Staff and doctors, role per clinic |
| doctors, doctor_availability, doctor_leave | Doctor profiles, weekly hours (in-clinic, online), leave |
| leads | Section 7.2 |
| requests | Every chatbot or staff request: Book, Online, Cancel, Reschedule, Callback, Question; data JSON; match result |
| appointments | Doctor, start, end, type, status (section 6), linked lead and request |
| patients | Created at Visited, linked leads |
| tasks | Lead, type, due time, assigned to, status, attempt number, outcome |
| chat_sessions, chat_messages | Transcript linked to the lead, kept as short memory: deleted after 3 days. The lead keeps the request and the patient's question |
| kb_documents, kb_chunks, kb_versions | Knowledge base (section 4) |
| unanswered_questions | Every question that went to a lead, for review and KB improvement |
| outbox | Outgoing WhatsApp, email and calendar jobs |
| audit_log | Section 8 |

Migrations are numbered SQL files in `backend/supabase/migrations`, the only way the schema changes.

---

## 12. Security and privacy

- The widget holds no keys and stores only `visitor_id` and `session_id`.
- The backend checks the request origin against the clinic's allowed domains. The clinic ID in the request must match the origin.
- All SQL uses parameters and filters by `clinic_id`.
- Patient data stays in India-region hosting. Consent text is shown in every flow that collects details, and the time of consent is stored (DPDP Act 2023).
- LLM calls send only the question and KB text, never the patient's name, phone or email. Paid tier only.
- Secrets live in `.env` on the server, never in the repository.

## 13. Testing

- **Widget**: Playwright for every flow in frontend.md on all 3 clinics, desktop and mobile.
- **Backend**: pytest for every node, flow, validation rule, slot rule (closed days, last slot, 2-week window, hidden pending slots, no double booking) and lead rule (upsert, contact count, round robin, task timing, escalation).
- **Answer quality set**: about 100 questions per clinic, labelled answer, medical, lead or other-clinic. Used to tune `HIGH` and `LOW`. The release gate is 0 medical answers and 0 other-clinic mentions.
- **CRM**: Playwright for each role, including checks that a role cannot see or do what the table in section 8 forbids.

## 14. Build order

1. Widgets, Steps 3 to 11 of [WIDGET-STEPS.md](../WIDGET-STEPS.md), against the mock backend.
2. CRM screens from the approved design.
3. Database migrations, Auth, roles, Row Level Security.
4. Flow engine, slots, leads, tasks, notifications. Widgets and CRM switch from mock to real.
5. Knowledge base ingestion, classifier, hybrid search, LangGraph pipeline.
6. LLM fallback and Hinglish (when the Groq key arrives).
7. Integrations one by one: Google Sheets, Interakt, Google Calendar.
8. Test sets, threshold tuning, deploy to Linode, clinic sign-off.

## 15. Open items

- Knowledge base PDFs per clinic (from the client).
- Groq and Gemini keys, Interakt account, Linode server, chat.brilliantbrains.ai DNS.
- Google Sheets layout for ads leads.
- Final confirmation of the two error messages in `core/i18n/en.json`.
