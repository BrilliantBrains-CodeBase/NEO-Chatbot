"use client";

import Placeholder from "@/components/crm/Placeholder";

// Sub-step 2 (CRM frame): the screen's header from the design; its content is built in a later step.
export default function TasksPage() {
  return (
    <Placeholder
      title={"Tasks"}
      description={"Who to call today: follow-ups, overdue callbacks and reminders."}
      next={["Mine or all", "Overdue in red", "Design to be agreed first (not in the approved design yet)"]}
    />
  );
}
