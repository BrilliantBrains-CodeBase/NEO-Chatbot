"use client";

import Placeholder from "@/components/crm/Placeholder";
import { useCrm } from "@/components/crm/CrmProvider";

// Sub-step 2 (CRM frame): the screen's header from the design; its content is built in a later step.
export default function TeamPage() {
  const { clinic } = useCrm();
  return (
    <Placeholder
      title={"Team"}
      description={`People who can sign in to ${clinic}, their roles and access.`}
      next={["Members, access requests, roles and permissions", "Invite, edit, disable and password reset", "New lead assignment (round robin among Front Desk)"]}
    />
  );
}
