"use client";

import Placeholder from "@/components/crm/Placeholder";
import { useCrm } from "@/components/crm/CrmProvider";

// Sub-step 2 (CRM frame): the screen's header from the design; its content is built in a later step.
export default function SettingsPage() {
  const { clinic } = useCrm();
  return (
    <Placeholder
      title={"Settings"}
      description={clinic}
      next={["Clinic profile, timings and holidays, doctors, treatments", "Lead settings, notifications, integrations, audit log"]}
    />
  );
}
