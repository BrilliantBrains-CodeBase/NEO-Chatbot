import type { Metadata } from "next";
import SignInForm from "@/components/auth/SignInForm";

export const metadata: Metadata = { title: "NEO CRM | Sign in" };

export default function SignInPage() {
  return <SignInForm />;
}
