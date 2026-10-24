"use client";

import Live, { Today } from "@/components/crm/Live";
import Placeholder from "@/components/crm/Placeholder";
import { useCrm } from "@/components/crm/CrmProvider";

// Sub-step 2 (CRM frame): the screen's header from the design; its content is built in a later step.
export default function DashboardPage() {
  const { clinic } = useCrm();
  return (
    <Placeholder
      title={"Good morning, Priya"}
      description={
        <>
          {clinic} · <Live><Today /></Live>
        </>
      }
      next={["4 key numbers: new leads, pending in Inbox, callbacks waiting, follow-ups due today", "Today's appointments and doctors on duty", "Leads by source, funnel, chatbot numbers and top treatments"]}
    />
  );
}
