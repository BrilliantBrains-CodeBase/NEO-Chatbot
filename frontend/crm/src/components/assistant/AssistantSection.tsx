"use client";

import { useCrm } from "@/components/crm/CrmProvider";
import Placeholder from "@/components/crm/Placeholder";
import AppearanceView from "./AppearanceView";
import ClinicInfoView from "./ClinicInfoView";
import WorkflowView from "./workflow/WorkflowView";
import TemplatesView from "./TemplatesView";
import WebsiteInstallView from "./WebsiteInstallView";
import IntegrationsView from "./IntegrationsView";
import TeamView from "./TeamView";
import SecurityView from "./SecurityView";
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
  if (section.id === "templates") return <TemplatesView />;
  if (section.id === "menu") return <WorkflowView />;
  if (section.id === "content") return <ClinicInfoView />;
  if (section.id === "install") return <WebsiteInstallView />;
  if (section.id === "integrations") return <IntegrationsView />;
  if (section.id === "team") return <TeamView manage />;
  if (section.id === "security") return <SecurityView />;
  return (
    <Placeholder
      title={section.label}
      description={`${clinic} · ${section.desc}`}
      next={[`Built in stage ${section.stage} of the Dashboard`]}
    />
  );
}
