# NEO CRM (frontend)

Staff app for the NEO clinics: leads, inbox, appointments, doctors' availability, patients, reports, team and
settings. Next.js 16 + React 19 + TypeScript. All data to and from the backend is JSON.

Designs: CRM screens `claude.ai/artifact/BHvewwn4fbDkVWC14z2Lhe`, sign-in pages
`claude.ai/artifact/YQfCYReoHxYCUwtVgn8MWW`.

```bash
npm install
npm run dev          # http://localhost:3000
npm run typecheck
npm run lint
npm run build
```

This Next.js version differs from older ones (for example, middleware is now `proxy`): read the guides in
`node_modules/next/dist/docs/` before changing framework code (see AGENTS.md).

Built one step at a time, screens first with sample data, then connected:
1. Sign-in pages (sign in, create an account, reset password). Sign-in is a demo stub; nothing is sent yet.
