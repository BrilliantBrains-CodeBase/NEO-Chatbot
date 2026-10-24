"use client";

import Placeholder from "@/components/crm/Placeholder";

// Sub-step 2 (CRM frame): the screen's header from the design; its content is built in a later step.
export default function PatientsPage() {

  return (
    <Placeholder
      title={"Patients"}
      description={"Every unique person, one record per phone number."}
      next={["Source filters, search, treatments, date range and stage", "Export with chosen sources, treatments and columns"]}
    />
  );
}
