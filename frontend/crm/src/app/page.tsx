import { redirect } from "next/navigation";

// The CRM starts at sign-in. Once sign-in is connected, a signed-in user goes to the Dashboard instead.
export default function Home() {
  redirect("/sign-in");
}
