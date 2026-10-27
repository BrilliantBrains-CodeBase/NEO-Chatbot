# Workflow canvas (Dashboard → Menu buttons): plan

The chat's buttons and conversations are built on a **canvas, like n8n**: ready-made **blocks (nodes)** that
already know their job, dragged onto the canvas, set up in a side panel and connected with lines. It replaces the
one-level Menu buttons screen. Status: **planned, not built**. Built on the `saas` branch, one step at a time.

## Rules

- **Every block works with typed text as well as taps** (section 2). Patients type as much as they tap.
- **No LLM.** Typed text is understood by rules, approved phrases and meaning matching, as today.
- **No self-training.** Typed phrases and answers are suggested, **approved by staff**, then published.
- **Draft → publish → versions** (migration 0019), so any change can be rolled back.
- **Publish is blocked** until the checks pass: no loose ends, and the test sets (buttons 72/72, typed 313/313,
  small 80/80 for CL01) still pass.
- **One source of data:** blocks read Clinic info (Services, Contact & hours, Reviews), Doctors and Appearance,
  so a price or a phone number is changed once and every block shows it.
- **Everything lands in the CRM pipeline:** Leads, Inbox, Appointments, Cal.com, as the chat does today.

## 1. Triggers: how a conversation starts

| Trigger | What starts it |
|---|---|
| **Opening** | The chat opens: welcome message, trust figures, then the main buttons |
| **Main button** | Each main button on the opening screen (Book Consultation, Explore Treatments, About Doctors...) is a trigger |
| **Typed message** | The patient types instead of tapping; the trigger's approved typed phrases lead to the same flow |
| **Link or ad** (later) | The chat opened from a page or an ad (e.g. the IVF page opens the IVF flow) |

## 2. Working with typed text (built into every block)

| Situation | What the block does |
|---|---|
| Typing instead of tapping | Each button and trigger has **typed phrases** ("book appointment", "appointment chahiye"), approved by staff; typos allowed |
| Typing an answer | Questions accept typed answers and check them: dates ("tomorrow", "28 Oct", "next Monday"), times ("11 am", "evening"), phones ("+91 98765 43210", "9876543210") |
| A question mid-flow | "How much does it cost?" while booking: the knowledge base answers, then the flow **carries on** where it was |
| Changing their mind | "Actually I want to cancel" while booking: switches to the Cancel flow (after "Shall I stop the booking?") |
| Typing a treatment | "beard", "prp": opens that treatment's card directly |
| Not understood | The block's **No match** exit: knowledge base, then the fallback message and the call-back offer |
| Medical or emergency words | Always first, from any block: medical guard (the doctor will advise) or Emergency (108) |
| "Main menu", "back", "start again" | Work from anywhere |

On the canvas each block shows a **"Typed: N phrases"** badge; the test chat lets you type as well as tap.

## 3. Block library

### Appointments (each has a mode: **Form** or **Step by step**)

| Block | Form mode | Step-by-step mode | Saved in the CRM as |
|---|---|---|---|
| **Book appointment (in-clinic)** | One card: name, phone, treatment, date, time, Submit | One question at a time, each answer checked | Lead + **Booking request** (Inbox) + pending appointment |
| **Online consultation** | Same + email (confirmed) | Same, one at a time | Lead + **Online consult** request; Cal.com on approve |
| **Cancel appointment** | Name, phone, booked date | One at a time | **Cancellation** request, matched to the appointment |
| **Reschedule appointment** | Name, phone, booked date, new date and time | One at a time | **Reschedule** request |
| **Call back** | Name, phone, reason | One at a time | **Callback** request |
| **Report request** | Name, phone, visit date | One at a time | Request in the Inbox |
| **Follow-up booking** | Existing patient found by phone | One at a time | Booking request on the same lead |
| **Check my appointment** | Phone | Phone | Shows the next appointment (date, time, doctor) |

Settings for each: which fields (on/off, order), the wording of each question, the check on each answer (Indian
mobile, email, date within the booking window, clinic hours), read the answers back, final message, who gets the
lead (round robin / manager), email alert.

Helper blocks: **Choose a doctor** (only doctors who do the treatment), **Slot picker** (real free times; in-clinic
and online share one diary), **Consent** (the consent line before any lead is saved), **OTP check** (optional,
WhatsApp or SMS), **Duplicate check** (a known phone updates the lead), **Lead tag / source** (e.g. "Diwali offer").

### Treatments

