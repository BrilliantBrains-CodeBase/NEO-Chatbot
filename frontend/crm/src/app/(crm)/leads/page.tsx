import Loading from "@/components/crm/Loading";
import { Suspense } from "react";
import LeadsView from "@/components/leads/LeadsView";

export default function LeadsPage() {
  return (
    <Suspense fallback={<Loading />}>
      <LeadsView />
    </Suspense>
  );
}
