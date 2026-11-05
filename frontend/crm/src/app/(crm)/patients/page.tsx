import { Suspense } from "react";
import PatientsView from "@/components/patients/PatientsView";

export default function PatientsPage() {
  return (
    <Suspense>
      <PatientsView />
    </Suspense>
  );
}
