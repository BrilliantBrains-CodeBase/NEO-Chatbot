# TODO

## Open items to confirm

- [ ] **Error messages**: the two in `frontend/widgets/core/i18n/en.json` are not in the mockups, so they were written during the build. Please confirm or change them:
  - "You seem to be offline. Please check your connection and try again."
  - "Something went wrong. Please try again."
- [ ] **Config address**: the widget uses `/v1/widget/config/{clinic}`, since the README doesn't give an exact path. The backend will need to use the same one.
- [ ] **Arya texts not in frontend.md or the mockups** (written during the build; same pattern for Navya and Diya). Please confirm or change them:
  - After choosing "Other": "Please tell us briefly what you are looking for."
  - Reason too short: "Please add a few more words."
  - Summary with Any time: "24 Oct 2026, any time"; confirmation: "on 24 Oct 2026 (any time)"
  - After tapping Main menu: "How can I help you today?"
  - Question typed mid-booking with no answer (or medical): "I don't have a confirmed answer for that yet. I have noted your question for our team."
  - Cost asked mid-booking: "Hair transplant cost is graft based, Rs 60 to Rs 100 per graft. The final count is confirmed after a scalp evaluation."
  - Address asked mid-booking: "We are at 1st floor, Scorpio House, near Marathahalli Bridge, Munnekolala, Bengaluru 560037. Open Wednesday to Monday, 10 AM to 7 PM. Tuesday closed."
  - Typed date that cannot be booked: "That date is not available. Please choose another date."
  - Typed time that cannot be booked: "That time is not available. Please choose one of the times shown."

---

## Done so far

### GitHub and docs
- [x] Repo cloned and connected to GitHub (`NEO-Chatbot`) (done 15 Oct 2026)
- [x] Created `WIDGET-STEPS.md`: an 11-step checklist for the chatbot widgets, English only (done 15 Oct 2026)
- [x] README.md updated: (done 15 Oct 2026)
  - Week plan: Week 1 widgets, Week 2 CRM, and Weeks 5 and 6 split into separate rows
  - New sections: clinic details (hours, closed days, phones, doctors), booking rules and widget layout
  - Contract: added the `treatment_card` block and the input modes
  - Loader file added to the folder layout, plus the Windows activate command
  - `docs/RAG-AND-LEADS.md` marked as "to be written in the backend phase"
- [x] frontend.md updated: (done 15 Oct 2026)
  - "Rules added after review" block: 15-minute slots, date rules, changeable country code, cancel/reschedule matching
  - Derma Call Back flow corrected to match Navya and Arya
  - Blank date picker cells and "Explore Treatments" labels fixed
  - "Extra flows" section: Explore lists, About Doctor cards, International Patients, WhatsApp, Talk to us, no-answer fallback, Derma status line, popular treatments and doctor cards
- [x] Client decisions recorded: (done 15 Oct 2026)
  - Cancel/reschedule: match name plus phone or email. If there is no match, the request still goes to staff marked "No matching booking". The patient sees the same message either way.
  - The booked-date picker allows previous and future dates, from 2 months back

### Step 1: Widget project setup (done 15 Oct 2026)
- [x] `frontend/widgets/` with Preact, TypeScript and Vite (done 15 Oct 2026)
- [x] Folders: `core/`, `neo-fertility/`, `neo-follicle/`, `derma-solutions/`, `playground/`, `tests/` (done 15 Oct 2026)
- [x] Build makes one self-contained file per clinic for a plain `<script>` tag (done 15 Oct 2026)
- [x] Size check: build fails if a file is over its limit (done 15 Oct 2026)
- [x] `.gitignore`, ESLint 10, Prettier (done 15 Oct 2026)
- [x] Scripts: `npm run dev`, `build`, `size`, `typecheck`, `lint`, `test` (done 15 Oct 2026)

