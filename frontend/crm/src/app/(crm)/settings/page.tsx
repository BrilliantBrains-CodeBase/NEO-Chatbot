"use client";

import BellCard from "@/components/crm/BellCard";
import PasswordCard from "@/components/crm/PasswordCard";
import ProfileCard from "@/components/crm/ProfileCard";

// Settings: how my account works. Clinic setup stays in the Dashboard (Clinic info, Integrations, Team).
export default function SettingsPage() {
  return (
    <>
      <div className="ph">
        <div>
          <h1>Settings</h1>
          <p>Your profile, password and notifications.</p>
        </div>
      </div>
      <ProfileCard />
      <PasswordCard />
      <BellCard />
    </>
  );
}
