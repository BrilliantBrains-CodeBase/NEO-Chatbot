"use client";

import Placeholder from "@/components/crm/Placeholder";

// Sub-step 2 (CRM frame): the screen's header from the design; its content is built in a later step.
export default function AppointmentsPage() {
  return (
    <Placeholder
      title={"Appointments"}
      description={"Confirmed visits by doctor and day. Mark patients as visited or no-show."}
      next={["Day view by doctor, week view and list", "Visited, no-show and cancel", "Appointment panel with Meet link"]}
    />
  );
}
