"use client";

import Placeholder from "@/components/crm/Placeholder";
import { useCrm } from "@/components/crm/CrmProvider";

// Sub-step 2 (CRM frame): the screen's header from the design; its content is built in a later step.
export default function ProfilePage() {
  const { clinic } = useCrm();
  return (
    <Placeholder
      title={"Priya S"}
      description={`Front Desk · ${clinic}`}
      next={["Personal details", "Change password", "My notifications and sign out"]}
    />
  );
}
