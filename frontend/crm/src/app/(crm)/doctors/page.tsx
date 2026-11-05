import Loading from "@/components/crm/Loading";
import { Suspense } from "react";
import DoctorsView from "./DoctorsView";

// The view reads ?doc= (one doctor's week) from the address: it renders inside a Suspense boundary.
export default function DoctorsPage() {
  return (
    <Suspense fallback={<Loading />}>
      <DoctorsView />
    </Suspense>
  );
}