| Block | Shows | Settings |
|---|---|---|
| **Treatment categories** (main list) | e.g. Hair transplant, Hair fall & scalp, Other | Which categories, order, message above |
| **Treatment list** (sub list) | The treatments in one category | From Clinic info → Services |
| **Treatment card** | Name, description, price line, **Book for this** (→ a booking block with the treatment filled in), **Read more** | Which buttons show |
| **Treatment cost** | Cost questions (e.g. receding / crown / advanced) → cost answer | Options and answers |
| **Cost estimator** | A few questions → a price range, "confirmed at consultation" | Questions, ranges |

### Information

| Block | Source / settings |
|---|---|
| **Doctors** (list → profile → "Book with Dr ...") | The CRM's Doctors |
| **Clinic location & hours** | Clinic info → Contact & hours |
| **Reviews** | Clinic info → Reviews |
| **Answer** | Fixed text + optional buttons |
| **Knowledge base answer** | Approved knowledge base; if none, the **No match** exit |
| **FAQ list** | Question buttons, each answered from the knowledge base |
| **Gallery** | Before / after photos (with consent) |
| **Fixed guides** | EMI & insurance, first-visit checklist, scan preparation, directions |
| **International patients** | Country → travel help → video consult |

### Contact & safety

| Block | Does |
|---|---|
| **WhatsApp** | Opens WhatsApp with the message from Contact & hours |
| **Call** | Calls the clinic |
| **Emergency** | 108 reply, warning signs, call the clinic |
| **Talk to a person** | Urgent callback, or the clinic phone during open hours |

### Logic

| Block | Does |
|---|---|
| **Choice** | A message with up to 12 buttons, each its own exit (a general sub-menu) |
| **Clinic open / closed** | Two exits, from Contact & hours |
| **Day and time** | e.g. a weekend message |
| **Returning visitor** | "Welcome back. Continue your booking?" (the chat remembers 3 days) |
| **Language choice** | When languages are decided |
| **A/B test** | Two versions, half the visitors each, to see which gets more bookings |
| **Go to** | Jump to another part of the flow (no copying) |
| **Back / Main menu** | As in the chat today |

### Engagement

| Block | Does |
|---|---|
| **Rating** | "Was this helpful? 👍 / 👎" + optional comment → Bot quality |
| **Share your experience** | Asks happy patients for a Google review (link) |
| **Offer / announcement** | A time-limited message on the opening screen (start and end dates) |

### Messages out (after a lead is saved)

WhatsApp confirmation (once a provider is chosen), email alert to the front desk, Cal.com booking for online
consults (exists), reminders 24 h and 1 h before.

## 4. CRM pipeline links

