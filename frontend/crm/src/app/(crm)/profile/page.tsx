"use client";

import { Suspense } from "react";
import ProfileView from "@/components/settings/ProfileView";

// My profile: the signed-in person's details, email, password, own notifications and roles.
export default function ProfilePage() {
  return (
    <Suspense fallback={null}>
      <ProfileView />
    </Suspense>
  );
}
