import { redirect } from "next/navigation";

// Team & access moved: old links still arrive.
export default function OldTeamPage() {
  redirect("/team");
}
