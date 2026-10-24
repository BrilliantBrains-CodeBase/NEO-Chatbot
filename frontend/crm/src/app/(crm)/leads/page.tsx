"use client";

import Placeholder from "@/components/crm/Placeholder";

// Sub-step 2 (CRM frame): the screen's header from the design; its content is built in a later step.
export default function LeadsPage() {

  return (
    <Placeholder
      title={"Leads"}
      description={"Every lead from chatbot, ads, calls and walk-ins."}
      next={["Stage tabs, search and filters (source, type, doctor, assigned)", "Table and board views, CSV export", "Lead panel: stage and owner, key info, timeline, chat, notes, call log", "Add lead form with duplicate check"]}
    />
  );
}
