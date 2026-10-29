"use client";

import TeamView from "@/components/assistant/TeamView";

// CRM → Team: your own profile; Clinic Managers and BB Admin see everyone in the clinic. Access is managed in
// Dashboard → Team & access.
export default function TeamPage() {
  return <TeamView manage={false} />;
}
