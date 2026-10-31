import { notFound } from "next/navigation";

// Reports is turned off for everyone: the page returns 404.
export default function ReportsPage() {
  notFound();
}
