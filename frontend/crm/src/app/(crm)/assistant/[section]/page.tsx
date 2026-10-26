import { notFound } from "next/navigation";
import AssistantSection from "@/components/assistant/AssistantSection";
import { SECTIONS } from "@/lib/assistant";

export function generateStaticParams() {
  return SECTIONS.map((s) => ({ section: s.id }));
}

export default async function SectionPage({
  params,
}: {
  params: Promise<{ section: string }>;
}) {
  const { section } = await params;
  const s = SECTIONS.find((x) => x.id === section);
  if (!s) notFound();
  return <AssistantSection section={s} />;
}
