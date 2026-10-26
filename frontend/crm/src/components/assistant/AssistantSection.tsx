"use client";

import { useCrm } from "@/components/crm/CrmProvider";
import Placeholder from "@/components/crm/Placeholder";
import AppearanceView from "./AppearanceView";
import { canUseConsole, type Section } from "@/lib/assistant";

/** One console section. Each is built in its stage; until then it shows the design's header. */
export default function AssistantSection({ section }: { section: Section }) {
  const { clinic, me } = useCrm();
  const role = me?.clinics.find((c) => c.name === clinic)?.role;
  if (me && (!canUseConsole(role) || (section.bbOnly && !me.bb_admin))) {
    return (
      <div className="empty">
        <h2>No access</h2>
        The Dashboard is for clinic managers and BB Admin.
      </div>
    );
  }
  if (section.id === "appearance") return <AppearanceView />;
  return (
    <Placeholder
      title={section.label}
      description={`${clinic} · ${section.desc}`}
      next={[`Built in stage ${section.stage} of the Dashboard`]}
    />
  );
}
