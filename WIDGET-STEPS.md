# Chatbot Widget: Step-by-Step Build Plan

Scope: the 3 chatbot widgets (Navya AI, Arya AI, Diya AI) in `frontend/widgets/`. **English only.**
The backend is not built yet, so the widgets run against a **mock backend** that follows the contract in README.md.

Sources used to build this plan:
- **R** = README.md
- **F** = frontend.md
- **M** = approved mockup artifacts (Navya, Arya, Diya)
- **D** = client decisions (15 Oct 2026)

Tick each box when the step is done.

---

## Step 1: Project setup

- [ ] 1.1 Create `frontend/widgets/` with Preact, TypeScript and Vite (R)
- [ ] 1.2 Folder layout: `core/`, `neo-fertility/`, `neo-follicle/`, `derma-solutions/`, `playground/`, `tests/` (R)
- [ ] 1.3 Vite library build with 3 entries: `dist/neo-fertility.js`, `dist/neo-follicle.js` and `dist/derma-solutions.js` (R)
- [ ] 1.4 Size check in `vite.config.ts`: the build fails if any bundle is over 40 KB compressed (R)
- [ ] 1.5 Add a `.gitignore` (node_modules, dist) plus ESLint and Prettier
- [ ] 1.6 Add `npm run dev`, `build`, `test` and `size` scripts (R)

## Step 2: Core shell (shared by all clinics)

- [ ] 2.1 `shadow.ts`: mount the widget inside Shadow DOM and inject the CSS, so clinic site styles can't break it (R)
- [ ] 2.2 Small loader: shows only the launcher, then loads the full widget on first open. Loader must be under 5 KB (R targets)
- [ ] 2.3 `styles/base.css`: Figtree font, shared tokens (`--ink`, `--mute`, `--line`, `--surface`, `--honey`, `--wa`) (M)
- [ ] 2.4 `i18n/en.json`: every piece of widget text in one file, English only (R, D)
- [ ] 2.5 `session.ts`: `visitor_id` and `session_id` in localStorage, no personal data (R)
- [ ] 2.6 `api.ts`: config fetch, `POST /v1/chat/message`, retries, timeout, offline message (R)

## Step 3: Layout and container

- [ ] 3.1 **Launcher**: 60 px circle with the honey unread dot. On desktop it also shows a "Chat with us" label after 8 seconds. Never auto-open the panel (M)
- [ ] 3.2 **Desktop panel**: 380 × 580, 20 px radius, bottom-right 24 px (M)
- [ ] 3.3 **Mobile sheet**: 88% height with a backdrop, grip bar and full screen option. Launcher sits above the site's sticky bar. Inputs use 16 px text so iPhone doesn't zoom (M)
- [ ] 3.4 **Header**: avatar, bot name, "Instant Reply Assistant", restart button, close button (F)
- [ ] 3.5 **Footer**: "AI Generated Responses, Not For Medical Advice / Powered By Brilliant Brains" (F)
- [ ] 3.6 **Typing bar**: text input, send button, and a country code selector that appears only for phone steps (F, M)

## Step 4: Core components (UI blocks from the contract)

Each block is drawn by `renderer.tsx` from `ui.type` (R).

- [ ] 4.1 `text` bubbles (bot and patient), typing dots, line breaks inside a bubble (F: " / ")
- [ ] 4.2 `menu`: main menu (each clinic styles it differently, see Step 6)
- [ ] 4.3 `chips`: pill buttons with Back / Main menu ghost links under them (M)
- [ ] 4.4 `phone`: country code select. India must be 10 digits starting 6–9, other countries 6–12 digits. Code is changeable (D, M)
- [ ] 4.5 `email`: email validation, error "Please enter a valid email address." (F)
- [ ] 4.6 `month_calendar`: past days disabled, clinic closed days disabled, today outlined (F, M)
- [ ] 4.7 `time_grid`: **15-minute slots** (D) inside clinic hours, past times hidden today, "Any time", "More times" (F, M)
- [ ] 4.8 `summary`: confirmation card plus consent line (F)
- [ ] 4.9 `link_buttons`: Call, WhatsApp, Maps, website links (M)
- [ ] 4.10 `emergency`: warning text plus Call 108 and Call clinic (F)
- [ ] 4.11 `doctor_card`: profile and stats grid (Navya, Arya) (M)
- [ ] 4.12 Accessibility: `aria-live` on messages, keyboard focus rings, reduced-motion support (M)

## Step 5: Flows (same on all 3 clinics, text exactly as in F)

- [ ] 5.1 **Book appointment (in-clinic)**: name → phone → email → treatment → date → time → summary → confirm (F)
- [ ] 5.2 **Online consultation**: same steps, plus "Switch to in-clinic visit" and the Google Meet message (F)
- [ ] 5.3 **Cancel**: name → phone (or email) → booked date (previous or future, from 2 months back). The backend matches the details to a booking. If there is no match, the request still goes to staff, marked "No matching booking", for approval. Same patient message either way. No OTP (D)
- [ ] 5.4 **Reschedule**: name → phone (or email) → old date (previous or future) → new date → new time, with the same match rule (D)
- [ ] 5.5 **Call Back**: name → phone → reason → confirmation (F). **Derma uses the same flow** (D, fixes the F bug)
- [ ] 5.6 **Emergency**: clinic-specific text and phone number (F)
- [ ] 5.7 **WhatsApp**: opens wa.me with a prefilled message (M)
- [ ] 5.8 **Explore Treatments**: category → treatment card (short text, "Book for X", "Read more on our website") (M)
- [ ] 5.9 **Typed question fallback**: "I don't have a confirmed answer for that yet…" → callback (M)
- [ ] 5.10 **Talk to us** and clinic info (address, hours, Maps) (M)
- [ ] 5.11 Change buttons on the summary: Change treatment, Change date and time, Start again (F)
- [ ] 5.12 Restart button and session restore after a page reload (R)

