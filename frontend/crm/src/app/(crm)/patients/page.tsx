import Loading from "@/components/crm/Loading";
import { Suspense } from "react";
import PatientsView from "@/components/patients/PatientsView";

export default function PatientsPage() {
  return (
    <Suspense fallback={<Loading />}>
      <PatientsView />
    </Suspense>
  );
}