### Step 2: Core shell (done 15 Oct 2026)
- [x] **Loader** (`<clinic>.js`, 1.8 KB, limit 5 KB): shows only the launcher. It loads the full widget `<clinic>.app.js` (6.9 KB so far, limit 40 KB) on first open (done 15 Oct 2026)
- [x] **Shadow DOM**: clinic website CSS cannot change the widget (tested with aggressive CSS) (done 15 Oct 2026)
- [x] **Launcher**: (done 15 Oct 2026)
  - Clinic colour and unread dot
  - Desktop: "Chat with us" label appears after 8 seconds
  - Mobile: sits above the site's sticky bar and hides while open
  - Never auto-opens
- [x] **Clinic colours** in `theme.css` for each clinic (plum, blue, brown) (done 15 Oct 2026)
- [x] **`en.json`**: all widget interface text, English only (done 15 Oct 2026)
- [x] **Session**: only `visitor_id` and `session_id` are stored. The same session continues after reload; a new one starts after 30 minutes of no activity (done 15 Oct 2026)
- [x] **API client**: 10-second timeout, two retries for server and network errors, offline check, and room to plug in the mock backend (done 15 Oct 2026)
- [x] **Playwright tests** in the installed Edge, desktop and mobile: 8 of 8 pass (done 15 Oct 2026)

### Fixes after code review (done 21 Oct 2026)
- [x] `visitor_id` and `session_id` now use 16 random bytes (32 hex characters) instead of 4, so they don't collide at scale
- [x] Close button on the placeholder panel, so mobile users can close the chat before Step 3 adds the header
- [x] WIDGET-STEPS.md: item 1.4 now names `scripts/size.mjs`; item 3.1 (Launcher) ticked, since it was built in Step 2

### Backend skeleton (done 21 Oct 2026)
- [x] FastAPI on Python 3.12 (uv), cloud Supabase through the connection string, `/v1/health` and `/v1/health/ready`
- [x] Redis optional (Phase 2); tests use clinic CL99

### Neo Follicle (Arya) widget, pieces 1 to 8 (done 21 Oct 2026)
Each piece was checked (typecheck, lint, build, Playwright on desktop and mobile) and committed separately.
- [x] 1: contract types, date helpers, icons, safe bold text
- [x] 2: desktop panel 380 x 580, mobile sheet with backdrop, swipe down, header, footer
- [x] 3: message bubbles, typing dots, offline and server errors with Try again, restart with a new session
- [x] 4: typing bar with text, phone (15 country codes, IN +91 default) and email modes
- [x] 5: Arya 3-column menu cards, chips with Back and Main menu, call, WhatsApp and website links
- [x] 6: month calendar (closed days, 2-week window, booked date 2 months back) and 15-minute time grid
- [x] 7: doctor card with stats grid
- [x] 8: mock backend with every Arya flow word for word: booking (in-clinic, online), cancel, reschedule, callback, typed-question lead, Explore, Not sure, cost guide, International, Talk to us, emergency and medical rules, questions mid-booking
- [x] Bugs found by the tests and fixed: shared button style overriding component styles (would have broken the 16 px iPhone input), invalid email blocked by the browser popup, mobile tap missed after typing, test timing race with the opening animation
- [x] 150 Playwright tests pass; Arya widget 13.0 KB of the 40 KB limit, loader 1.9 KB of 5 KB

### Git
- [x] Branch `dev`: docs commit (done 15 Oct 2026)
- [x] Branch `feat/widgets`: Step 1 and Step 2 commits (done 15 Oct 2026)
- [x] Pushed to GitHub: `feat/widgets` and `frontend` branches (done 21 Oct 2026)

---

## Next

- [ ] Piece 9b: iPhone-size and keyboard-only tests for Arya
- [ ] Piece 9c: restore the conversation after a page reload (WIDGET-STEPS 5.12)
- [ ] Push the Arya commits to GitHub (`feat/widgets` and `frontend`)
- [ ] Backend: database migrations, then the real `/v1/chat/message` for Arya (replaces the mock)
- [ ] Navya and Diya faces
- [ ] Optional: add `.gitattributes` to stop the "LF will be replaced by CRLF" warnings
