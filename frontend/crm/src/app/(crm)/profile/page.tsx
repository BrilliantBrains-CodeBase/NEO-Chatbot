"use client";

import Placeholder from "@/components/crm/Placeholder";
import { useCrm } from "@/components/crm/CrmProvider";

// Sub-step 2 (CRM frame): the screen's header from the design; its content is built in a later step.
export default function ProfilePage() {
  const { me } = useCrm();
  return (
    <Placeholder
      title={me?.name ?? ""}
      description={me ? `${me.role_label} · ${me.clinics.map((c) => c.name).join(", ")}` : ""}
      next={["Personal details", "Change password", "My notifications and sign out"]}
    />
  );
}