- Lead blocks save into **Leads** (source Chatbot, the flow's tag), the **Inbox** (request type), **Appointments**
  and **Cal.com**, as today.
- **Stage rules:** e.g. booking request → lead stage Follow Up; approved → Booked.
- **Staff alerts:** emergency or urgent callback → the bell and an email to the manager.
- **Unanswered typed questions** → Bot quality → Unanswered questions, for staff to answer.

## 5. The canvas

- **Left:** the block library with search, grouped as in section 3; drag a block onto the canvas.
- **Middle:** the canvas. Triggers on the left, flows to the right; a line from each button or exit (Submitted,
  No match, Open, Closed ...). Zoom, pan, mini-map, auto-arrange, search.
- **Right:** the selected block's settings (e.g. Form / Step by step, fields, wording, checks, where it goes).
- **Test chat:** tap and type as a patient; the active block is highlighted and the matched typed phrase shown.
  Test leads go to the test clinic, not to staff.
- **Problems panel:** loose ends, unreachable blocks, missing settings, buttons without typed phrases.
- **Stats on the canvas:** how many patients reached each block and where they dropped off (from the answer
  traces the bot already records).
- **Tools:** copy, paste, duplicate; copy a flow to another clinic; sticky notes; version history and compare.
- **Templates:** whole starter flows (Hair clinic, Fertility clinic, Skin clinic) and block groups (e.g. "Full
  booking" = consent + questions + slot picker + save lead). CL01's chat today is imported as the first flow.
- Canvas library: **React Flow** (`@xyflow/react`, MIT).

## 6. Build order

| Step | What |
|---|---|
| **W1** | Backend: the flow format (triggers, blocks, lines, settings per block type, canvas positions), checks, import of CL01's menu, 19 pages and booking questions; tests |
| **W2** | Canvas: library, drag, connect, zoom, mini-map, auto-arrange; settings panel for Choice, Answer, WhatsApp, Call, Emergency |
| **W3** | Treatment blocks (categories → list → card → cost), reading from Services |
| **W4** | Appointment blocks with Form / Step by step and field settings, Consent, Choose a doctor, Slot picker; saving into Leads, Inbox, Appointments |
| **W5** | Information blocks (Doctors, Location, Reviews, Knowledge base, FAQ list), Check my appointment (OTP optional, sent on WhatsApp through Interakt), Clinic open / closed, Go to. Report request: paused (2026-10-27) |
| **W6** | Test chat (tap and type, active block and matched phrase shown); publish checks with the test sets |
| **W7** | Typed phrases per button and trigger, with staff approval |
| **W8** | Templates (Hair, Fertility, Skin) and block groups |
| **W9** | Stats on the canvas (reach and drop-off per block) |
| **W10** | Engagement blocks (rating, Google review, offers), A/B test, messages out |
| **W11** | (With the user's OK) the live chatbot runs the published flow instead of `CL01.json` |

## 7. More from other tools (Voiceflow, Botpress, Typebot, Landbot, ManyChat)

Ideas that fit the rules (no LLM, staff approval); AI-written replies and AI routing are left out.

| Idea | What it adds | Step |
|---|---|---|
| **ON/OFF everywhere** | Whole flow, block (skipped; the patient goes on) and button ON/OFF; scheduled ON/OFF (between dates, or clinic hours only); greyed out on the canvas | W4 |
| **Fields (variables)** | Saved answers (name, phone, treatment, date, source); used in messages ("Thanks {name}"); a **Set field** block | W4 |
| **Conditions** | If / else on fields, clinic hours, day and time, device, returning patient | W5 |
| **No reply / retries** | Reminder after N minutes of silence; ask again up to 2 times on a wrong answer, then offer a call back | W5 |
| **Global triggers** | Main menu, talk to a person, emergency, start again: set once for the whole flow | W5 |
| **Richer messages** | Image, video, card, carousel (treatments, doctors), file / PDF, map, typing delay | W5 |
| **More question types** | Number, date picker, time slots, picture choice, rating 1-5, file upload (with consent), yes / no, consent tick | W4 |
| **Components** | Save a group of blocks (e.g. "Full booking"), reuse it in many flows, edit once | W8 |
| **Hand-over to a person** | Dropped (2026-10-27): "talk to a person" is a Call back (global trigger → Call back block) | — |
| **Test chat with fields** | See the saved values while clicking through; test link before going live | W6 |
| **Path stats** | Reach, drop-off and conversion to booking per block | W9 |
| **Content helpers** | Search, unused blocks, duplicate a flow to another clinic, translations per block (when languages are decided) | W8 |

Canvas behaviour: the view is fitted once when a workflow loads; clicking a block, opening the side panel or
adding blocks keeps the user's zoom and position.

## 8. To do: Doctor card buttons (noted 2026-10-27)

The Doctor card (built: name, title, qualifications, photo, about, up to 6 figures, Book button, full profile link)
also needs its own buttons, like a menu block, each with a dot for its line or a job of its own:
- **Book an appointment with {doctor}**: opens a booking block with this doctor filled in (the doctor question
  is skipped; slots are this doctor's only).
- **View treatments**: this doctor's treatments (from Clinic info → Services), each to its card.
- More to be listed by the user.

## 9. To do: Webhooks, in Dashboard → Integrations, not on the canvas (noted 2026-10-27)

- **Webhook (send)** block: when the chat reaches it, the backend sends the conversation's data as JSON to an
  address the clinic sets (e.g. another system, Google Sheet, Zapier / Make). Settings: https address, method
  (POST), which fields to send (name, phone, treatment, answers, lead code ...), a secret header so the receiver
  can trust it, a time limit and up to 3 retries. Exits: **Sent** and **Failed** (e.g. Failed → call back block).
  Values from the reply can be saved into fields (e.g. a booking number) to use in the next messages.
- **Webhook (receive)** trigger: an address of our backend with a secret that an outside system can call to start
  or continue a flow (e.g. a lead from an ad form), like the Google Sheet leads webhook already built.
- Every send and receive is logged (time, status, error) in the Activity log; no patient data in the address,
  only in the body; https only.

## 10. Live CRM data in the blocks (noted 2026-10-27)

Blocks show and use the CRM's **live** data, never copies typed into the canvas:
- **Appointment blocks:** doctors from the CRM's Doctors; **free slots live** from the doctors' hours, leave and
  existing appointments (in-clinic and online share one diary); the canvas shows today's free slots on the block.
- **Doctor card / Doctors list:** name, photo, qualifications and status from the CRM's Doctors (on leave shown).
- **Treatments:** from Clinic info → Services (published prices).
- **Contact & hours, Reviews:** from Clinic info.
- **On each block:** live counts from the CRM: leads and bookings made through it (today / 7 days), pending
  requests waiting in the Inbox.
- **Test chat:** makes test leads and requests in the test clinic, visible in the CRM's Leads and Inbox.
