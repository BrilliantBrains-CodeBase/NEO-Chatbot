import type { Metadata } from "next";
import SetPasswordForm from "@/components/auth/SetPasswordForm";

export const metadata: Metadata = { title: "NEO CRM | Set password" };

export default function SetPasswordPage() {
  return <SetPasswordForm />;
}
