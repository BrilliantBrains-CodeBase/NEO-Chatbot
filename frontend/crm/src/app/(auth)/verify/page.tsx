import type { Metadata } from "next";
import VerifyCodeForm from "@/components/auth/VerifyCodeForm";

export const metadata: Metadata = { title: "NEO CRM | Sign-in code" };

export default function VerifyPage() {
  return <VerifyCodeForm />;
}
