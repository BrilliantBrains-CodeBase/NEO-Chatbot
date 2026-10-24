import type { Metadata } from "next";
import CreateAccountForm from "@/components/auth/CreateAccountForm";

export const metadata: Metadata = { title: "NEO CRM | Create an account" };

export default function CreateAccountPage() {
  return <CreateAccountForm />;
}
