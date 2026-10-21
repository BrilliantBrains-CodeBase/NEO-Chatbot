# TODO

## Open items to confirm

- [ ] **Error messages**: the two in `frontend/widgets/core/i18n/en.json` are not in the mockups, so they were written during the build. Please confirm or change them:
  - "You seem to be offline. Please check your connection and try again."
  - "Something went wrong. Please try again."
- [ ] **Config address**: the widget uses `/v1/widget/config/{clinic}`, since the README doesn't give an exact path. The backend will need to use the same one.

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

### Git
- [x] Branch `dev`: docs commit (done 15 Oct 2026)
- [x] Branch `feat/widgets`: Step 1 and Step 2 commits (done 15 Oct 2026)
- [x] Pushed to GitHub: `feat/widgets` and `frontend` branches (done 21 Oct 2026)

---

## Next

- [ ] Step 3: layout (desktop panel, mobile sheet, header, footer, typing bar)
- [ ] Optional: add `.gitattributes` to stop the "LF will be replaced by CRLF" warnings
