"use client";

import Placeholder from "@/components/crm/Placeholder";
import { useCrm } from "@/components/crm/CrmProvider";

// Sub-step 2 (CRM frame): the screen's header from the design; its content is built in a later step.
export default function ReportsPage() {
  const { clinic } = useCrm();
  return (
    <Placeholder
      title={"Reports"}
      description={`${clinic} · Last 30 days`}
      next={["Overview, sources, treatments, doctors, staff and chatbot", "Date range and CSV export"]}
    />
  );
}
