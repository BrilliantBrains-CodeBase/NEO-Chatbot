"use client";

import ProfileCard from "@/components/crm/ProfileCard";

// My profile: my details (the same card is on Settings).
export default function ProfilePage() {
  return (
    <>
      <div className="ph">
        <div>
          <h1>My profile</h1>
          <p>Your details in the CRM.</p>
        </div>
      </div>
      <ProfileCard />
    </>
  );
}
