import { Suspense } from "react";
import LeadsView from "@/components/leads/LeadsView";

export default function LeadsPage() {
  return (
    <Suspense>
      <LeadsView />
    </Suspense>
  );
}
