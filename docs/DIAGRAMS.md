# Plan diagrams

Pictures of the design in [RAG-AND-LEADS.md](RAG-AND-LEADS.md). GitHub draws them automatically. In VS Code, open the Markdown preview (a Mermaid extension may be needed).

---

## 1. Whole system

```mermaid
flowchart TB
  subgraph Sites["Clinic websites (one script tag each)"]
    W1["neofollicletransplant.com<br/>Arya AI · NFHT"]
    W2["neofertility.co.in<br/>Navya AI · CL02"]
    W3["dermasolutions.co.in<br/>Diya AI · CL03"]
  end

  subgraph Server["Linode Mumbai · Docker Compose · Caddy HTTPS"]
    API["FastAPI<br/>/v1/chat/message · /v1/widget/config · CRM API"]
    LG["LangGraph answer pipeline"]
    FE["Flow engine<br/>book · online · cancel · reschedule · callback · lead"]
    WK["Workers (arq)<br/>KB ingest · outbox · Sheets sync · task timers"]
    R[("Redis<br/>sessions · slot holds · cache · rate limits")]
  end

  subgraph DB["Supabase (one database, every row has clinic_id)"]
    PG[("Postgres + pgvector<br/>leads · appointments · tasks · KB · chats")]
    AU["Auth (email + password)"]
    RT["Realtime (live CRM alerts)"]
  end

  CRM["NEO CRM (Next.js)<br/>Front Desk · Clinic Manager · Doctor · BB Admin"]

  subgraph Ext["Integrations (mocked until keys arrive)"]
    LLM["Groq, then Gemini<br/>last resort only"]
    IK["Interakt WhatsApp"]
    GC["Google Calendar / Meet"]
    GS["Google Sheets ads leads"]
  end

  W1 & W2 & W3 -- "JSON over HTTPS" --> API
  API --> LG --> FE
  LG --> R
  FE --> R
  LG --> PG
  FE --> PG
  LG -. "no answer found" .-> LLM
  WK --> PG
  WK --> IK & GC
  GS --> WK
  PG --> RT --> CRM
  CRM -- "JSON" --> API
  CRM --> AU
```

---

## 2. Answer pipeline (one message)

```mermaid
flowchart TD
  IN(["Patient message (JSON)"]) --> LS["load_session<br/>Redis, 30 min idle"]
  LS --> CI["check_input<br/>rate limit · 500 chars · injection"]
  CI --> DL["detect_language<br/>English or Hinglish"]
  DL --> EM{"Emergency words?"}
  EM -- yes --> EMR["Emergency reply<br/>Call 108 · Call clinic"]
  EM -- no --> RO{"Button, or text that<br/>answers the open step?"}
  RO -- yes --> FL["Flow engine"]
  RO -- no --> CL{"classify<br/>rules + fuzzy, then<br/>embedding classifier"}
  CL -- medical --> LC["Lead capture<br/>name · phone · email<br/>question = reason"]
  CL -- intent --> FL
  CL -- clinic question --> KB{"Knowledge base<br/>cache, then hybrid search<br/>(keyword + vector, this clinic only)"}
  KB -- "score ≥ HIGH" --> ANS["Answer word for word"]
  KB -- "LOW to HIGH" --> DYM["Did you mean? chips"]
  KB -- "score < LOW" --> LLM{"LLM: Groq, then Gemini<br/>KB text only · strict JSON"}
  LLM -- "valid, grounded,<br/>not medical, no other clinic" --> ANS
  LLM -- "fails any check" --> LC
  ANS --> LO["localise<br/>Hinglish rewrite, numbers unchanged"]
  DYM --> RS
  LO --> RS{"Flow was open?"}
  RS -- yes --> RE["Ask the same step again<br/>(data kept)"]
  RS -- no --> OUT
  RE --> OUT
  FL --> OUT
  LC --> OUT
  EMR --> OUT(["respond: messages · ui · input · quick<br/>save transcript and session"])
```

---

## 3. Booking and slot life cycle

```mermaid
stateDiagram-v2
  [*] --> Free: in availability, within 2 weeks
  Free --> Held: patient picks a time (5 min hold)
  Held --> Free: no confirm in 5 min
  Held --> Pending: patient confirms (still hidden)
  Free --> Confirmed: staff book it in CRM
  Pending --> Confirmed: staff confirm by phone
  Pending --> Free: staff reject or patient cancels
  Pending --> Missed: slot time passes unconfirmed
  Confirmed --> Free: cancelled
  Confirmed --> Visited: patient attends
  Confirmed --> NoShow: patient does not come
  Visited --> [*]
  NoShow --> [*]
  Missed --> [*]

  note right of Pending
    Not confirmed in 2 working hours
    → alert to Clinic Manager
  end note
```

Only **Free** slots are ever shown in the chatbot. The database blocks two active bookings on the same doctor and time.

---

## 4. Lead life cycle and follow-up

```mermaid
flowchart LR
  SRC["Chatbot · Meta Ads · Google Ads<br/>Manual · WhatsApp"] --> UP{"Same phone or email<br/>in this clinic?"}
  UP -- yes --> UPD["Update lead<br/>contact_count + 1<br/>add to timeline"]
  UP -- no --> NEW["Create lead<br/>stage New"]
  NEW --> AS["Round robin to<br/>Front Desk"]
  UPD --> AS
  AS --> AL["Live CRM alert"]
  AS --> T1["Task: Call patient<br/>due in 30 min<br/>(or next working day)"]
  T1 --> OC{"Call outcome"}
  OC -- Answered --> FU["Follow Up"]
  OC -- "No answer / Busy" --> RT{"Tries < 3?"}
  RT -- yes --> T2["Retry task<br/>next working day"] --> OC
  RT -- no --> LOST["Lost<br/>Not reachable"]
  OC -- "Wrong number" --> INV["Invalid"]
  FU --> BK["Booked<br/>(appointment confirmed)"]
  FU --> LOST2["Lost<br/>with reason"]
  BK --> VI["Visited<br/>→ Patient record"]
```

---

## 5. Who can do what in the CRM

```mermaid
flowchart LR
  BA["BB Admin<br/>all clinics"] --> ALL["Everything<br/>incl. export, delete, team, settings"]
  CM["Clinic Manager<br/>own clinic"] --> MG["Leads · reassign · appointments<br/>availability · KB approve · export · settings"]
  FD["Front Desk<br/>own clinic"] --> FDA["Leads · calls · tasks<br/>confirm or reject appointments · availability"]
  DR["Doctor<br/>own clinic"] --> DRA["Own appointments<br/>own availability and leave"]
```

Every stage change, assignment, export and delete is written to the audit log.

---

## 6. Build order

```mermaid
flowchart LR
  S1["1. Widgets<br/>Steps 3-11, mock backend"] --> S2["2. CRM screens<br/>approved design"]
  S2 --> S3["3. Database<br/>migrations · Auth · RLS"]
  S3 --> S4["4. Flows · slots · leads<br/>tasks · alerts (mock → real)"]
  S4 --> S5["5. Knowledge base<br/>classifier · hybrid search · LangGraph"]
  S5 --> S6["6. LLM fallback<br/>and Hinglish"]
  S6 --> S7["7. Sheets · Interakt<br/>Google Calendar"]
  S7 --> S8["8. Tests · tuning<br/>deploy · sign-off"]
```
