import Loading from "@/components/crm/Loading";
import { Suspense } from "react";
import InboxView from "@/components/inbox/InboxView";

export default function InboxPage() {
  return (
    <Suspense fallback={<Loading />}>
      <InboxView />
    </Suspense>
  );
}
