import { Suspense } from "react";
import AppointmentsView from "@/components/appointments/AppointmentsView";

export default function AppointmentsPage() {
  // The view reads ?day= and ?open= from the address: it renders inside a Suspense boundary.
  return (
    <Suspense>
      <AppointmentsView />
    </Suspense>
  );
}
