import { notFound } from "next/navigation";

// Tasks is turned off for everyone: the page returns 404.
export default function TasksPage() {
  notFound();
}
