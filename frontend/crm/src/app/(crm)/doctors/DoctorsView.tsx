"use client";

import { useSearchParams } from "next/navigation";
import Live, { Today } from "@/components/crm/Live";
import Placeholder from "@/components/crm/Placeholder";

// Sub-step 2 (CRM frame): the screen's header from the design; its content is built in a later step. Reads
// ?doc= from the address, so the page renders it inside a Suspense boundary.
export default function DoctorsView() {
  const doc = useSearchParams().get("doc") ?? "";
  return (
    <Placeholder
      title={doc || "Doctors Availability"}
      description={
        doc ? (
          "Week schedule, leave and slot settings"
        ) : (
          <>
            Today, <Live><Today /></Live>
          </>
        )
      }
      next={["A card per doctor: booked, free and pending today", "A doctor's week grid in 15 or 30 minute slots", "Mark leave, edit schedule, book a free slot"]}
    />
  );
}