## Step 6: Clinic faces

### 6.1 Neo Fertility (Navya AI): plum
- [ ] Theme tokens `--rose:#3D203F --rose-d:#2B152D --blush:#8E5A92 --tint:#F5EEF6` (F)
- [ ] Menu: 2-column tiles, 6 buttons (R, F)
- [ ] Hours Mon–Sun 9:30 AM–6:30 PM, no closed day (M)
- [ ] About Doctor: Dr Payal Mahapatra card and stats (M)
- [ ] Treatments: Fertility (6), Gynecology and pregnancy (6) (M)

### 6.2 Neo Follicle (Arya AI): blue
- [ ] Theme tokens `--rose:#3E74D9 --rose-d:#2A56AE --blush:#8FB0EE --tint:#EEF3FC` (F)
- [ ] Menu: 3-column cards, Emergency across a full row, 7 buttons (R, F)
- [ ] Hours Wed–Mon 10 AM–7 PM, **Tuesday closed** (M)
- [ ] About Doctors: Dr Sandeep Mahapatra card and stats (M)
- [ ] International Patients card (R, M)
- [ ] Treatments: Hair Transplant (6), Hair Fall and Scalp (10), Beard, Eyebrow, "Not sure, help me choose" (M)

### 6.3 Derma Solutions (Diya AI): brown
- [ ] Theme tokens `--rose:#481E0B --rose-d:#33150A --blush:#B98A72 --tint:#F6F0EC` (F)
- [ ] Menu: pill quick replies (R)
- [ ] Hours Mon and Wed–Sun 10 AM–8 PM, **Tuesday closed** (M)
- [ ] Status line "Open today, 10 AM to 8 PM" or closed (F, M)
- [ ] Quick pills above the typing bar: Main menu, Book, WhatsApp (F)
- [ ] Typing suggestions from keywords (acne, scar, hair fall…) and popular treatment pills (M)
- [ ] Doctor step in booking: `doctor_carousel` (4 cards, Select, View profile, No preference) (F)
- [ ] Date step: `week_strip` with month picker (F)
- [ ] Time step: 3-column paged grid (F)
- [ ] Treatments: 5 categories, 41 treatments (M)

## Step 7: Clinic config (dynamic JSON)

- [ ] 7.1 One JSON per clinic: names, colours, menu, hours, closed days, phone, WhatsApp, treatments, doctors, emergency text (R)
- [ ] 7.2 Load from the config API; use a local JSON copy until the backend is ready (R)

## Step 8: Mock backend

- [ ] 8.1 Mock `POST /v1/chat/message` that replies using the contract format (`messages`, `ui`, `input`, `quick`) (R, F)
- [ ] 8.2 Script every flow in F word for word (F)
- [ ] 8.3 Mock slot list (15 min) and cancel/reschedule match check (D)

## Step 9: Playground

- [ ] 9.1 Dev page to switch between the 3 clinic faces (R)
- [ ] 9.2 Desktop and mobile preview side by side (M)

## Step 10: Tests and checks

- [ ] 10.1 Playwright: every flow in F for every clinic, including the invalid inputs ("P", "12345", "priya@") (F)
- [ ] 10.2 Date rules: closed days, past dates, past times hidden today (F)
- [ ] 10.3 Bundle size check: loader under 5 KB, each widget under 40 KB (R)
- [ ] 10.4 Test inside a sample page with aggressive CSS, to confirm Shadow DOM isolation (R)
- [ ] 10.5 Mobile checks: iPhone and Android sizes (M)

## Step 11: Build and hand-off

- [ ] 11.1 `npm run build` → 3 files in `dist/` (R)
- [ ] 11.2 Embed snippet for each clinic site (R)
- [ ] 11.3 Commit to a `feat/widgets` branch, then merge into `dev` (R conventions)

---

## Coverage check: README.md and frontend.md

**Already covered in the two files:** stack, folder layout, shared core plus faces, bundle sizes, Shadow DOM, session IDs, backend contract and UI blocks, English-only `en.json`, script tags, and word-for-word text for book, online, cancel, reschedule, callback and emergency.

**Was missing from both files.** All items below were added to README.md and frontend.md on 15 Oct 2026. Item 13 is marked as "to be written in the backend phase".

| # | Missing item | Where it comes from |
|---|---|---|
| 1 | Desktop panel and mobile sheet sizes, launcher behaviour | Mockups |
| 2 | 15-minute slots (mockups show 30 min) | Decision |
| 3 | Cancel/reschedule match check on name plus phone or email, no OTP | Decision |
| 4 | Changeable country code and validation rules | Decision, mockups |
| 5 | Derma Call Back should match the other clinics (F shows a bug) | Decision |
| 6 | Clinic hours and closed days | Mockups |
| 7 | Explore Treatments levels after step 1, treatment cards | Mockups |
| 8 | About Doctor(s), International Patients, WhatsApp, Talk to us, clinic info flows | Mockups |
| 9 | Typed-question fallback to callback | Mockups |
| 10 | Derma typing suggestions and popular pills | Mockups |
| 11 | Back / Main menu ghost links | Mockups |
| 12 | Loader file (under 5 KB) is in the targets but not in the folder layout | README |
| 13 | `docs/RAG-AND-LEADS.md` is linked in README but not in the repo | README |
| 14 | README week plan says 6 weeks but lists 5 | README |
| 15 | Contract UI blocks don't include a `treatment_card` or `doctor_profile` block | Needed for items 7–8 |
