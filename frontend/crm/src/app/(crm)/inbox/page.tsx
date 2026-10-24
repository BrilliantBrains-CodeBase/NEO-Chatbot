"use client";

import Placeholder from "@/components/crm/Placeholder";

// Sub-step 2 (CRM frame): the screen's header from the design; its content is built in a later step.
export default function InboxPage() {

  return (
    <Placeholder
      title={"Inbox"}
      description={"Approve bookings, handle cancellations and reschedules, call back patients and read chats."}
      next={["Booking requests, online consults, cancellations, reschedules, callbacks, chatbot chats", "Approval with the doctor's free slots, approve with change, reject with reason", "Callback outcomes and chat transcripts"]}
    />
  );
}
